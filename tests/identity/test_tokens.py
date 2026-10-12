"""M1-02: Ed25519 JWT encoding and the checks decode() must enforce."""

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from channels.identity.tiers import StepUpRequired, Tier, require
from channels.identity.tokens import TokenError, decode, encode

KEY = Ed25519PrivateKey.generate()
CLAIMS = {"iss": "me", "aud": "api", "sub": "sarah", "iat": 1000, "exp": 2000}


def test_round_trip():
    assert decode(encode(CLAIMS, KEY), KEY.public_key(), "me", "api", now=1500) == CLAIMS


@pytest.mark.parametrize("now, issuer, audience, message", [
    (2100, "me", "api", "expired"),
    (900 - 60, "me", "api", "future"),
    (1500, "other", "api", "issuer"),
    (1500, "me", "other", "audience"),
])
def test_claim_checks(now, issuer, audience, message):
    with pytest.raises(TokenError, match=message):
        decode(encode(CLAIMS, KEY), KEY.public_key(), issuer, audience, now=now)


def test_signature_from_another_key_or_tampered_claims_is_rejected():
    with pytest.raises(TokenError, match="invalid"):
        decode(encode(CLAIMS, Ed25519PrivateKey.generate()), KEY.public_key(), "me", "api", now=1500)
    head, _, signature = encode(CLAIMS, KEY).split(".")
    forged = base64.urlsafe_b64encode(json.dumps({**CLAIMS, "sub": "admin"}).encode()).rstrip(b"=").decode()
    with pytest.raises(TokenError, match="invalid"):
        decode(f"{head}.{forged}.{signature}", KEY.public_key(), "me", "api", now=1500)


def test_alg_none_is_rejected():
    head = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(CLAIMS).encode()).rstrip(b"=").decode()
    with pytest.raises(TokenError):
        decode(f"{head}.{body}.", KEY.public_key(), "me", "api", now=1500)


def test_step_up_rule():
    require("T2_SSO", Tier.T1_VERIFIED)
    with pytest.raises(StepUpRequired) as raised:
        require("T0_ANON", Tier.T1_VERIFIED)
    assert raised.value.required is Tier.T1_VERIFIED
