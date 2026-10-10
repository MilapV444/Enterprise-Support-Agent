"""Envelope encryption and crypto-shredding.

- Each tenant has a master key in OpenBao transit (v1 stand-in for a per-tenant KMS key); it never leaves
  OpenBao.
- Each user has a random 256-bit data key, wrapped under the tenant master key and stored in user_keys in
  the key-store database (migrations/keys). Deleting a user's rows there shreds every field encrypted
  under the key.
- Fields are AES-256-GCM with the tenant, user and field name as associated data, so a ciphertext cannot
  be replayed into another user's or another field's slot.

Field format: key_version (4 bytes, big-endian) | nonce (12 bytes) | ciphertext + tag.
"""

import base64
import os
import re
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TENANT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class KeyShredded(LookupError):
    """The user's data key is gone (erased, or never created): their encrypted fields cannot be read."""


class OpenBaoTransit:
    """Wraps and unwraps data keys under the tenant's transit key, created on first use."""

    def __init__(self, bao):
        self.bao = bao

    def _path(self, op, tenant_id):
        if not TENANT_ID.match(tenant_id):
            raise ValueError(f"invalid tenant id: {tenant_id!r}")
        return f"transit/{op}/tenant-{tenant_id}"

    def wrap(self, tenant_id, key):
        body = {"plaintext": base64.b64encode(key).decode()}
        reply = self.bao.request("POST", self._path("encrypt", tenant_id), body)
        return reply["data"]["ciphertext"].encode()

    def unwrap(self, tenant_id, wrapped):
        body = {"ciphertext": wrapped.decode()}
        reply = self.bao.request("POST", self._path("decrypt", tenant_id), body)
        return base64.b64decode(reply["data"]["plaintext"])


class KeyStore:
    """Per-user data keys in the key-store database, used as key_service under the tenant's context.

    The connection must be in autocommit mode: each call runs in its own transaction, so the tenant
    context set with SET LOCAL ends with it.
    """

    def __init__(self, conn, kms):
        if not conn.autocommit:
            raise ValueError("KeyStore needs an autocommit connection")
        self.conn, self.kms = conn, kms

    def current_key(self, tenant_id, user_id):
        """Return (version, key) for the user's newest data key, creating version 1 on first use."""
        with self.conn.transaction():
            self._context(tenant_id)
            row = self._latest(user_id)
            if row is None:
                wrapped = self.kms.wrap(tenant_id, AESGCM.generate_key(bit_length=256))
                self.conn.execute(
                    "INSERT INTO user_keys (tenant_id, user_id, key_version, wrapped_dek) "
                    "VALUES (%s, %s, 1, %s) ON CONFLICT DO NOTHING", (tenant_id, user_id, wrapped))
                row = self._latest(user_id)
        return row[0], self.kms.unwrap(tenant_id, bytes(row[1]))

    def key(self, tenant_id, user_id, version):
        with self.conn.transaction():
            self._context(tenant_id)
            row = self.conn.execute(
                "SELECT wrapped_dek FROM user_keys WHERE user_id = %s AND key_version = %s",
                (user_id, version)).fetchone()
        if row is None:
            raise KeyShredded(f"{tenant_id}/{user_id} v{version}")
        return self.kms.unwrap(tenant_id, bytes(row[0]))

    def shred(self, tenant_id, user_id):
        """Delete every data key of the user; returns how many were deleted."""
        with self.conn.transaction():
            self._context(tenant_id)
            return self.conn.execute("DELETE FROM user_keys WHERE user_id = %s", (user_id,)).rowcount

    def _context(self, tenant_id):
        self.conn.execute("SET LOCAL ROLE key_service")
        self.conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    def _latest(self, user_id):
        return self.conn.execute(
            "SELECT key_version, wrapped_dek FROM user_keys WHERE user_id = %s "
            "ORDER BY key_version DESC LIMIT 1", (user_id,)).fetchone()


def _aad(tenant_id, user_id, field):
    return "\x1f".join((tenant_id, user_id, field)).encode()


def encrypt_field(store, tenant_id, user_id, field, plaintext):
    version, key = store.current_key(tenant_id, user_id)
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext, _aad(tenant_id, user_id, field))
    return struct.pack(">I", version) + nonce + sealed


def decrypt_field(store, tenant_id, user_id, field, blob):
    (version,), nonce, sealed = struct.unpack(">I", blob[:4]), blob[4:16], blob[16:]
    key = store.key(tenant_id, user_id, version)
    return AESGCM(key).decrypt(nonce, sealed, _aad(tenant_id, user_id, field))
