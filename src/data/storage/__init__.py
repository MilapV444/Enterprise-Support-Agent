"""Object storage (Cloudflare R2 or a local directory) and versioned raw snapshots (NFR-4, DP-ADP-04)."""

from data.storage.objects import LocalStore, ObjectExists, R2Store, r2_store_from_secrets
from data.storage.snapshots import latest_snapshot, read_snapshot, write_snapshot

__all__ = ["LocalStore", "ObjectExists", "R2Store", "latest_snapshot", "r2_store_from_secrets",
           "read_snapshot", "write_snapshot"]
