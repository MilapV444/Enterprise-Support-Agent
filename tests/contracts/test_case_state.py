"""LG-01: the case state store that replaces the LangGraph checkpointer (FR-18 / MS-D8; DECISION-bc6301b4).
The Postgres store and the in-memory one keep the same contract."""

import subprocess
from pathlib import Path

import psycopg
import pytest

from core.orchestrator import case_state
from core.orchestrator.case_state import MemoryStore, PostgresStore, StaleState
from data.migrate import migrate, psql
from schemas.thread_state import merge

ROOT = Path(__file__).resolve().parents[2]
DB = "test_case_state"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    case_state.apply_schema(DB)
    case_state.apply_schema(DB)  # a second apply is a no-op
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_a', 'Acme', 'US'), ('t_b', 'Globex', 'EU')")


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return MemoryStore()
    request.getfixturevalue("database")
    psql(DB, "DELETE FROM case_state")
    return PostgresStore(connect)


STATE = {"schema_version": 1, "tenant_id": "t_a", "case_id": "c1", "stage": "TRIAGED", "path": ["INGESTED"],
         "triage": {"intent": "BILLING_INQUIRY", "confidence": 0.9}, "waiting_since": None}


def test_a_new_case_has_no_state(store):
    assert store.load("t_a", "c1") == ({}, 0)


def test_a_saved_state_loads_back_with_the_next_version(store):
    assert store.save("t_a", "c1", STATE, 0) == 1
    assert store.load("t_a", "c1") == (STATE, 1)
    assert store.save("t_a", "c1", {**STATE, "stage": "RESOLVED"}, 1) == 2
    assert store.load("t_a", "c1") == ({**STATE, "stage": "RESOLVED"}, 2)


@pytest.mark.parametrize("loaded", [0, 1, 3])
def test_a_save_from_a_stale_version_is_refused(store, loaded):
    store.save("t_a", "c1", STATE, 0)
    store.save("t_a", "c1", STATE, 1)                       # another run saved version 2
    with pytest.raises(StaleState):
        store.save("t_a", "c1", {**STATE, "stage": "X"}, loaded)
    assert store.load("t_a", "c1") == (STATE, 2)


def test_cases_are_kept_apart_per_tenant(store):
    store.save("t_a", "c1", STATE, 0)
    assert store.load("t_b", "c1") == ({}, 0)
    assert store.save("t_b", "c1", {**STATE, "tenant_id": "t_b"}, 0) == 1
    assert store.load("t_a", "c1") == (STATE, 1)


def test_row_level_security_hides_other_tenants_rows(database):
    store = PostgresStore(connect)
    psql(DB, "DELETE FROM case_state")
    store.save("t_a", "c1", STATE, 0)
    store.save("t_b", "c2", STATE, 0)
    with connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', 't_b', true)")
        assert conn.execute("SELECT tenant_id, case_id FROM case_state").fetchall() == [("t_b", "c2")]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM case_state")


def test_merge_extends_the_append_fields_and_replaces_the_rest():
    state = {"path": ["INGESTED"], "messages": [{"role": "user", "content": "hi"}], "stage": "INGESTED"}
    merged = merge(state, {"path": ["TRIAGED"], "messages": [], "trajectory": [{"step": 1}],
                           "stage": "TRIAGED", "error": None})
    assert merged == {"path": ["INGESTED", "TRIAGED"], "messages": [{"role": "user", "content": "hi"}],
                      "trajectory": [{"step": 1}], "stage": "TRIAGED", "error": None}
    assert state["path"] == ["INGESTED"]                    # the loaded state is not changed in place
