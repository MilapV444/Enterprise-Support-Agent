import subprocess
from pathlib import Path

import psycopg
import pytest

from channels import sessions
from channels.api import turns
from channels.identity import otp
from data import events
from data.migrate import migrate, psql

ROOT = Path(__file__).resolve().parents[2]
DB = "test_identity"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example


@pytest.fixture(scope="session", autouse=True)
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (events, turns, sessions, otp):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU')")


def connect():
    return psycopg.connect(DSN, autocommit=True)


def sql(query):
    return psql(DB, query)
