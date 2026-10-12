"""M0-05: write-once object stores (local directory and R2) and versioned raw snapshots (NFR-4, DP-D11)."""

import io
from datetime import date

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from data.storage import (
    LocalStore,
    ObjectExists,
    R2Store,
    latest_snapshot,
    read_snapshot,
    write_snapshot,
)


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


def test_local_store_round_trip_and_listing(store):
    store.put("a/1.txt", b"one")
    store.put("a/2.txt", b"two")
    store.put("b/1.txt", b"three")
    assert store.get("a/2.txt") == b"two"
    assert store.keys("a/") == ["a/1.txt", "a/2.txt"]
    store.delete("a/1.txt")
    assert store.keys("a/") == ["a/2.txt"]
    with pytest.raises(KeyError):
        store.get("a/1.txt")


def test_local_store_never_overwrites(store):
    store.put("k", b"first")
    with pytest.raises(ObjectExists):
        store.put("k", b"second")
    assert store.get("k") == b"first"


@pytest.mark.parametrize("key", ["../escape", "a/../../escape", ""])
def test_local_store_rejects_keys_outside_its_root(store, key):
    with pytest.raises(ValueError, match="invalid key"):
        store.put(key, b"x")


def stubbed_r2():
    client = boto3.client("s3", region_name="auto", endpoint_url="https://account.r2.cloudflarestorage.com",
                          aws_access_key_id="id", aws_secret_access_key="secret")
    return R2Store("bucket", client), Stubber(client)


def test_r2_put_is_conditional_and_maps_conflicts():
    r2, stub = stubbed_r2()
    stub.add_response("put_object", {}, {"Bucket": "bucket", "Key": "k", "Body": b"x", "IfNoneMatch": "*"})
    stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
    with stub:
        r2.put("k", b"x")
        with pytest.raises(ObjectExists):
            r2.put("k", b"x")
    stub.assert_no_pending_responses()


def test_r2_get_list_and_missing_key():
    r2, stub = stubbed_r2()
    stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"data"), 4)},
                      {"Bucket": "bucket", "Key": "k"})
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_response("list_objects_v2", {"Contents": [{"Key": "p/2"}, {"Key": "p/1"}], "IsTruncated": False},
                      {"Bucket": "bucket", "Prefix": "p/"})
    with stub:
        assert r2.get("k") == b"data"
        with pytest.raises(KeyError):
            r2.get("missing")
        assert r2.keys("p/") == ["p/1", "p/2"]


def test_snapshots_add_versions_and_keep_the_old_ones(store):
    day = date(2026, 10, 12)
    v1 = write_snapshot(store, "t_us", day, {"kb/a.md": b"# A", "kb/b.md": b"# B"})
    v2 = write_snapshot(store, "t_us", day, {"kb/a.md": b"# A, edited"})
    assert (v1, v2) == ("snapshots/t_us/2026-10-12/raw_v1.tar.gz", "snapshots/t_us/2026-10-12/raw_v2.tar.gz")
    assert read_snapshot(store, v1) == {"kb/a.md": b"# A", "kb/b.md": b"# B"}
    assert read_snapshot(store, v2) == {"kb/a.md": b"# A, edited"}
    assert latest_snapshot(store, "t_us", day) == v2


def test_snapshots_are_kept_per_tenant(store):
    day = date(2026, 10, 12)
    write_snapshot(store, "t_us", day, {"a": b"us"})
    assert latest_snapshot(store, "t_eu", day) is None
    assert write_snapshot(store, "t_eu", day, {"a": b"eu"}).startswith("snapshots/t_eu/")


def test_snapshot_rejects_tenant_ids_that_would_escape_the_prefix(store):
    with pytest.raises(ValueError, match="invalid tenant id"):
        write_snapshot(store, "t_us/../t_eu", date(2026, 10, 12), {"a": b"x"})
