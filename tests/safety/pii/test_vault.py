"""M1-13: the token vault, reply restore, needs_pii-gated tool restore, vault-down degrade and a PII-seeded
conversation that never shows raw PII to a model, Jev, a provider or a log (FR-31, AC-14).
Runs against the compose Postgres (vault + key-store databases) and OpenBao."""

import json
import logging
import subprocess
import time
from pathlib import Path

import httpx
import psycopg
import pytest
from pydantic import BaseModel, Field

from core.orchestrator.decisions import Answer, DecisionEngine, Masked
from core.secrets import OpenBao
from data.keys import KeyStore, OpenBaoTransit
from data.migrate import migrate, psql
from reliability.fallbacks import openai_compatible
from safety.pii.tokens import RedactingFilter, Tokenizer
from safety.pii.vault import UnknownToken, Vault, VaultUnavailable, needs_pii_fields

ROOT = Path(__file__).resolve().parents[3]
VAULT_DB, KEYS_DB = "test_pii_vault", "test_pii_keys"
DSN = "postgresql://agent:change-me@127.0.0.1:5432/{}"  # credentials from .env.example
TOKENS = Tokenizer(b"test-token-key")
SEED = "I'm sarah@acme.com, card 4111 1111 1111 1111, call +44 20 7946 0000 about INV-9821"
RAW = ("sarah@acme.com", "4111 1111 1111 1111", "4111111111111111", "+44 20 7946 0000")


class SendEmail(BaseModel):
    """A reviewed tool schema: only the recipient may carry a real value."""

    to_address: str = Field(json_schema_extra={"needs_pii": True})
    subject: str
    body: str


@pytest.fixture(scope="module")
def stores():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres", "openbao"], cwd=ROOT, check=True, capture_output=True)
    for name, kind in ((VAULT_DB, "vault"), (KEYS_DB, "keys")):
        psql("postgres", f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        psql("postgres", f'CREATE DATABASE "{name}"')
        migrate(kind, name)
    bao = OpenBao("http://127.0.0.1:8200", "change-me")
    for _ in range(30):
        try:
            bao.enable_transit()
            break
        except httpx.HTTPError:
            time.sleep(1)
    with psycopg.connect(DSN.format(KEYS_DB), autocommit=True) as keys_conn:
        yield KeyStore(keys_conn, OpenBaoTransit(bao))


@pytest.fixture
def vault(stores):
    return Vault(TOKENS, lambda: psycopg.connect(DSN.format(VAULT_DB), autocommit=True), stores)


@pytest.fixture
def broken(stores):
    def unreachable():
        return psycopg.connect("postgresql://agent:change-me@127.0.0.1:1/none", connect_timeout=1)
    return Vault(TOKENS, unreachable, stores)


def test_values_are_stored_encrypted_and_restored_into_the_reply(vault):
    masked, stored = vault.tokenize("t_us", SEED)
    assert stored and all(raw not in masked for raw in RAW) and "INV-9821" in masked
    rows = psql(VAULT_DB, "SELECT encode(value_enc, 'hex') FROM pii_tokens")
    assert rows and all(b"sarah".hex() not in value for (value,) in rows)  # encrypted at rest
    reply = vault.restore_reply("t_us", f"I emailed {TOKENS.token('EMAIL', 'sarah@acme.com')}.")
    assert reply.text == "I emailed sarah@acme.com." and not reply.degraded


def test_only_needs_pii_fields_get_real_values(vault):
    vault.tokenize("t_us", SEED)
    email = TOKENS.token("EMAIL", "sarah@acme.com")
    args = {"to_address": email, "subject": f"Re: {email}", "body": f"Hello {email}"}
    restored = vault.restore_args("t_us", SendEmail, args)
    assert restored == {"to_address": "sarah@acme.com", "subject": f"Re: {email}", "body": f"Hello {email}"}
    assert needs_pii_fields(SendEmail) == {"to_address"}


def test_another_tenant_cannot_restore_the_token(vault):
    vault.tokenize("t_us", SEED)
    email = TOKENS.token("EMAIL", "sarah@acme.com")
    assert vault.restore_reply("t_eu", email).text == email
    with pytest.raises(UnknownToken):
        vault.restore_args("t_eu", SendEmail, {"to_address": email, "subject": "s", "body": "b"})


def test_vault_down_masks_anyway_degrades_replies_and_blocks_needs_pii_tools(broken):
    masked, stored = broken.tokenize("t_us", SEED)
    assert not stored and all(raw not in masked for raw in RAW)
    email = TOKENS.token("EMAIL", "sarah@acme.com")
    reply = broken.restore_reply("t_us", f"Sent to {email}")
    assert reply.degraded and reply.text == f"Sent to {email}"
    with pytest.raises(VaultUnavailable):
        broken.restore_args("t_us", SendEmail, {"to_address": email, "subject": "s", "body": "b"})
    assert broken.restore_args("t_us", SendEmail, {"to_address": "ops@example.org", "subject": "s",
                                                   "body": "b"})["to_address"] == "ops@example.org"


class RecordingJev:
    def __init__(self):
        self.sent = []

    def evaluate(self, state, questions):
        self.sent.append(json.dumps(state))
        return {qid: Answer(True, 0.99) for qid in questions}


def test_a_pii_seeded_conversation_shows_no_raw_pii_to_models_jev_providers_or_logs(vault, caplog):
    masked, _ = vault.tokenize("t_us", SEED)
    jev = RecordingJev()
    DecisionEngine(jev).guard("ok", "Did the customer confirm?", {"message": Masked(masked)})
    provider_bodies = []

    def provider(request):
        provider_bodies.append(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": "Done."}}]})

    model = openai_compatible("free", "https://llm.test/v1", "m", transport=httpx.MockTransport(provider))
    model.complete([{"role": "user", "content": masked}], 64)
    logger = logging.getLogger("support.turn")
    logger.addFilter(RedactingFilter(TOKENS))
    with caplog.at_level(logging.INFO, logger="support.turn"):
        logger.info("turn from customer: %s", SEED)
    for seen in (*jev.sent, *provider_bodies, caplog.text):
        assert all(raw not in seen for raw in RAW), seen
