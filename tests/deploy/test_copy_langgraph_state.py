"""LG-05.2: the one-off copy of LangGraph checkpoints into case_state, and the drop of LangGraph's tables.
Needs langgraph-checkpoint-postgres (no longer a project dependency): skipped where it is not installed."""

import importlib.util
import subprocess
from pathlib import Path

import psycopg
import pytest

langgraph_postgres = pytest.importorskip("langgraph.checkpoint.postgres")
from langgraph.graph import END, START, StateGraph  # noqa: E402

from core.orchestrator import case_state  # noqa: E402
from core.orchestrator.case_state import PostgresStore  # noqa: E402
from core.orchestrator.statechart import build, thread  # noqa: E402
from data.migrate import migrate, psql  # noqa: E402
from schemas.thread_state import ThreadState  # noqa: E402
from tests.orchestrator.test_statechart import SOP, Hooks  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = "test_copy_langgraph_state"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
SCRIPT = ROOT / "scripts" / "copy_langgraph_state.py"
spec = importlib.util.spec_from_file_location("copy_langgraph_state", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)
WAITING = {"schema_version": 1, "tenant_id": "t_us", "session_id": "s1", "stage": "AWAITING_CUSTOMER",
           "path": ["INGESTED", "TRIAGED", "AWAITING_CUSTOMER"],
           "messages": [{"role": "user", "content": "It is broken"}],
           "event": {"type": "USER_MESSAGE", "text": "It is broken"}}


def checkpointed(saver, case_id, values):
    """A case as the LangGraph statechart left it: a state written by a node on the case's thread."""
    graph = StateGraph(ThreadState)
    graph.add_node("wait", lambda state: values)
    graph.add_edge(START, "wait")
    graph.add_edge("wait", END)
    graph.compile(checkpointer=saver).invoke({"case_id": case_id}, thread("t_us", case_id))


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example", "up",
                    "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    case_state.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")
    with langgraph_postgres.PostgresSaver.from_conn_string(DSN) as saver:
        saver.setup()
        checkpointed(saver, "waiting", WAITING)
        checkpointed(saver, "answered-since", {**WAITING, "stage": "RESOLVED"})
    store = PostgresStore(lambda: psycopg.connect(DSN, autocommit=True))
    store.save("t_us", "answered-since", {"stage": "TRIAGED", "path": ["INGESTED", "TRIAGED"]}, 0)  # new code
    return store


def test_the_latest_checkpoint_of_each_case_is_copied_and_newer_case_state_is_kept(database):
    assert script.copy(DSN) == {"copied": 1, "kept": 1}
    copied, version = database.load("t_us", "waiting")
    assert version == 1 and {k: copied[k] for k in WAITING} == WAITING and copied["case_id"] == "waiting"
    assert not {k for k in copied if k not in ThreadState.__annotations__}       # no LangGraph channels
    assert database.load("t_us", "answered-since")[0]["stage"] == "TRIAGED"
    assert script.copy(DSN) == {"copied": 0, "kept": 2}                     # running it again is harmless


def test_a_copied_case_carries_on_in_the_new_statechart(database):
    script.copy(DSN)
    hooks = Hooks(triage=SOP)
    state = build(hooks, database).invoke({"event": {"type": "USER_MESSAGE", "text": "Invoice INV-7"}},
                                         thread("t_us", "waiting"))
    assert state["stage"] == "RESOLVED" and state["path"][:3] == WAITING["path"]
    assert [m["content"] for m in state["messages"]] == ["It is broken", "Invoice INV-7"]


def test_drop_removes_langgraphs_tables_only(database):
    script.drop(DSN)
    left = {row[0] for row in psql(DB, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert not set(script.TABLES) & left and "case_state" in left
