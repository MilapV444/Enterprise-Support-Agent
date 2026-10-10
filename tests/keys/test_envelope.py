"""M0-04: envelope encryption with per-user data keys in the key store, crypto-shredding and secret loading
(FR-44, NFR-30). Runs against the compose OpenBao and Postgres."""

import subprocess
import time
from pathlib import Path

import httpx
import psycopg
import pytest
from cryptography.exceptions import InvalidTag

from core.secrets import MissingSecret, OpenBao, load_secret
from data.keys import KeyShredded, KeyStore, OpenBaoTransit, decrypt_field, encrypt_field
from data.migrate import migrate, psql

ROOT = Path(__file__).resolve().parents[2]
KEYS_DB = "test_keys_envelope"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{KEYS_DB}"  # credentials from .env.example
TOKEN = "change-me"


@pytest.fixture(scope="module")
def bao():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres", "openbao"], cwd=ROOT, check=True, capture_output=True)
    client = OpenBao("http://127.0.0.1:8200", TOKEN)
    for _ in range(30):
        try:
            client.request("GET", "sys/health")
            break
        except httpx.HTTPError:
            time.sleep(1)
    client.enable_transit()
    return client


@pytest.fixture(scope="module")
def store(bao):
    psql("postgres", f'DROP DATABASE IF EXISTS "{KEYS_DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{KEYS_DB}"')
    migrate("keys", KEYS_DB)
    with psycopg.connect(DSN, autocommit=True) as conn:
        yield KeyStore(conn, OpenBaoTransit(bao))


def rows(sql):
    return psql(KEYS_DB, sql)


def test_field_round_trips_and_one_key_serves_all_of_a_users_fields(store):
    blob = encrypt_field(store, "t_us", "u1", "address", b"221B Baker Street")
    assert b"Baker" not in blob
    assert decrypt_field(store, "t_us", "u1", "address", blob) == b"221B Baker Street"
    encrypt_field(store, "t_us", "u1", "phone", b"+44 20 7946 0000")
    assert rows("SELECT count(*) FROM user_keys WHERE user_id = 'u1'") == [["1"]]


def test_key_store_holds_only_the_wrapped_key(store):
    _, key = store.current_key("t_us", "u1")
    wrapped = rows("SELECT encode(wrapped_dek, 'escape') FROM user_keys WHERE user_id = 'u1'")[0][0]
    assert wrapped.startswith("vault:v1:") and key.hex() not in wrapped


def test_ciphertext_is_bound_to_tenant_user_and_field(store):
    blob = encrypt_field(store, "t_us", "u1", "address", b"secret")
    with pytest.raises(InvalidTag):
        decrypt_field(store, "t_us", "u1", "phone", blob)
    encrypt_field(store, "t_us", "u2", "address", b"other")
    with pytest.raises(InvalidTag):
        decrypt_field(store, "t_us", "u2", "address", blob)


def test_another_tenant_cannot_read_the_key_or_unwrap_it(store, bao):
    blob = encrypt_field(store, "t_us", "u1", "address", b"secret")
    encrypt_field(store, "t_eu", "u9", "address", b"gives t_eu a master key of its own")
    with pytest.raises(KeyShredded):  # row-level security hides t_us's key from t_eu's context
        decrypt_field(store, "t_eu", "u1", "address", blob)
    [[wrapped_hex]] = rows("SELECT encode(wrapped_dek, 'hex') FROM user_keys WHERE user_id = 'u1'")
    wrapped = bytes.fromhex(wrapped_hex)
    with pytest.raises(httpx.HTTPStatusError):  # t_eu's master key cannot unwrap t_us's data key
        OpenBaoTransit(bao).unwrap("t_eu", wrapped)


def test_shredding_makes_only_that_users_fields_unreadable(store):
    mine = encrypt_field(store, "t_us", "u3", "address", b"erase me")
    theirs = encrypt_field(store, "t_us", "u4", "address", b"keep me")
    assert store.shred("t_us", "u3") == 1
    with pytest.raises(KeyShredded):
        decrypt_field(store, "t_us", "u3", "address", mine)
    assert decrypt_field(store, "t_us", "u4", "address", theirs) == b"keep me"
    assert store.shred("t_eu", "u4") == 0  # another tenant cannot shred it either


def test_key_store_requires_an_autocommit_connection(bao):
    with psycopg.connect(DSN) as conn, pytest.raises(ValueError, match="autocommit"):
        KeyStore(conn, OpenBaoTransit(bao))


def test_invalid_tenant_id_never_reaches_openbao(bao):
    with pytest.raises(ValueError, match="invalid tenant id"):
        OpenBaoTransit(bao).wrap("../sys", b"x")


def test_secrets_come_from_the_environment_first_then_openbao(bao, monkeypatch):
    bao.request("POST", "secret/data/support-agent", {"data": {"GROQ_API_KEY": "from-bao"}})
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert load_secret("GROQ_API_KEY", bao) == "from-bao"
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert load_secret("GROQ_API_KEY", bao) == "from-env"
    with pytest.raises(MissingSecret):
        load_secret("NOT_SET_ANYWHERE", bao)


def test_rotated_secret_is_read_on_the_next_call(bao, monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    for value in ("v1", "v2"):
        bao.request("POST", "secret/data/support-agent", {"data": {"UPSTASH_REDIS_REST_TOKEN": value}})
        assert load_secret("UPSTASH_REDIS_REST_TOKEN", bao) == value
