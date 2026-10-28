"""M4-05: the per-tenant answer cache (public-KB answers only, versioned keys, Jev eligibility) and tenant
budgets (exact cost, soft cap to knowledge-base answers, showback, reconciliation, release cost gate)
(FR-42, FR-43 / CR-ADP-03, CR-ADP-04)."""

import math
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable
from cost import budgets, cache
from cost.budgets import SOFT_CAP_NOTICE, Band, Ledger, Prices, release_gate
from cost.cache import AnswerCache, key
from data.migrate import PsqlError, migrate, psql

ROOT = Path(__file__).resolve().parents[2]
DB = "test_cost"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
QUESTION = "How do I rotate an API key?"
ANSWER = "Open Settings, then API keys, and choose Rotate [kb-12]."
PUBLIC = [("kb-12", "public")]


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (cache, budgets, cache):  # the second cache.apply_schema is a no-op
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), "
             "('t_eu', 'Globex', 'EU'), ('t_free', 'Initech', 'US')")


class Jev:
    def __init__(self, p_public=0.95, down=False):
        self.p, self.down, self.seen = p_public, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"public": Answer(self.p >= 0.5, max(self.p, 1 - self.p))}


@pytest.fixture
def answers(database):
    psql(DB, "DELETE FROM answer_cache")
    return AnswerCache(connect, DecisionEngine(Jev()))


# The answer cache -------------------------------------------------------------------------------------------

def test_a_public_documentation_answer_is_cached_for_its_tenant_and_versions(answers):
    assert answers.put("t_us", QUESTION, ANSWER, "7", "kb-v41", PUBLIC) is None
    assert answers.get("t_us", "how do I ROTATE an api-key", "7", "kb-v41") == ANSWER   # normalised question
    assert answers.get("t_eu", QUESTION, "7", "kb-v41") is None                      # another tenant
    assert answers.get("t_us", QUESTION, "8", "kb-v41") is None                      # another product version
    assert answers.get("t_us", QUESTION, "7", "kb-v42") is None                      # after the nightly sync


@pytest.mark.parametrize("change, reason", [
    ({"tools_called": ["crm.get_subscription"]}, "a tool ran"),
    ({"passages": [("kb-12", "public"), ("int-3", "internal")]}, "non-public"),
    ({"passages": []}, "non-public or no"),
    ({"question": "How do I rotate an API key in v2.3?"}, "names a version"),
    ({"question": "How do I rotate an API key in 4.1.0?"}, "names a version"),
    ({"answer": "Ask sarah@acme.com to rotate it [kb-12]."}, "personal data"),
])
def test_only_answers_from_public_documentation_alone_are_cached(answers, change, reason):
    fields = {"question": QUESTION, "answer": ANSWER, "passages": PUBLIC, "tools_called": (), **change}
    got = answers.put("t_us", fields["question"], fields["answer"], "7", "kb-v41", fields["passages"],
                      fields["tools_called"])
    assert reason in got
    assert psql(DB, "SELECT count(*) FROM answer_cache") == [["0"]]


@pytest.mark.parametrize("jev, reason", [(Jev(p_public=0.79), "account data"),
                                         (Jev(p_public=0.1), "account data"),
                                         (Jev(down=True), "could not be decided")])
def test_jev_decides_eligibility_and_an_unsure_or_missing_answer_caches_nothing(database, jev, reason):
    psql(DB, "DELETE FROM answer_cache")
    got = AnswerCache(connect, DecisionEngine(jev)).put("t_us", QUESTION, ANSWER, "7", "kb-v41", PUBLIC)
    assert reason in got and psql(DB, "SELECT count(*) FROM answer_cache") == [["0"]]


def test_jev_sees_the_question_and_the_answer():
    jev = Jev()
    AnswerCache(None, DecisionEngine(jev)).eligible(QUESTION, ANSWER, PUBLIC, ())
    assert jev.seen == [{"question": QUESTION, "answer": ANSWER}]


def test_a_version_volatile_question_is_never_served_from_the_cache(answers):
    volatile = "How do I rotate an API key on v7.1?"
    psql(DB, f"INSERT INTO answer_cache (tenant_id, key, answer, doc_ids, expires_at) VALUES ('t_us', "
             f"'{key('t_us', volatile, '7', 'kb-v41')}', 'Old steps', '{{kb-12}}', now() + interval '1 day')")
    assert answers.get("t_us", volatile, "7", "kb-v41") is None                     # even if an entry exists


