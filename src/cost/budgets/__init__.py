"""Exact cost, tenant budgets with a soft cap, showback, reconciliation and the release cost gate (FR-43 /
CR-ADP-04: CR-D4, CR-D7, CR-D11, CR-D12).

- Ledger.record(): the provider-reported usage of one completion, added atomically to the tenant's month,
  model and route. Only a model in the price table is accepted, so every token has a price.
- cost = tokens x the versioned price table (USD per million tokens), in Decimal.
- band(): NOMINAL under 80% of the tenant's monthly budget; WARNING from 80% (the tenant's admins are told
  once a month); SOFT_CAP from 100%: knowledge-base-only answers with SOFT_CAP_NOTICE, never a shutdown. A
  tenant without a budget is NOMINAL.
- report(): the month's tokens and cost per model and route, for the tenant's admins (showback, no
  chargeback).
- reconcile(): the ledger's cost per model against the provider invoices; a gap over 2% is flagged.
- release_gate(): a release may raise the cost per resolved conversation of any route by at most 10% over
  the previous release and never above 1.5x the baseline.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from data.migrate import psql

WARN_AT, CAP_AT = Decimal("0.80"), Decimal("1.00")
RECONCILE_TOLERANCE = Decimal("0.02")
RELEASE_RISE, BASELINE_CEILING = Decimal("1.10"), Decimal("1.50")
SOFT_CAP_NOTICE = ("Your organization has reached its monthly advanced automation limit. You are currently "
                   "receiving basic knowledge support.")
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Prices:
    version: str
    per_million: dict      # model -> (input USD, output USD) per million tokens, as Decimals

    def cost(self, model, prompt_tokens, completion_tokens):
        rate_in, rate_out = self.per_million[model]
        return (Decimal(prompt_tokens) * rate_in + Decimal(completion_tokens) * rate_out) / MILLION


class Band(str, Enum):
    NOMINAL = "nominal"
    WARNING = "warning"
    SOFT_CAP = "soft_cap"


SCHEMA_NAME = "cost_0002_budgets.sql"
SCHEMA = """
CREATE TABLE usage_ledger (
  tenant_id         text NOT NULL REFERENCES tenants (id),
  month             text NOT NULL CHECK (month ~ '^[0-9]{4}-[0-9]{2}$'),
  model             text NOT NULL,
  route             text NOT NULL,
  prompt_tokens     bigint NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
  completion_tokens bigint NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
  PRIMARY KEY (tenant_id, month, model, route)
);
CREATE TABLE tenant_budgets (
  tenant_id    text PRIMARY KEY REFERENCES tenants (id),
  monthly_usd  numeric(12, 2) NOT NULL CHECK (monthly_usd > 0),
  warned_month text
);
"""
for table in ("usage_ledger", "tenant_budgets"):
    SCHEMA += f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {table}
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE {table} OWNER TO app_owner;
"""
SCHEMA += """
GRANT SELECT, INSERT ON usage_ledger TO app_runtime;
GRANT UPDATE (prompt_tokens, completion_tokens) ON usage_ledger TO app_runtime;
GRANT SELECT ON tenant_budgets TO app_runtime;
GRANT UPDATE (warned_month) ON tenant_budgets TO app_runtime;
"""


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def month_of(moment=None):
    return (moment or datetime.now(timezone.utc)).strftime("%Y-%m")


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


class Ledger:
    def __init__(self, connect, prices, notify_admins):
        """notify_admins(tenant_id, text): the 80% notice to the tenant's admins."""
        self.connect, self.prices, self.notify_admins = connect, prices, notify_admins

    def record(self, tenant_id, model, route, usage, moment=None):
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if any(type(n) is not int or n < 0 for n in (prompt, completion)):
            raise ValueError("usage must be the provider's prompt and completion token counts")
        if model not in self.prices.per_million:
            raise ValueError(f"{model!r} has no price in table {self.prices.version}")
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            conn.execute("INSERT INTO usage_ledger (tenant_id, month, model, route, prompt_tokens, "
                         "completion_tokens) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, month, "
                         "model, route) DO UPDATE SET prompt_tokens = usage_ledger.prompt_tokens + "
                         "excluded.prompt_tokens, completion_tokens = usage_ledger.completion_tokens + "
                         "excluded.completion_tokens",
                         (tenant_id, month_of(moment), model, route, prompt, completion))

    def _rows(self, conn, month):
        return conn.execute("SELECT model, route, prompt_tokens, completion_tokens FROM usage_ledger "
                            "WHERE month = %s ORDER BY model, route", (month,)).fetchall()

    def report(self, tenant_id, month):
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            rows = self._rows(conn, month)
            budget = conn.execute("SELECT monthly_usd FROM tenant_budgets").fetchone()
        lines = [{"model": m, "route": r, "prompt_tokens": p, "completion_tokens": c,
                  "cost_usd": self.prices.cost(m, p, c)} for m, r, p, c in rows]
        total = sum((line["cost_usd"] for line in lines), Decimal(0))
        return {"tenant_id": tenant_id, "month": month, "price_table": self.prices.version, "lines": lines,
                "total_usd": total, "budget_usd": budget and Decimal(budget[0]),
                "used": budget and total / Decimal(budget[0])}

    def band(self, tenant_id, moment=None):
        month = month_of(moment)
        report = self.report(tenant_id, month)
        if report["budget_usd"] is None:
            return Band.NOMINAL
        used = report["used"]
        if used >= CAP_AT:
            return Band.SOFT_CAP
        if used >= WARN_AT:
            with self.connect() as conn, conn.transaction():
                _context(conn, tenant_id)
                first = conn.execute("UPDATE tenant_budgets SET warned_month = %s WHERE warned_month IS "
                                     "DISTINCT FROM %s", (month, month)).rowcount
            if first:
                self.notify_admins(tenant_id, f"Your organization has used {used:.0%} of its monthly budget.")
            return Band.WARNING
        return Band.NOMINAL

    def reconcile(self, tenants, month, invoices):
        """invoices: {model: USD billed for the month, all tenants}; returns {model: (ledger, invoice, gap)}
        for each model whose gap exceeds the tolerance (or that only one side has)."""
        ledger = {}
        for tenant_id in tenants:
            for line in self.report(tenant_id, month)["lines"]:
                ledger[line["model"]] = ledger.get(line["model"], Decimal(0)) + line["cost_usd"]
        flagged = {}
        for model in set(ledger) | set(invoices):
            ours, billed = ledger.get(model, Decimal(0)), Decimal(str(invoices.get(model, 0)))
            gap = abs(ours - billed) / billed if billed else (Decimal(1) if ours else Decimal(0))
            if gap > RECONCILE_TOLERANCE:
                flagged[model] = (ours, billed, gap)
        return flagged


def release_gate(candidate, previous, baseline):
    """{route: USD per resolved conversation} for the candidate, the previous release and the baseline;
    returns the violations (empty: the release may ship). A route missing from previous or baseline cannot
    be compared and is a violation."""
    violations = []
    for route, cost in candidate.items():
        cost = Decimal(str(cost))
        if route not in previous or route not in baseline:
            violations.append(f"{route}: no previous release or baseline to compare with")
            continue
        if cost > RELEASE_RISE * Decimal(str(previous[route])):
            violations.append(f"{route}: {cost} is more than 10% over the previous release")
        if cost > BASELINE_CEILING * Decimal(str(baseline[route])):
            violations.append(f"{route}: {cost} is more than 1.5x the baseline")
    return violations
