"""M1-02: tiered sign-in, step-up, revocation, on-behalf-of tokens and the API with sign-in (FR-7, FR-8)."""

import pytest
from fastapi.testclient import TestClient

from channels.identity.oidc import MockIdP
from channels.identity.otp import OtpError
from channels.identity.server import build_app
from channels.identity.service import ACCESS_TTL, API_AUDIENCE, ISSUER, Identity
from channels.identity.tiers import SCOPES, StepUpRequired, Tier
from channels.identity.tokens import TokenError, decode
from tests.identity.conftest import DSN, connect, sql

IDP = MockIdP()


@pytest.fixture
def outbox():
    return {}


@pytest.fixture
def identity(outbox):
    return Identity(connect, idp=(IDP.issuer, IDP.public_key),
                    send_otp=lambda tenant, user, code: outbox.__setitem__((tenant, user), code))


def claims(identity, token):
    return decode(token, identity.key.public_key(), ISSUER, API_AUDIENCE)


def verified(identity, outbox, user="sarah", current=None):
    challenge = identity.start_otp("t_us", user)
    return identity.verify_otp("t_us", challenge, outbox[("t_us", user)], current)


def sso(identity, user="sarah", current=None, mfa=True, tenant="t_us"):
    return identity.sso("t_us", IDP.id_token(identity.client_id, tenant, user, "n-1", mfa), "n-1", current)


@pytest.mark.parametrize("tier", list(Tier))
def test_each_tier_gets_only_its_scopes_and_a_24_hour_token(identity, outbox, tier):
    token = {Tier.T0_ANON: lambda: identity.anonymous("t_us"),
             Tier.T1_VERIFIED: lambda: verified(identity, outbox),
             Tier.T2_SSO: lambda: sso(identity)}[tier]()
    got = claims(identity, token)
    assert (got["tier"], got["scope"].split()) == (tier.name, list(SCOPES[tier]))
    assert got["exp"] - got["iat"] == ACCESS_TTL


def test_otp_is_single_use_and_wrong_codes_count(identity, outbox):
    challenge = identity.start_otp("t_us", "kim")
    code = outbox[("t_us", "kim")]
    with pytest.raises(OtpError):
        identity.verify_otp("t_us", challenge, "000000" if code != "000000" else "111111")
    identity.verify_otp("t_us", challenge, code)
    with pytest.raises(OtpError):
        identity.verify_otp("t_us", challenge, code)


def test_otp_locks_after_five_attempts_and_expires(identity, outbox):
    challenge = identity.start_otp("t_us", "lee")
    code = outbox[("t_us", "lee")]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(OtpError):
            identity.verify_otp("t_us", challenge, wrong)
    with pytest.raises(OtpError):
        identity.verify_otp("t_us", challenge, code)
    late = identity.start_otp("t_us", "lee")
    sql(f"UPDATE otp_challenges SET expires_at = now() - interval '1 second' WHERE id = '{late}'")
    with pytest.raises(OtpError):
        identity.verify_otp("t_us", late, outbox[("t_us", "lee")])


def test_otp_challenge_is_tenant_bound(identity, outbox):
    challenge = identity.start_otp("t_us", "max")
    with pytest.raises(OtpError):
        identity.verify_otp("t_eu", challenge, outbox[("t_us", "max")])


@pytest.mark.parametrize("change, message", [
    (dict(mfa=False), "MFA"), (dict(tenant="t_eu"), "another tenant")])
def test_sso_needs_mfa_and_the_right_tenant(identity, change, message):
    with pytest.raises(TokenError, match=message):
        sso(identity, **change)


def test_sso_rejects_a_wrong_nonce_or_another_providers_token(identity):
    with pytest.raises(TokenError, match="nonce"):
        identity.sso("t_us", IDP.id_token(identity.client_id, "t_us", "sarah", "n-1"), "n-2")
    with pytest.raises(TokenError):
        identity.sso("t_us", MockIdP().id_token(identity.client_id, "t_us", "sarah", "n-1"), "n-1")


def test_step_up_keeps_the_session_moves_anonymous_conversations_and_retires_the_old_token(identity, outbox):
    anonymous = identity.anonymous("t_us")
    app = TestClient(build_app(DSN, identity))
    reply = app.post("/v1/conversations/conv-s/turns", json={"content": "hi"},
                     headers={"Authorization": f"Bearer {anonymous}", "Idempotency-Key": "k1"})
    assert reply.status_code == 202
    upgraded = verified(identity, outbox, user="sarah", current=anonymous)
    assert claims(identity, upgraded)["sid"] == claims(identity, anonymous)["sid"]
    assert sql("SELECT principal_id FROM conversations WHERE id = 'conv-s'") == [["sarah"]]
    with pytest.raises(TokenError, match="step-up"):
        identity.exchange(anonymous, "public-read-tools")
    stronger = sso(identity, current=upgraded)
    assert claims(identity, stronger)["sid"] == claims(identity, anonymous)["sid"]


