"""Mock enterprise SSO (OIDC) for v1: an identity provider that signs ID tokens, and their verification.

A real provider (Okta, Entra ID, Auth0) would publish its key through JWKS; verify_id_token() only needs the
provider's public key, issuer and our client id, so swapping the mock out does not change the caller.
"""

import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from channels.identity.tokens import TokenError, decode, encode

ID_TOKEN_TTL = 300


class MockIdP:
    def __init__(self, issuer="https://idp.mock.local", key=None):
        self.issuer, self.key = issuer, key or Ed25519PrivateKey.generate()

    @property
    def public_key(self):
        return self.key.public_key()

    def id_token(self, client_id, tenant_id, user_id, nonce, mfa=True, now=None):
        now = int(time.time() if now is None else now)
        return encode({"iss": self.issuer, "aud": client_id, "sub": user_id, "tid": tenant_id, "nonce": nonce,
                       "amr": ["pwd", "mfa"] if mfa else ["pwd"], "iat": now, "exp": now + ID_TOKEN_TTL},
                      self.key)


def verify_id_token(token, public_key, issuer, client_id, tenant_id, nonce, now=None):
    """Return the user id from a valid ID token for this tenant and login attempt, signed in with MFA."""
    claims = decode(token, public_key, issuer, client_id, now)
    if claims.get("nonce") != nonce:
        raise TokenError("nonce mismatch")
    if claims.get("tid") != tenant_id:
        raise TokenError("token is for another tenant")
    if "mfa" not in claims.get("amr", []):
        raise TokenError("SSO sign-in without MFA does not reach T2")
    return claims["sub"]
