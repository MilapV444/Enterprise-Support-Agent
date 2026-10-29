"""Evaluation datasets and their governance (NFR-6 / EV-ADP-01: EV-D1, EV-D10, EV-D15).

- Episodes: the framework scenarios as hand-written seeds (framework_seeds.json), each with its stratum
  (routine / edge / risk), route and expected assertions; plus production samples.
- Production samples need the tenant's explicit opt-in (default off). Opting in or out is an append-only
  record of who did it and when; the current state is the latest record. A sample is tokenized (the PII
  tokenizer, then refused if anything personal is left), stored with the tenant's own region, names the user
  only by subject hash, and is erased by user (erase()).
- weighted_mean(): the stratified estimate: each stratum's mean weighted by its production share P(s), so
  sampling edge and risk cases at the evaluation mix Q (more than production sees) does not bias the result.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from psycopg.types.json import Jsonb

from data.migrate import psql
from safety.pii.tokens import find as find_pii

STRATA = ("routine", "edge", "risk")
PRODUCTION_MIX = {"routine": 0.80, "edge": 0.15, "risk": 0.05}     # P
EVALUATION_MIX = {"routine": 0.30, "edge": 0.40, "risk": 0.30}     # Q
SEEDS = Path(__file__).with_name("framework_seeds.json")

SCHEMA_NAME = "evals_0001_datasets.sql"
SCHEMA = """
CREATE TABLE eval_opt_in (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id text NOT NULL REFERENCES tenants (id),
  opted_in  boolean NOT NULL,
  by_admin  text NOT NULL,
  at        timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER eval_opt_in_append_only BEFORE UPDATE OR DELETE ON eval_opt_in
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TABLE eval_samples (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  region          text NOT NULL,
  user_hash       text NOT NULL,
  conversation_id text NOT NULL,
  stratum         text NOT NULL CHECK (stratum IN ('routine', 'edge', 'risk')),
  route           text NOT NULL,
  turns           jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX eval_samples_user ON eval_samples (tenant_id, user_hash);
"""
for table in ("eval_opt_in", "eval_samples"):
    SCHEMA += f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {table}
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE {table} OWNER TO app_owner;
"""
SCHEMA += """
GRANT SELECT, INSERT ON eval_opt_in TO app_runtime;
GRANT SELECT, INSERT, DELETE ON eval_samples TO app_runtime;
"""


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


@dataclass(frozen=True)
class Episode:
    id: str
    stratum: str
    route: str
    source: str                        # "framework", "seed" or "production"
    turns: tuple[str, ...]
    expect: dict = field(default_factory=dict)


def framework_episodes():
    return [Episode(e["id"], e["stratum"], e["route"], e["source"], tuple(e["turns"]), e["expect"])
            for e in json.loads(SEEDS.read_text(encoding="utf-8"))]


def subject_hash(tenant_id, principal_id):
    return hashlib.sha256(f"{tenant_id}\x1f{principal_id}".encode()).hexdigest()


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


class Samples:
    def __init__(self, connect, tokenizer):
        self.connect, self.tokenizer = connect, tokenizer

    def set_opt_in(self, tenant_id, admin, opted_in):
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            conn.execute("INSERT INTO eval_opt_in (tenant_id, opted_in, by_admin) VALUES (%s, %s, %s)",
                         (tenant_id, opted_in, admin))

    def opted_in(self, conn, tenant_id):
        row = conn.execute("SELECT opted_in FROM eval_opt_in ORDER BY at DESC, id DESC LIMIT 1").fetchone()
        return bool(row and row[0])

    def sample(self, tenant_id, principal_id, conversation_id, turns, stratum, route):
        """Store a production conversation for evaluation; returns the sample id, or None when the tenant
        has not opted in."""
        if stratum not in STRATA:
            raise ValueError(f"unknown stratum {stratum!r}")
        masked = [self.tokenizer.mask(turn)[0] for turn in turns]
        if any(find_pii(turn) for turn in masked):
            raise ValueError("a turn still holds personal data after tokenization")
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            if not self.opted_in(conn, tenant_id):
                return None
            (region,) = conn.execute("SELECT region FROM tenants WHERE id = %s", (tenant_id,)).fetchone()
            (sample_id,) = conn.execute(
                "INSERT INTO eval_samples (tenant_id, region, user_hash, conversation_id, stratum, route, "
                "turns) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (tenant_id, region, subject_hash(tenant_id, principal_id), conversation_id, stratum, route,
                 Jsonb(masked))).fetchone()
        return sample_id

    def erase(self, tenant_id, principal_id):
        """Delete every sample of the user; returns how many."""
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            return conn.execute("DELETE FROM eval_samples WHERE user_hash = %s",
                                (subject_hash(tenant_id, principal_id),)).rowcount

    def episodes(self, tenant_id, region):
        """The tenant's samples as episodes, refusing to read them from another region."""
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            (home,) = conn.execute("SELECT region FROM tenants WHERE id = %s", (tenant_id,)).fetchone()
            if home != region:
                raise PermissionError(f"{tenant_id}'s samples stay in {home}")
            rows = conn.execute("SELECT id, stratum, route, turns FROM eval_samples ORDER BY id").fetchall()
        return [Episode(f"sample-{i}", s, r, "production", tuple(t)) for i, s, r, t in rows]


def weighted_mean(results, production=PRODUCTION_MIX):
    """results: {stratum: [metric values]}; the population estimate sum_s P(s) x mean_s. (The pooled
    importance-sampling form, (1 / N) sum_i P(s_i) / Q(s_i) x Y_i with N_s = Q(s) x N, reduces to this; the
    ADP's sum_s P(s) / Q(s) x mean_s leaves out the Q(s) factor and would not estimate the production mean.) A
    stratum without results cannot be estimated."""
    missing = [s for s in STRATA if not results.get(s)]
    if missing:
        raise ValueError(f"no results for {missing}")
    return sum(production[s] * sum(results[s]) / len(results[s]) for s in STRATA)
