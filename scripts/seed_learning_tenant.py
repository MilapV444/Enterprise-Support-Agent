"""Insert the learning-profile demo tenant (id t_us). Safe to re-run."""

import os
from pathlib import Path

import psycopg

root = Path(__file__).resolve().parents[1]
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    os.environ.setdefault(key, value)

url = os.environ["DATABASE_URL"]
with psycopg.connect(url, autocommit=True) as conn:
    conn.execute(
        "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US') "
        "ON CONFLICT (id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us') "
        "ON CONFLICT (tenant_id) DO NOTHING"
    )
    print("seeded t_us")
