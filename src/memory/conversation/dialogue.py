"""Dialogue memory for one conversation (FR-15 / MS-ADP-01: MS-D2, MS-Q2).

The dialogue slot is three parts, and compaction only ever touches the second:
- pins: constraints and identifiers the customer stated. Identifiers (INV-9821) are pinned on sight;
  a negation clause ("do not reboot production") is pinned when Jev says it is a hard constraint, or when Jev
  cannot answer (losing a constraint is worse than keeping one). Every new customer message is checked against
  each active constraint and a confident "this withdraws it" revokes it, with the turn kept as the reason.
  At most MAX_PINS are active; past that, pinning stops and the turn reports an overflow for a human.
- summary: older turns folded into a rolling summary by `summarize(previous, turns, pins) -> str`. A summary
  that introduces a number or identifier its sources do not have is refused and the turns stay verbatim.
- verbatim: the last VERBATIM turns, as stored.
Pins from every conversation on the same case are part of the buffer, so a follow-up conversation keeps them.

Turns are stored already masked (PII tokens). A turn is written at the next sequence number the caller saw;
a second writer with the same number gets StaleTurn (HTTP 409). Tables are module-owned (DECISION-d4b79fe1);
connections are autocommit and every query runs as app_runtime under the tenant's row-level security.
"""

import re
from dataclasses import dataclass, field

import psycopg

from core.orchestrator.decisions import JevUnavailable, mask
from data.migrate import psql

VERBATIM = 8
MAX_PINS = 10
PIN_CONFIDENCE, REVOKE_CONFIDENCE = 0.85, 0.80
IDENTIFIER = re.compile(r"\b[A-Z]{3,4}-[0-9]{4,8}\b")
NEGATION = re.compile(r"\b(?:do not|don't|never|must not|cannot|can't|refuse to)\s+[a-z][a-z ]*",
                      re.IGNORECASE)
FIGURE = re.compile(r"\d[\d,.]*\d|\d")
UNFOLDED = ("SELECT seq, role, content FROM dialogue_turns WHERE conversation_id = %s AND seq > %s "
            "ORDER BY seq")
IS_CONSTRAINT = {"type": "noul", "instructions": "Is this statement an operational constraint or "
                                                 "non-negotiable directive that must never be violated?"}
WITHDRAWS = {"type": "noul", "instructions": "Does the customer's latest statement revoke, withdraw or "
                                             "contradict their earlier constraint?"}

SCHEMA_NAME = "memory_0001_dialogue.sql"
SCHEMA = """
CREATE TABLE dialogue_turns (
  tenant_id       text NOT NULL REFERENCES tenants (id),
  conversation_id text NOT NULL,
  seq             integer NOT NULL CHECK (seq >= 1),
  role            text NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
  content         text NOT NULL,  -- masked: PII tokens only
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, conversation_id, seq),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);

CREATE TABLE dialogue_summaries (
  tenant_id       text NOT NULL REFERENCES tenants (id),
  conversation_id text NOT NULL,
  summary         text NOT NULL,
  through_seq     integer NOT NULL,  -- turns up to here are folded in
  PRIMARY KEY (tenant_id, conversation_id),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);

CREATE TABLE dialogue_pins (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  conversation_id text NOT NULL,
  kind            text NOT NULL CHECK (kind IN ('constraint', 'identifier')),
  content         text NOT NULL,
  source_seq      integer NOT NULL,
  status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  revoked_by_seq  integer,
  created_at      timestamptz NOT NULL DEFAULT now(),
  revoked_at      timestamptz,
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);

ALTER TABLE dialogue_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_turns FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dialogue_turns
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE dialogue_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_summaries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dialogue_summaries
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE dialogue_pins ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_pins FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dialogue_pins
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

ALTER TABLE dialogue_turns OWNER TO app_owner;
ALTER TABLE dialogue_summaries OWNER TO app_owner;
ALTER TABLE dialogue_pins OWNER TO app_owner;
GRANT SELECT, INSERT ON dialogue_turns TO app_runtime;
GRANT SELECT, INSERT, UPDATE ON dialogue_summaries, dialogue_pins TO app_runtime;
"""


class StaleTurn(RuntimeError):
    """Another writer already took this sequence number: reload and resubmit (HTTP 409)."""


@dataclass
class Appended:
    pinned: list[str] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)
    pin_overflow: bool = False  # too many active pins: pinning stopped, a human should look


@dataclass
class Buffer:
    pins: list[dict]       # {"kind", "content"}, this case's active pins
    summary: str
    turns: list[dict]      # {"seq", "role", "content"}, oldest first

    def for_assembler(self):
        """Keyword arguments for core.context.assembler.assemble()."""
        return {"pins": [{"text": p["content"], "importance": 2 if p["kind"] == "constraint" else 1}
                         for p in self.pins],
                "summary": self.summary,
                "turns": [{"role": t["role"], "content": t["content"]} for t in self.turns]}


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def figures(text):
    return {f.replace(",", "") for f in FIGURE.findall(text)}