def test_another_person_signing_in_gets_a_new_session(identity, outbox):
    sarah = verified(identity, outbox, user="sarah")
    bob = verified(identity, outbox, user="bob", current=sarah)
    assert claims(identity, bob)["sid"] != claims(identity, sarah)["sid"]


def test_on_behalf_of_tokens(identity, outbox):
    token = verified(identity, outbox)
    obo = identity.verify_obo(identity.exchange(token, "status-tools"), "status-tools")
    assert (obo["sub"], obo["act"], obo["aud"], obo["exp"] - obo["iat"]) == (
        "sarah", {"sub": "svc:enterprise-agent-runtime"}, "status-tools", 900)
    assert obo["scope"].split() == ["status:read", "tickets:read", "orders:read", "case:update"]
    with pytest.raises(StepUpRequired) as raised:
        identity.exchange(token, "account-tools")
    assert raised.value.required is Tier.T2_SSO
    with pytest.raises(TokenError):  # an access token is not an on-behalf-of token
        identity.verify_obo(token, API_AUDIENCE)


def test_anonymous_gets_only_the_read_only_public_audience(identity):
    token = identity.anonymous("t_us")
    obo = identity.verify_obo(identity.exchange(token, "public-read-tools"), "public-read-tools")
    assert obo["sub"].startswith("anon:") and obo["scope"].split() == ["kb:read", "status:read"]
    for audience in ("status-tools", "account-tools"):
        with pytest.raises(StepUpRequired):
            identity.exchange(token, audience)


def test_logout_and_session_expiry_revoke_the_24_hour_token(identity, outbox):
    token = verified(identity, outbox)
    identity.logout(token)
    with pytest.raises(TokenError, match="session"):
        identity.exchange(token, "public-read-tools")
    other = verified(identity, outbox)
    sql(f"UPDATE sessions SET last_seen_at = now() - interval '31 minutes' "
        f"WHERE id = '{claims(identity, other)['sid']}'")
    with pytest.raises(TokenError, match="session"):
        identity.exchange(other, "public-read-tools")


def test_api_with_real_sign_in(identity, outbox):
    app = TestClient(build_app(DSN, identity, mock_idp=IDP, poll_seconds=0.05, stream_seconds=0.3))
    assert app.post("/v1/conversations/conv-x/turns", json={"content": "hi"},
                    headers={"Idempotency-Key": "k"}).status_code == 401
    token = app.post("/v1/identity/anonymous", json={"tenant_id": "t_us"}).json()["access_token"]
    sarah = {"Authorization": f"Bearer {token}", "Idempotency-Key": "k"}
    turn = app.post("/v1/conversations/conv-x/turns", json={"content": "hi"}, headers=sarah)
    assert turn.status_code == 202
    other = app.post("/v1/identity/anonymous", json={"tenant_id": "t_us"}).json()["access_token"]
    intruder = {"Authorization": f"Bearer {other}"}
    assert app.get("/v1/conversations/conv-x/events", headers=intruder).status_code == 403
    nonce = "n-9"
    id_token = app.post("/v1/identity/mock-idp", json={"tenant_id": "t_us", "user_id": "sarah",
                                                       "nonce": nonce}).json()["id_token"]
    upgraded = app.post("/v1/identity/sso", json={"tenant_id": "t_us", "id_token": id_token, "nonce": nonce},
                        headers={"Authorization": f"Bearer {token}"}).json()["access_token"]
    assert claims(identity, upgraded)["tier"] == "T2_SSO"
    assert app.post("/v1/identity/logout", headers={"Authorization": f"Bearer {upgraded}"}).status_code == 204
    after_logout = app.post("/v1/conversations/conv-x/turns", json={"content": "hi"},
                            headers={"Authorization": f"Bearer {upgraded}", "Idempotency-Key": "k2"})
    assert after_logout.status_code == 401


def test_an_open_event_stream_counts_as_activity(identity, outbox):
    token = verified(identity, outbox)
    sid = claims(identity, token)["sid"]
    sql(f"UPDATE sessions SET last_seen_at = now() - interval '29 minutes' WHERE id = '{sid}'")
    app = TestClient(build_app(DSN, identity, poll_seconds=0.05, stream_seconds=0.2))
    with app.stream("GET", "/v1/conversations/conv-live/events",
                    headers={"Authorization": f"Bearer {token}"}) as reply:
        assert reply.status_code == 200
    [[idle]] = sql(f"SELECT extract(epoch FROM now() - last_seen_at) < 60 FROM sessions WHERE id = '{sid}'")
    assert idle == "t"
