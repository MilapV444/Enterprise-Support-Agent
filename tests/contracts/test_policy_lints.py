"""M5-05: static checks over the code's own declarations, run in CI (NFR-25 / TQ-ADP-05: TQ-D7; NFR-21 TQ-D3's
Jev rule; NFR-23 / TQ-ADP-03: TQ-D6).

- Every table, in the SQL migrations and in every module-owned SCHEMA, has row-level security enabled and
  forced and a policy; the exceptions are listed with their reason.
- Migrations follow expand / contract: no statement that breaks code still running on the previous release
  (dropping or renaming a column or table, changing a column's type).
- Every Jev question in the code has a known type and no digits or money in its wording (the NUMBERS rule
  DecisionEngine enforces at run time, caught here before it can fail a live turn).
- Every framework scenario (one to eight) has its end-to-end test.
"""

import importlib
import re
from pathlib import Path

import pytest

from core.orchestrator.decisions import NUMBERS

ROOT = Path(__file__).resolve().parents[2]
NO_RLS = {"knowledge_tombstones": "register S15: per-tenant rows keyed by scope, no row-level security yet"}
BREAKING = re.compile(r"\bDROP\s+COLUMN\b|\bRENAME\b|\bALTER\s+COLUMN\s+\w+\s+(?:SET\s+DATA\s+)?TYPE\b|"
                      r"\bDROP\s+TABLE\b", re.I)


def module_names():
    for path in sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "evals").rglob("*.py")]):
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        parts = parts[1:] if parts[0] == "src" else parts
        yield ".".join(parts[:-1] if parts[-1] == "__init__" else parts), path


def sql_sources():
    """{source: SQL}: the migration files, and each module's SCHEMA strings as imported (loops expanded)."""
    sources = {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
               for p in (ROOT / "migrations").rglob("*.sql")}
    for name, path in module_names():
        if not re.search(r"^SCHEMA_NAME\s*=", path.read_text(encoding="utf-8"), re.M):
            continue
        module = importlib.import_module(name)
        for attribute in dir(module):
            value = getattr(module, attribute)
            if attribute.startswith("SCHEMA") and isinstance(value, str) and "CREATE" in value:
                sources[f"{name}.{attribute}"] = value
    return sources


SQL = sql_sources()
EVERYTHING = "\n".join(SQL.values())
TABLES = sorted({(m.group(1), source) for source, text in SQL.items()
                 for m in re.finditer(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", text, re.I)})


def test_the_lint_sees_every_store():
    names = {table for table, _ in TABLES}
    assert len(names) >= 30 and {"turns", "escalations", "user_facts", "pii_tokens", "eval_samples"} <= names


@pytest.mark.parametrize("table, source", TABLES, ids=[t for t, _ in TABLES])
def test_every_table_has_forced_row_level_security_and_a_policy(table, source):
    checks = {"enabled": rf"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
              "forced": rf"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
              "a policy": rf"CREATE POLICY \w+ ON {table}\b"}
    missing = [what for what, pattern in checks.items() if not re.search(pattern, EVERYTHING)]
    if table in NO_RLS:
        assert missing, f"{table} now has row-level security: drop it from NO_RLS and close {NO_RLS[table]}"
        return
    assert not missing, f"{table} ({source}) has no row-level security {', '.join(missing)}"


@pytest.mark.parametrize("source", sorted(SQL))
def test_migrations_only_expand(source):
    breaking = [m.group(0) for m in BREAKING.finditer(SQL[source])]
    assert not breaking, f"{source}: {breaking} breaks the previous release; expand now, contract later"


def test_the_expand_contract_lint_catches_breaking_statements():
    for statement in ("ALTER TABLE turns DROP COLUMN content", "ALTER TABLE turns RENAME COLUMN a TO b",
                      "ALTER TABLE turns ALTER COLUMN id TYPE bigint", "DROP TABLE turns",
                      "ALTER TABLE turns ALTER COLUMN id SET DATA TYPE text",
                      "ALTER TABLE turns RENAME TO t"):
        assert BREAKING.search(statement), statement
    assert not BREAKING.search("ALTER TABLE turns ADD COLUMN channel text; CREATE INDEX t_ix ON turns (id)")


# Jev questions ----------------------------------------------------------------------------------------------

def is_question(value):
    return isinstance(value, dict) and isinstance(value.get("instructions"), str) and "type" in value


def questions():
    """Every Jev question defined at module level: question dicts, maps of them, and question templates
    (module-level strings named *QUESTION or RELEVANT that a caller formats into a question)."""
    found = []
    for name, path in module_names():
        text = path.read_text(encoding="utf-8")
        if '"instructions"' not in text and "QUESTION" not in text:
            continue
        module = importlib.import_module(name)
        for attribute, value in vars(module).items():
            if is_question(value):
                found.append((f"{name}.{attribute}", value))
            elif isinstance(value, dict) and value and all(is_question(v) for v in value.values()):
                found += [(f"{name}.{attribute}.{qid}", q) for qid, q in value.items()]
            elif isinstance(value, str) and (attribute.endswith("QUESTION") or attribute == "RELEVANT"):
                found.append((f"{name}.{attribute}", {"type": "template", "instructions": value}))
    return found


QUESTIONS = questions()


def test_the_lint_finds_the_questions_of_every_decision_point():
    names = " ".join(name for name, _ in QUESTIONS)
    assert len(QUESTIONS) >= 15
    for where in ("orchestrator.decisions", "agents.merge", "hitl.gate", "hitl.queues", "memory.facts",
                  "tools.validation", "reliability.bursts", "cost.router", "observability.alerts"):
        assert where in names, where


@pytest.mark.parametrize("name, question", QUESTIONS, ids=[n for n, _ in QUESTIONS])
def test_every_jev_question_has_a_known_type_and_no_numbers(name, question):
    assert question["type"] in {"choice", "score", "noul", "template"}, name
    criteria = question.get("criteria") or []
    wording = [question["instructions"], *(criteria.values() if isinstance(criteria, dict) else criteria)]
    template = re.sub(r"\{\w*\}", "", " ".join(wording))          # a placeholder is filled by the caller
    assert not NUMBERS.search(template), f"{name}: numbers and money stay in code, not in Jev questions"
    if question["type"] in {"choice", "score"}:
        assert criteria, f"{name}: a {question['type']} question needs its options"


# Every framework scenario has its end-to-end test -----------------------------------------------------------

def test_every_framework_scenario_has_its_end_to_end_test():
    names = set()
    for path in (ROOT / "tests").rglob("test_*.py"):
        names |= set(re.findall(r"^def (test_scenario_(\d)_\w+)", path.read_text(encoding="utf-8"), re.M))
    covered = {int(number) for _, number in names}
    assert covered == set(range(1, 9)), f"scenarios without a test: {sorted(set(range(1, 9)) - covered)}"
