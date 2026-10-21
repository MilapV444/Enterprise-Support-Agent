"""M2-01: verbatim window, rolling summary, pins that survive compaction and can be withdrawn, and Jev linking
a new conversation to the right case (FR-15). Runs against the compose Postgres; Jev is scripted."""

import subprocess
import uuid
from pathlib import Path

import psycopg
import pytest

from channels import sessions
from core.orchestrator.decisions import NUMBERS, Answer, DecisionEngine, JevUnavailable
from data.migrate import migrate, psql
from memory.conversation import dialogue
from memory.conversation.cases import NEW_CASE, confirm, link, open_cases
from memory.conversation.dialogue import MAX_PINS, VERBATIM, Dialogue, StaleTurn

ROOT = Path(__file__).resolve().parents[3]
DB = "test_conversation_memory"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
CONSTRAINT = "do not reboot production during business hours"


class ScriptedJev:
    """Answers by rule: rules(question_id, question, state) -> Answer, or raises JevUnavailable."""

    def __init__(self, rules):
        self.rules, self.seen = rules, []

    def evaluate(self, state, questions):
        self.seen.append((state, questions))
        return {qid: self.rules(qid, question, state) for qid, question in questions.items()}


def jev(constraint=0.95, withdraws=0.05, case=None):
    """Pinning, revocation and case answers; a value of None means Jev is down for that question."""
    def rules(qid, question, state):
        if qid == "case":
            if case is None:
                raise JevUnavailable("down")
            return Answer(*case)
        p = constraint if "constraint" not in state else withdraws
        if p is None:
            raise JevUnavailable("down")
        return Answer(p >= 0.5, max(p, 1 - p))
    return ScriptedJev(rules)


def summarizer(reply=None):
    calls = []

    def summarize(previous, turns, pins):
        calls.append((previous, turns, pins))
        return reply or (previous + " " + " / ".join(t["content"][:20] for t in turns)).strip()
    summarize.calls = calls
    return summarize


@pytest.fixture(scope="module")
def conn():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    sessions.apply_schema(DB)
    dialogue.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU')")
    with psycopg.connect(DSN, autocommit=True) as connection:
        yield connection


def conversation(conn, principal="sarah", tenant="t_us"):
    session = sessions.start(conn, tenant, principal, "T2_SSO")
    conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
    assert sessions.open_conversation(conn, tenant, principal, session, conversation_id)
    return conversation_id


def talk(memory, conversation_id, messages, tenant="t_us", start=1):
    for seq, text in enumerate(messages, start):
        memory.append(tenant, conversation_id, seq, "user" if seq % 2 else "assistant", text)


def test_schema_is_applied_once_through_the_ledger(conn):
    dialogue.apply_schema(DB)
    ledger = f"SELECT count(*) FROM schema_migrations WHERE name = '{dialogue.SCHEMA_NAME}'"
    assert psql(DB, ledger) == [["1"]]


def test_old_turns_fold_into_the_summary_and_the_last_n_stay_verbatim(conn):
    memory, summarize = Dialogue(conn, DecisionEngine(jev()), summarizer()), summarizer()
    memory.summarize = summarize
    conv = conversation(conn)
    talk(memory, conv, [f"message {chr(97 + i)}" for i in range(12)])
    assert memory.compact("t_us", conv) and not memory.compact("t_us", conv)  # nothing more to fold
    buffer = memory.buffer("t_us", conv)
    assert [t["seq"] for t in buffer.turns] == list(range(12 - VERBATIM + 1, 13))
    assert [t["content"] for t in summarize.calls[0][1]] == [f"message {c}" for c in "abcd"]
    assert buffer.summary.startswith("message a")
    talk(memory, conv, ["message m", "message n"], start=13)
    assert memory.compact("t_us", conv)
    assert summarize.calls[1][0] == buffer.summary  # recursive: the new summary builds on the old one
    assert len(memory.buffer("t_us", conv).turns) == VERBATIM