def test_entries_expire_after_seven_days(answers):
    answers.put("t_us", QUESTION, ANSWER, "7", "kb-v41", PUBLIC)
    days = psql(DB, "SELECT extract(epoch FROM expires_at - created_at)::int / 86400 FROM answer_cache")
    assert days == [["7"]]
    psql(DB, "UPDATE answer_cache SET expires_at = now() - interval '1 second'")
    assert answers.get("t_us", QUESTION, "7", "kb-v41") is None
    assert answers.prune("t_us") == 1


def test_a_deleted_document_evicts_every_answer_that_cited_it(answers):
    answers.put("t_us", QUESTION, ANSWER, "7", "kb-v41", PUBLIC)
    answers.put("t_us", "Where are API keys?", "Under Settings [kb-9].", "7", "kb-v41", [("kb-9", "public")])
    assert answers.evict_document("t_us", "kb-12") == 1
    assert answers.get("t_us", QUESTION, "7", "kb-v41") is None
    assert answers.get("t_us", "Where are API keys?", "7", "kb-v41") == "Under Settings [kb-9]."
    assert answers.evict_document("t_eu", "kb-9") == 0                              # not another tenant's


def test_a_cache_hit_passes_the_output_checks_again(answers):
    stale = "Rotate it with sk_live_4eC39HqLyjWDarjtT1zdp7dc [kb-12]."
    psql(DB, f"INSERT INTO answer_cache (tenant_id, key, answer, doc_ids, expires_at) VALUES ('t_us', "
             f"'{key('t_us', QUESTION, '7', 'kb-v41')}', '{stale}', '{{kb-12}}', now() + interval '1 day')")
    assert answers.get("t_us", QUESTION, "7", "kb-v41") is None
    linked = "See http://intranet.example.net/keys [kb-12]."
    psql(DB, f"UPDATE answer_cache SET answer = '{linked}'")
    assert answers.get("t_us", QUESTION, "7", "kb-v41") == "See [link removed] [kb-12]."


def test_the_cache_is_isolated_by_row_level_security_too(answers):
    answers.put("t_us", QUESTION, ANSWER, "7", "kb-v41", PUBLIC)
    with connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', 't_eu', true)")
        assert conn.execute("SELECT count(*) FROM answer_cache").fetchone()[0] == 0


# Budgets ----------------------------------------------------------------------------------------------------

PRICES = Prices("2026-10", {"claude-sonnet": (Decimal("3"), Decimal("15")),
                            "groq-llama": (Decimal("0.05"), Decimal("0.08"))})
OCTOBER = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def ledger(database):
    psql(DB, "DELETE FROM usage_ledger; DELETE FROM tenant_budgets;"
             "INSERT INTO tenant_budgets (tenant_id, monthly_usd) VALUES ('t_us', 100.00), ('t_eu', 50.00)")
    notices = []
    return Ledger(connect, PRICES, lambda tenant, text: notices.append((tenant, text))), notices


def spend(ledger, tenant, usd, model="claude-sonnet", route="faq"):
    """Record completion tokens worth `usd` at the model's output price."""
    tokens = math.ceil(Decimal(usd) / PRICES.per_million[model][1] * 1_000_000)  # at least usd
    ledger.record(tenant, model, route, {"prompt_tokens": 0, "completion_tokens": tokens}, OCTOBER)


def test_cost_is_exact_tokens_times_the_versioned_price_table(ledger):
    led, _ = ledger
    led.record("t_us", "claude-sonnet", "faq", {"prompt_tokens": 1_000_000, "completion_tokens": 100_000},
               OCTOBER)
    led.record("t_us", "claude-sonnet", "faq", {"prompt_tokens": 500_000, "completion_tokens": 0}, OCTOBER)
    led.record("t_us", "groq-llama", "diagnostic", {"prompt_tokens": 2_000_000, "completion_tokens": 0},
               OCTOBER)
    report = led.report("t_us", "2026-10")
    assert report["price_table"] == "2026-10"
    lines = [(ln["model"], ln["route"], ln["prompt_tokens"], ln["cost_usd"]) for ln in report["lines"]]
    assert lines == [("claude-sonnet", "faq", 1_500_000, Decimal("6")),
                     ("groq-llama", "diagnostic", 2_000_000, Decimal("0.1"))]
    assert report["total_usd"] == Decimal("6.1") and report["used"] == Decimal("0.061")
    assert led.report("t_eu", "2026-10")["lines"] == []                   # tenants see only their own


