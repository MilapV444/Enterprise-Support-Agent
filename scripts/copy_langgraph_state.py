"""One-off cut-over (LG-05.2, DECISION-bc6301b4): each case's latest LangGraph checkpoint into case_state.

    python scripts/copy_langgraph_state.py         copy; changes no LangGraph table
    python scripts/copy_langgraph_state.py --drop  then drop checkpoints, checkpoint_blobs, checkpoint_writes
                                                   and checkpoint_migrations (after checking the copy)

DATABASE_URL is the owner login (the LangGraph tables are its own). Rows are written through
core.orchestrator.case_state.PostgresStore (app_runtime, tenant RLS) and only where a case has no case_state
row yet: a case the new code has already answered keeps its state. Thread ids are "<tenant>:<case>". A run
that was interrupted mid-graph is copied as it stood, with no node pending: its next message starts a new run.

Needs langgraph-checkpoint-postgres, which the project no longer declares: run it from an environment that
still has it installed.
"""

import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.orchestrator.case_state import PostgresStore, StaleState  # noqa: E402
from schemas.thread_state import ThreadState  # noqa: E402

TABLES = ["checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"]
FIELDS = set(ThreadState.__annotations__)  # LangGraph also keeps internal channels; only state fields move


def copy(dsn):
    """Returns {"copied": n, "kept": n}: cases written, and cases that already had a case_state row."""
    from langgraph.checkpoint.postgres import PostgresSaver

    store, report = PostgresStore(lambda: psycopg.connect(dsn, autocommit=True)), {"copied": 0, "kept": 0}
    with PostgresSaver.from_conn_string(dsn) as saver, psycopg.connect(dsn, autocommit=True) as conn:
        threads = [row[0] for row in conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns = '' ORDER BY thread_id")]
        for thread_id in threads:
            tenant_id, case_id = thread_id.split(":", 1)
            values = saver.get_tuple({"configurable": {"thread_id": thread_id}}).checkpoint["channel_values"]
            try:
                store.save(tenant_id, case_id, {k: v for k, v in values.items() if k in FIELDS}, 0)
                report["copied"] += 1
            except StaleState:
                report["kept"] += 1
    return report


def drop(dsn):
    with psycopg.connect(dsn, autocommit=True) as conn, conn.transaction():
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dsn = os.environ["DATABASE_URL"]
    print(copy(dsn))
    if "--drop" in argv:
        drop(dsn)
        print("dropped", ", ".join(TABLES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