def test_pins_survive_compaction_and_reach_the_assembler(conn):
    summarize = summarizer()
    memory = Dialogue(conn, DecisionEngine(jev()), summarize)
    conv = conversation(conn)
    first = memory.append("t_us", conv, 1, "user", f"Please {CONSTRAINT}. Ticket INC-20931 is ours.")
    assert first.pinned == ["INC-20931", CONSTRAINT]
    talk(memory, conv, [f"later turn {chr(97 + i)}" for i in range(20)], start=2)
    assert memory.compact("t_us", conv)
    buffer = memory.buffer("t_us", conv)
    assert [p["content"] for p in buffer.pins] == ["INC-20931", CONSTRAINT]
    assert all(CONSTRAINT not in t["content"] for t in buffer.turns)  # its turn is long gone from the window
    assert summarize.calls[0][2] == ["INC-20931", CONSTRAINT]  # the summarizer is told what not to alter
    context = buffer.for_assembler()
    assert context["pins"] == [{"text": "INC-20931", "importance": 1}, {"text": CONSTRAINT, "importance": 2}]
    assert context["summary"] == buffer.summary and len(context["turns"]) == VERBATIM


@pytest.mark.parametrize("constraint, pinned", [(0.95, True), (0.3, False), (None, True)])
def test_negations_are_pinned_when_jev_says_constraint_or_cannot_answer(conn, constraint, pinned):
    memory = Dialogue(conn, DecisionEngine(jev(constraint=constraint)), summarizer())
    conv = conversation(conn)
    result = memory.append("t_us", conv, 1, "user", f"I {CONSTRAINT}")
    assert (result.pinned == [CONSTRAINT]) is pinned


def test_plain_messages_and_agent_turns_pin_nothing(conn):
    engine = jev()
    memory = Dialogue(conn, DecisionEngine(engine), summarizer())
    conv = conversation(conn)
    assert memory.append("t_us", conv, 1, "user", "The dashboard is slow today").pinned == []
    assert memory.append("t_us", conv, 2, "assistant", f"I will {CONSTRAINT}, INC-20931").pinned == []
    assert engine.seen == []


@pytest.mark.parametrize("withdraws, revoked", [(0.9, True), (0.6, False), (None, False)])
def test_a_withdrawn_constraint_is_unpinned_with_its_reason(conn, withdraws, revoked):
    memory = Dialogue(conn, DecisionEngine(jev(withdraws=withdraws)), summarizer())
    conv = conversation(conn)
    memory.append("t_us", conv, 1, "user", f"Please {CONSTRAINT}")
    result = memory.append("t_us", conv, 3, "user", "Actually, go ahead and restart the node now")
    assert (result.revoked == [CONSTRAINT]) is revoked
    assert (CONSTRAINT in [p["content"] for p in memory.buffer("t_us", conv).pins]) is not revoked
    if revoked:
        rows = psql(DB, f"SELECT status, revoked_by_seq FROM dialogue_pins WHERE conversation_id = '{conv}'")
        assert rows == [["revoked", "3"]]


def test_a_summary_that_changes_a_figure_is_refused(conn):
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer("Customer disputes a $12,400 charge."))
    conv = conversation(conn)
    talk(memory, conv, ["I was charged $1,240 twice"] + [f"turn {chr(97 + i)}" for i in range(VERBATIM)])
    assert not memory.compact("t_us", conv)
    buffer = memory.buffer("t_us", conv)
    assert buffer.summary == "" and buffer.turns[0]["content"] == "I was charged $1,240 twice"
    memory.summarize = summarizer("Customer disputes a $1,240 charge.")
    assert memory.compact("t_us", conv)


def test_a_second_writer_with_the_same_sequence_number_is_stale(conn):
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer())
    conv = conversation(conn)
    memory.append("t_us", conv, 1, "user", "first tab")
    with pytest.raises(StaleTurn):
        memory.append("t_us", conv, 1, "user", "second tab")
    assert [t["content"] for t in memory.buffer("t_us", conv).turns] == ["first tab"]


def test_pinning_stops_at_the_ceiling_and_reports_it(conn):
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer())
    conv = conversation(conn)
    flood = " ".join(f"ABC-{1000 + i}" for i in range(MAX_PINS + 5))
    result = memory.append("t_us", conv, 1, "user", flood)
    assert len(result.pinned) == MAX_PINS and result.pin_overflow
    assert len(memory.buffer("t_us", conv).pins) == MAX_PINS


def test_memory_is_tenant_scoped(conn):
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer())
    conv = conversation(conn)
    memory.append("t_us", conv, 1, "user", f"Please {CONSTRAINT}")
    other = memory.buffer("t_eu", conv)
    assert other.turns == [] and other.pins == []


