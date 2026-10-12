"""Versioned raw snapshots of a nightly ingestion batch (DP-D11).

Key: snapshots/<tenant_id>/<batch date>/raw_v<n>.tar.gz. Each write adds the next version and never
replaces an older one, so an index can be rebuilt from exactly what was ingested. gzip (stdlib) stands in
for the ADP's zstd until Python 3.14's compression.zstd is the floor.
"""

import io
import re
import tarfile

from data.keys.envelope import TENANT_ID
from data.storage.objects import ObjectExists

VERSION = re.compile(r"/raw_v(\d+)\.tar\.gz$")


def _prefix(tenant_id, batch_date):
    if not TENANT_ID.match(tenant_id):
        raise ValueError(f"invalid tenant id: {tenant_id!r}")
    return f"snapshots/{tenant_id}/{batch_date.isoformat()}/"


def _versions(store, prefix):
    return sorted(int(m.group(1)) for k in store.keys(prefix) if (m := VERSION.search(k)))


def write_snapshot(store, tenant_id, batch_date, documents):
    """Store {name: bytes} as the next version for the batch date and return its key."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in sorted(documents):
            info = tarfile.TarInfo(name)
            info.size = len(documents[name])
            tar.addfile(info, io.BytesIO(documents[name]))
    prefix = _prefix(tenant_id, batch_date)
    for _ in range(3):  # another writer may take the same version number first
        versions = _versions(store, prefix)
        key = f"{prefix}raw_v{(versions[-1] if versions else 0) + 1}.tar.gz"
        try:
            store.put(key, buffer.getvalue())
            return key
        except ObjectExists:
            continue
    raise ObjectExists(prefix)


def read_snapshot(store, key):
    with tarfile.open(fileobj=io.BytesIO(store.get(key)), mode="r:gz") as tar:
        return {member.name: tar.extractfile(member).read() for member in tar.getmembers() if member.isfile()}


def latest_snapshot(store, tenant_id, batch_date):
    prefix = _prefix(tenant_id, batch_date)
    versions = _versions(store, prefix)
    return f"{prefix}raw_v{versions[-1]}.tar.gz" if versions else None