class Dialogue:
    def __init__(self, conn, engine, summarize, verbatim=VERBATIM):
        """engine: core.orchestrator.decisions.DecisionEngine; summarize(previous, turns, pins) -> str."""
        self.conn, self.engine, self.summarize, self.verbatim = conn, engine, summarize, verbatim

    def _jev_yes(self, question, state, threshold, unavailable):
        try:
            answer = self.engine.ask({k: mask(v) for k, v in state.items()}, {"q": question})["q"]
        except JevUnavailable:
            return unavailable
        return answer.value is True and answer.confidence >= threshold

    def _case_pins(self, conversation_id):
        """Active pins of every conversation on this conversation's case (or of the conversation alone)."""
        return self.conn.execute(
            "SELECT p.id, p.kind, p.content FROM dialogue_pins p "
            "JOIN conversations c ON c.id = p.conversation_id "
            "WHERE p.status = 'active' AND (c.id = %s OR c.case_id = "
            "(SELECT case_id FROM conversations WHERE id = %s)) ORDER BY p.id",
            (conversation_id, conversation_id)).fetchall()

    def append(self, tenant_id, conversation_id, seq, role, content):
        """Store turn `seq` (masked text). For a customer message, sweep revocations and pin new
        constraints."""
        result = Appended()
        with self.conn.transaction():
            _context(self.conn, tenant_id)
            try:
                with self.conn.transaction():
                    self.conn.execute("INSERT INTO dialogue_turns (tenant_id, conversation_id, seq, role, "
                                      "content) VALUES (%s, %s, %s, %s, %s)",
                                      (tenant_id, conversation_id, seq, role, content))
            except psycopg.errors.UniqueViolation as error:
                raise StaleTurn(f"turn {seq} of {conversation_id} already exists") from error
            if role != "user":
                return result
            pins = self._case_pins(conversation_id)
            for pin_id, kind, pinned in pins:
                withdrawn = {"constraint": pinned, "latest": content}
                if kind == "constraint" and self._jev_yes(WITHDRAWS, withdrawn, REVOKE_CONFIDENCE,
                                                          unavailable=False):
                    self.conn.execute("UPDATE dialogue_pins SET status = 'revoked', revoked_by_seq = %s, "
                                      "revoked_at = now() WHERE id = %s", (seq, pin_id))
                    result.revoked.append(pinned)
            active = {pinned for _, _, pinned in pins} - set(result.revoked)
            candidates = [("identifier", m.group(0)) for m in IDENTIFIER.finditer(content)]
            candidates += [("constraint", m.group(0).strip()) for m in NEGATION.finditer(content)
                           if self._jev_yes(IS_CONSTRAINT, {"statement": m.group(0)}, PIN_CONFIDENCE,
                                            unavailable=True)]
            for kind, text in candidates:
                if text in active:
                    continue
                if len(active) >= MAX_PINS:
                    result.pin_overflow = True
                    break
                self.conn.execute("INSERT INTO dialogue_pins (tenant_id, conversation_id, kind, content, "
                                  "source_seq) VALUES (%s, %s, %s, %s, %s)",
                                  (tenant_id, conversation_id, kind, text, seq))
                active.add(text)
                result.pinned.append(text)
        return result

    def compact(self, tenant_id, conversation_id):
        """Fold turns older than the verbatim window into the summary; returns True if it changed."""
        with self.conn.transaction():
            _context(self.conn, tenant_id)
            row = self.conn.execute("SELECT summary, through_seq FROM dialogue_summaries "
                                    "WHERE conversation_id = %s FOR UPDATE", (conversation_id,)).fetchone()
            previous, through = row or ("", 0)
            turns = self.conn.execute(UNFOLDED, (conversation_id, through)).fetchall()
            evicted = turns[:-self.verbatim] if len(turns) > self.verbatim else []
            if not evicted:
                return False
            pins = [content for _, _, content in self._case_pins(conversation_id)]
            folded = [{"role": role, "content": content} for _, role, content in evicted]
            summary = self.summarize(previous, folded, pins)
            sources = " ".join([previous, *pins, *(t["content"] for t in folded)])
            if not figures(summary) <= figures(sources):  # a changed or invented figure: keep the turns
                return False
            self.conn.execute(
                "INSERT INTO dialogue_summaries (tenant_id, conversation_id, summary, through_seq) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id, conversation_id) "
                "DO UPDATE SET summary = EXCLUDED.summary, through_seq = EXCLUDED.through_seq",
                (tenant_id, conversation_id, summary, evicted[-1][0]))
            return True

    def buffer(self, tenant_id, conversation_id):
        with self.conn.transaction():
            _context(self.conn, tenant_id)
            row = self.conn.execute("SELECT summary, through_seq FROM dialogue_summaries "
                                    "WHERE conversation_id = %s", (conversation_id,)).fetchone()
            summary, through = row or ("", 0)
            turns = self.conn.execute(UNFOLDED, (conversation_id, through)).fetchall()
            pins = self._case_pins(conversation_id)
        return Buffer([{"kind": kind, "content": content} for _, kind, content in pins], summary,
                      [{"seq": seq, "role": role, "content": content} for seq, role, content in turns])
