"""Minimal JWTs signed with Ed25519 ("EdDSA"), using only `cryptography`.

decode() accepts nothing but EdDSA, checks the signature first, then expiry, issuer and audience.
"""

import base64
import json
import time

from cryptography.exceptions import InvalidSignature

LEEWAY = 30  # seconds of clock skew tolerated on exp / iat


class TokenError(ValueError):
    pass


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode(claims, private_key):
    signing_input = b".".join(_b64(json.dumps(part, separators=(",", ":")).encode())
                              for part in ({"alg": "EdDSA", "typ": "JWT"}, claims))
    return (signing_input + b"." + _b64(private_key.sign(signing_input))).decode()


def decode(token, public_key, issuer, audience, now=None):
    try:
        head, body, signature = token.split(".")
        header = json.loads(_unb64(head))
        if header.get("alg") != "EdDSA":
            raise TokenError("unsupported algorithm")
        public_key.verify(_unb64(signature), f"{head}.{body}".encode())
        claims = json.loads(_unb64(body))
    except (ValueError, InvalidSignature) as error:
        raise TokenError("invalid token") from error
    now = time.time() if now is None else now
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] + LEEWAY < now:
        raise TokenError("token expired")
    if claims.get("iat", 0) - LEEWAY > now:
        raise TokenError("token issued in the future")
    if claims.get("iss") != issuer:
        raise TokenError("wrong issuer")
    audiences = claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]
    if audience not in audiences:
        raise TokenError("wrong audience")
    return claims