@pytest.mark.parametrize("usage", [{"prompt_tokens": 10}, {"prompt_tokens": -1, "completion_tokens": 0},
                                   {"prompt_tokens": 1.5, "completion_tokens": 0}])
def test_only_exact_provider_usage_of_a_priced_model_is_recorded(ledger, usage):
    led, _ = ledger
    with pytest.raises(ValueError):
        led.record("t_us", "claude-sonnet", "faq", usage, OCTOBER)
    with pytest.raises(ValueError, match="no price"):
        led.record("t_us", "gpt-unknown", "faq", {"prompt_tokens": 1, "completion_tokens": 1}, OCTOBER)
    assert psql(DB, "SELECT count(*) FROM usage_ledger") == [["0"]]


def test_a_month_of_spend_warns_at_80_percent_once_then_soft_caps_at_100(ledger):
    led, notices = ledger
    spend(led, "t_us", 79)
    assert led.band("t_us", OCTOBER) is Band.NOMINAL
    spend(led, "t_us", 1)
    assert led.band("t_us", OCTOBER) is Band.WARNING and led.band("t_us", OCTOBER) is Band.WARNING
    assert notices == [("t_us", "Your organization has used 80% of its monthly budget.")]   # once a month
    spend(led, "t_us", 20)
    assert led.band("t_us", OCTOBER) is Band.SOFT_CAP
    assert "basic knowledge support" in SOFT_CAP_NOTICE
    november = datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert led.band("t_us", november) is Band.NOMINAL                               # a new month
    assert led.band("t_free", OCTOBER) is Band.NOMINAL                              # no budget set


def test_each_tenant_has_its_own_budget(ledger):
    led, _ = ledger
    spend(led, "t_us", 60)
    spend(led, "t_eu", 60)
    assert (led.band("t_us", OCTOBER), led.band("t_eu", OCTOBER)) == (Band.NOMINAL, Band.SOFT_CAP)


def test_concurrent_records_lose_nothing(ledger):
    import threading
    led, _ = ledger
    threads = [threading.Thread(target=led.record, args=("t_us", "groq-llama", "faq",
                                                          {"prompt_tokens": 1000, "completion_tokens": 10},
                                                          OCTOBER)) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    (line,) = led.report("t_us", "2026-10")["lines"]
    assert (line["prompt_tokens"], line["completion_tokens"]) == (20_000, 200)


def test_the_runtime_cannot_raise_its_own_budget_or_rewrite_usage(ledger):
    with connect() as conn:
        for statement in ("UPDATE tenant_budgets SET monthly_usd = 1000000", "DELETE FROM usage_ledger",
                          "UPDATE usage_ledger SET model = 'groq-llama'"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute("SET LOCAL ROLE app_runtime")
                conn.execute("SELECT set_config('app.current_tenant_id', 't_us', true)")
                conn.execute(statement)
    with pytest.raises(PsqlError):
        psql(DB, "INSERT INTO tenant_budgets (tenant_id, monthly_usd) VALUES ('t_free', 0)")


def test_reconciliation_flags_models_more_than_two_percent_off_the_invoices(ledger):
    led, _ = ledger
    spend(led, "t_us", 60)
    spend(led, "t_eu", 40)
    spend(led, "t_us", 10, model="groq-llama")
    flagged = led.reconcile(["t_us", "t_eu"], "2026-10",
                            {"claude-sonnet": Decimal("101.5"), "groq-llama": Decimal("9.0"), "bedrock": 3})
    assert set(flagged) == {"groq-llama", "bedrock"}                                 # 1.5% off is fine
    assert flagged["bedrock"][0] == Decimal(0)


def test_the_release_gate_holds_cost_per_resolved_conversation():
    previous, baseline = {"faq": 0.010, "diagnostic": 0.050}, {"faq": 0.008, "diagnostic": 0.040}
    assert release_gate({"faq": 0.011, "diagnostic": 0.055}, previous, baseline) == []
    violations = release_gate({"faq": 0.0111, "diagnostic": 0.061}, previous, baseline)
    assert violations == ["faq: 0.0111 is more than 10% over the previous release",
                          "diagnostic: 0.061 is more than 10% over the previous release",
                          "diagnostic: 0.061 is more than 1.5x the baseline"]
    assert release_gate({"faq": 0.0121}, {"faq": 0.0115}, {"faq": 0.008}) == [
        "faq: 0.0121 is more than 1.5x the baseline"]
    assert release_gate({"multi_specialist": 0.2}, previous, baseline) == [
        "multi_specialist: no previous release or baseline to compare with"]