def test_a_follow_up_conversation_links_to_the_right_case_and_keeps_its_pins(conn):
    """The M2-01 scenario: two conversations on one case, a day apart."""
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer())
    billing, outage = conversation(conn, "dana"), conversation(conn, "dana")
    first = link(conn, DecisionEngine(jev()), "t_us", "dana", billing, "Invoice INV-9821 charged twice")
    assert first.is_new and not first.needs_confirmation  # no open case yet: no Jev call needed
    memory.append("t_us", billing, 1, "user", "Invoice INV-9821 charged twice, do not cancel my plan")
    new_issue = DecisionEngine(jev(case=(NEW_CASE, 0.95)))
    assert link(conn, new_issue, "t_us", "dana", outage, "API is down").is_new
    memory.append("t_us", outage, 1, "user", "API is down")

    follow_up = conversation(conn, "dana")
    engine = jev(case=(first.case_id, 0.95))
    linked = link(conn, DecisionEngine(engine), "t_us", "dana", follow_up, "Any news on the double charge?")
    assert linked.case_id == first.case_id and not linked.is_new and not linked.needs_confirmation
    _, questions = engine.seen[0]
    options = questions["case"]["criteria"]
    assert set(options) == {first.case_id, *open_cases(conn, "t_us", "dana", follow_up)} | {NEW_CASE}
    assert not any(NUMBERS.search(text) for text in options.values())  # numbers stay out of Jev questions
    pins = [p["content"] for p in memory.buffer("t_us", follow_up).pins]
    assert pins == ["INV-9821", "do not cancel my plan"]  # the case's pins carry into the new conversation


def test_a_middling_match_asks_the_customer_and_binds_their_answer(conn):
    memory = Dialogue(conn, DecisionEngine(jev()), summarizer())
    old = conversation(conn, "erin")
    case_id = link(conn, DecisionEngine(jev()), "t_us", "erin", old, "x").case_id
    memory.append("t_us", old, 1, "user", "Refund for INV-4410 please")
    new = conversation(conn, "erin")
    asked = link(conn, DecisionEngine(jev(case=(case_id, 0.7))), "t_us", "erin", new, "about my refund")
    assert asked.needs_confirmation and asked.case_id == case_id and "INV-4410" in asked.prompt
    assert psql(DB, f"SELECT case_id IS NULL FROM conversations WHERE id = '{new}'") == [["t"]]  # not yet
    assert confirm(conn, "t_us", "erin", new, case_id) == case_id


@pytest.mark.parametrize("answer", [(NEW_CASE, 0.95), ("CASE", 0.4)])
def test_a_new_issue_or_a_weak_match_opens_a_new_case(conn, answer):
    old = conversation(conn, "finn")
    case_id = link(conn, DecisionEngine(jev()), "t_us", "finn", old, "x").case_id
    Dialogue(conn, DecisionEngine(jev()), summarizer()).append("t_us", old, 1, "user", "Printer jam")
    new = conversation(conn, "finn")
    choice = case_id if answer[0] == "CASE" else answer[0]
    linked = link(conn, DecisionEngine(jev(case=(choice, answer[1]))), "t_us", "finn", new, "SSO broken")
    assert linked.is_new and linked.case_id != case_id and not linked.needs_confirmation


def test_jev_down_asks_the_customer(conn):
    old = conversation(conn, "gail")
    case_id = link(conn, DecisionEngine(jev()), "t_us", "gail", old, "x").case_id
    new = conversation(conn, "gail")
    asked = link(conn, DecisionEngine(jev(case=None)), "t_us", "gail", new, "hello again")
    assert asked.needs_confirmation and asked.case_id == case_id


def test_only_the_principals_own_open_cases_are_offered_or_accepted(conn):
    mine, theirs, done = conversation(conn, "hana"), conversation(conn, "ivan"), conversation(conn, "hana")
    my_case = link(conn, DecisionEngine(jev()), "t_us", "hana", mine, "x").case_id
    their_case = link(conn, DecisionEngine(jev()), "t_us", "ivan", theirs, "x").case_id
    done_case = link(conn, DecisionEngine(jev(case=(NEW_CASE, 0.95))), "t_us", "hana", done, "x").case_id
    psql(DB, f"UPDATE cases SET status = 'resolved' WHERE id = '{done_case}'")
    new = conversation(conn, "hana")
    assert set(open_cases(conn, "t_us", "hana", new)) == {my_case}
    with pytest.raises(LookupError):
        confirm(conn, "t_us", "hana", new, their_case)
    with pytest.raises(LookupError):
        confirm(conn, "t_us", "hana", new, done_case)
