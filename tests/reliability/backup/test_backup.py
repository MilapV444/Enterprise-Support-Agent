"""M4-03: daily dumps to object storage, the erasure log, and the restore drill: restore the latest dumps into
restore copies, check them against their manifests, and replay every erasure made since the dump (NFR-19).

Runs against the compose Postgres (main, vault, keys), OpenBao and Temporal, with the erasure suite's seeding;
a local object store stands in for R2 (same put / get / keys / delete, write-once)."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data.keys import KeyStore, OpenBaoTransit
from data.migrate import psql
from data.storage import LocalStore
from data.storage.objects import ObjectExists
from memory.lifecycle.inventory import ErasureActivities
from tests.erasure.test_erasure import (
    DSN,
    KEYS,
    MAIN,
    SIGNING_KEY,
    VAULT,
    connect,
    erase,
    seed,
    stack,  # noqa: F401  (the compose stack fixture)
)

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("pgbackup", ROOT / "deploy" / "backup" / "pgbackup.py")
pgbackup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pgbackup)

DATABASES = ((MAIN, "main"), (VAULT, "vault"), (KEYS, "keys"))
NOW = datetime(2026, 10, 27, 2, 30, tzinfo=timezone.utc)


def restored_activities(services):
    def build(names):
        def keys():
            return KeyStore(connect(names["keys"]), OpenBaoTransit(services["bao"]))
        return ErasureActivities(DSN.format(names["main"]), DSN.format(names["vault"]), keys, None,
                                 SIGNING_KEY)
    return build


def user_rows(database, principal):
    sql = (f"SELECT (SELECT count(*) FROM conversations WHERE principal_id = '{principal}') "
           f"+ (SELECT count(*) FROM user_facts WHERE principal_id = '{principal}')")
    return int(psql(database, sql)[0][0])


def key_rows(database, principal):
    return int(psql(database, f"SELECT count(*) FROM user_keys WHERE user_id = '{principal}'")[0][0])


@pytest.fixture(scope="module")
def drilled(stack, tmp_path_factory):  # noqa: F811
    """Two users, a dump of all three databases, then one user erased in production and logged."""
    store = LocalStore(tmp_path_factory.mktemp("r2"))
    seed(stack, "dana")
    seed(stack, "kept")
    keys = {database: pgbackup.dump(store, database, NOW) for database, _ in DATABASES}
    erase(stack, "dana")
    pgbackup.log_erasure(store, "t_us", "dana", "job-dana", NOW + timedelta(hours=3))
    assert user_rows(MAIN, "dana") == 0 and key_rows(KEYS, "dana") == 0           # gone in production
    report = pgbackup.drill(store, restored_activities(stack), DATABASES, keep=True)  # kept to inspect
    return store, keys, report


def test_a_dump_is_stored_write_once_with_its_manifest(drilled):
    store, keys, _ = drilled
    assert keys[MAIN] == f"backups/{MAIN}/20261027T023000Z.dump"
    manifest = pgbackup.manifest(store, keys[MAIN])
    assert manifest["sha256"] and manifest["size"] == len(store.get(keys[MAIN]))
    assert "conversations" in manifest["counts"] and manifest["migrations"]
    with pytest.raises(ObjectExists):
        pgbackup.dump(store, MAIN, NOW)                                          # never overwritten
    assert pgbackup.latest(store, MAIN) == keys[MAIN]


def test_the_drill_restores_every_database_and_matches_the_manifests(drilled):
    _, keys, report = drilled
    assert report.ok, (report.mismatches, report.residue)
    assert report.restored == {db: (keys[db], f"restore_{db}") for db, _ in DATABASES}
    assert user_rows(f"restore_{MAIN}", "kept") > 0                              # the data came back


def test_a_user_erased_after_the_dump_is_erased_again_in_the_restored_copy(drilled):
    _, _, report = drilled
    assert report.erasures_replayed == 1 and report.residue == {}
    assert user_rows(f"restore_{MAIN}", "dana") == 0
    assert key_rows(f"restore_{KEYS}", "dana") == 0                              # shredded keys stay shredded
    assert key_rows(f"restore_{KEYS}", "kept") > 0


def test_the_drill_drops_its_copies_of_customer_data_unless_asked_to_keep_them(drilled, stack):  # noqa: F811
    store, _, _ = drilled
    report = pgbackup.drill(store, restored_activities(stack), DATABASES, prefix="standby_")
    assert report.ok and report.erasures_replayed == 1
    copies = [f"standby_{db}" for db, _ in DATABASES]
    names = "', '".join(copies)
    assert psql("postgres", f"SELECT datname FROM pg_database WHERE datname IN ('{names}')") == []


def test_a_restore_never_targets_a_live_database(drilled):
    store, keys, _ = drilled
    for target in (MAIN, "agent", "postgres", "prod_agent"):
        with pytest.raises(pgbackup.BackupError, match="refusing to restore"):
            pgbackup.restore(store, keys[MAIN], target)


def test_a_dump_that_does_not_match_its_manifest_is_not_restored(drilled, tmp_path):
    store, keys, _ = drilled
    copy = LocalStore(tmp_path)
    copy.put(keys[MAIN], store.get(keys[MAIN])[:-1] + b"x")
    copy.put(keys[MAIN] + ".json", store.get(keys[MAIN] + ".json"))
    with pytest.raises(pgbackup.BackupError, match="does not match its manifest"):
        pgbackup.restore(copy, keys[MAIN], "restore_tampered")


def test_the_drill_reports_rows_that_differ_from_the_manifest(drilled, tmp_path):
    store, keys, _ = drilled
    copy = LocalStore(tmp_path)
    for database, _ in DATABASES:
        key = keys[database]
        manifest = pgbackup.manifest(store, key)
        if database == MAIN:
            manifest["counts"]["conversations"] += 1
        copy.put(key, store.get(key))
        copy.put(key + ".json", json.dumps(manifest).encode())
    report = pgbackup.drill(copy, lambda names: pytest.fail("no replay needed"), DATABASES, prefix="standby_")
    assert not report.ok and any("conversations" in m for m in report.mismatches)


def test_an_erasure_is_logged_once_and_only_recent_ones_are_replayed(tmp_path):
    store = LocalStore(tmp_path)
    pgbackup.log_erasure(store, "t_us", "old", "job-old", NOW - timedelta(days=2))
    pgbackup.log_erasure(store, "t_us", "during", "job-during", NOW - timedelta(minutes=30))  # while dumping
    pgbackup.log_erasure(store, "t_us", "after", "job-after", NOW + timedelta(days=1))
    with pytest.raises(ObjectExists):
        pgbackup.log_erasure(store, "t_us", "after", "job-after", NOW + timedelta(days=1))
    assert [e["principal_id"] for e in pgbackup.erasures_since(store, NOW)] == ["during", "after"]


def test_dumps_and_erasure_log_entries_past_35_days_are_pruned_but_the_newest_dump_stays(tmp_path):
    store = LocalStore(tmp_path)
    for days, name in ((40, "a"), (36, "b"), (1, "c")):
        created = NOW - timedelta(days=days)
        key = f"backups/agent/{created.strftime(pgbackup.STAMP)}.dump"
        store.put(key, name.encode())
        store.put(key + ".json", json.dumps({"created_at": created.isoformat()}).encode())
    lonely = NOW - timedelta(days=90)
    key = f"backups/agent_keys/{lonely.strftime(pgbackup.STAMP)}.dump"
    store.put(key, b"k")
    store.put(key + ".json", json.dumps({"created_at": lonely.isoformat()}).encode())
    pgbackup.log_erasure(store, "t_us", "x", "job-x", NOW - timedelta(days=36))
    pgbackup.log_erasure(store, "t_us", "y", "job-y", NOW - timedelta(days=2))
    removed = pgbackup.prune(store, NOW)
    assert len(removed) == 3
    assert [store.get(k) for k in store.keys("backups/agent/") if k.endswith(".dump")] == [b"c"]
    assert store.keys("backups/agent_keys/")                                    # its only dump is kept
    assert [json.loads(store.get(k))["principal_id"] for k in store.keys("erasure-log/")] == ["y"]
