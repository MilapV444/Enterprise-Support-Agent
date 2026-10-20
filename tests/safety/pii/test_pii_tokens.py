"""M1-13: PII detection, the technical allow-list, deterministic tokens and log redaction (FR-31, AC-14)."""

import logging

import pytest

from safety.pii.tokens import TOKEN, RedactingFilter, Tokenizer, find, luhn

TOKENS = Tokenizer(b"test-token-key")


@pytest.mark.parametrize("text, kind", [
    ("mail sarah@acme.com today", "EMAIL"), ("call +1 (415) 555-0100", "PHONE"),
    ("SSN 123-45-6789", "SSN"), ("SSN 123 - 45 - 6789", "SSN"), ("SSN 123 45 6789", "SSN"),
    ("card 4111 1111 1111 1111", "CARD"), ("card 4111-1111-1111-1111", "CARD"),
    ("call 415.555.0100", "PHONE"),
])
def test_personal_data_is_found(text, kind):
    assert [k for _, _, k, _ in find(text)] == [kind]


@pytest.mark.parametrize("text", [
    "invoice INV-9821 and BUG-8192", "restart auth-user-service as admin", "pod k8s-pod-c2 in vpc-9021a",
    "got ERR_504_GATEWAY_TIMEOUT then SIGKILL", "released 2026-10-20 as v4.2.1", "order 1234 5678 9012 3456",
    "role arn:aws:iam::123456789012:role/support", "upgrade from 1.12 to 1.13.4",
])
def test_technical_identifiers_and_non_pii_numbers_are_left_alone(text):
    assert find(text) == [] and TOKENS.mask(text)[0] == text


def test_cards_must_pass_the_luhn_check():
    assert luhn("4111111111111111") and not luhn("1234567890123456")


def test_tokens_are_deterministic_and_typed():
    first, found = TOKENS.mask("I am Sarah@Acme.com, card 4111 1111 1111 1111")
    again, _ = TOKENS.mask("sarah@acme.com wrote again")
    email = TOKENS.token("EMAIL", "sarah@acme.com")
    assert email in first and email in again and TOKEN.fullmatch(email)
    assert {kind for kind, _ in found.values()} == {"EMAIL", "CARD"}
    assert "sarah" not in first.lower() and "4111" not in first
    assert Tokenizer(b"another-key").token("EMAIL", "sarah@acme.com") != email


def test_masking_masked_text_changes_nothing():
    masked, _ = TOKENS.mask("sarah@acme.com and +44 20 7946 0000")
    assert TOKENS.mask(masked) == (masked, {})


def test_log_records_never_carry_raw_pii(caplog):
    logger = logging.getLogger("support.test")
    logger.addFilter(RedactingFilter(TOKENS))
    with caplog.at_level(logging.INFO, logger="support.test"):
        logger.info("refund for %s on card %s", "sarah@acme.com", "4111 1111 1111 1111")
    assert "sarah@acme.com" not in caplog.text and "4111" not in caplog.text
    assert TOKENS.token("EMAIL", "sarah@acme.com") in caplog.text
