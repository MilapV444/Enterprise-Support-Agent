"""The token vault and schema-gated restore (FR-31 / SG-ADP-02: SG-D4, SG-D16, SG-D18; AC-14).

- tokenize(): masks locally (never needs the vault) and stores each new token's value in pii_tokens in the
  separate vault database, encrypted with the M0-04 envelope (tenant data key, bound to the token).
- restore_reply(): real values back into the reply the customer sees.
- restore_args(): real values only into tool fields declared with needs_pii=True; every other field keeps
  the token, so an injected "send this to a logging tool" leaks nothing.
- Vault down: masking still works; replies go out with tokens (degraded); needs_pii tool calls fail closed.
"""

from dataclasses import dataclass

import httpx
import psycopg

from data.keys import KeyShredded, decrypt_field, encrypt_field
from safety.pii.tokens import TOKEN

VAULT_KEY_OWNER = "pii-vault"  # the vault's data key in the key store, one per tenant
OUTAGE = (psycopg.Error, httpx.HTTPError, OSError)


class VaultUnavailable(RuntimeError):
    pass


class UnknownToken(LookupError):
    pass


@dataclass
class Restored:
    text: str
    degraded: bool  # True when the vault could not be reached and tokens were left in place


def needs_pii_fields(schema):
    """Names of the fields a reviewed tool schema marks needs_pii=True (pydantic Field json_schema_extra)."""
    return {name for name, info in schema.model_fields.items()
            if (info.json_schema_extra or {}).get("needs_pii") is True}


class Vault:
    def __init__(self, tokenizer, connect, key_store):
        """connect(): autocommit psycopg connection to the vault database; key_store: data.keys.KeyStore."""
        self.tokenizer, self.connect, self.keys = tokenizer, connect, key_store

    def _context(self, conn, tenant_id):
        conn.execute("SET LOCAL ROLE vault_service")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    def tokenize(self, tenant_id, text):
        """(masked text, stored): stored is False when the vault could not record the values."""
        masked, found = self.tokenizer.mask(text)
        if not found:
            return masked, True
        try:
            with self.connect() as conn, conn.transaction():
                self._context(conn, tenant_id)
                for token, (kind, value) in found.items():
                    sealed = encrypt_field(self.keys, tenant_id, VAULT_KEY_OWNER, token, value.encode())
                    conn.execute("INSERT INTO pii_tokens (tenant_id, token, kind, value_enc) "
                                 "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                 (tenant_id, token, kind, sealed))
        except OUTAGE:
            return masked, False
        return masked, True

    def lookup(self, tenant_id, tokens):
        """{token: value} for the tokens this tenant's vault holds; raises VaultUnavailable on an outage."""
        if not tokens:
            return {}
        try:
            with self.connect() as conn, conn.transaction():
                self._context(conn, tenant_id)
                rows = conn.execute("SELECT token, value_enc FROM pii_tokens WHERE token = ANY(%s)",
                                    (list(tokens),)).fetchall()
            values = {}
            for token, sealed in rows:
                try:
                    values[token] = decrypt_field(self.keys, tenant_id, VAULT_KEY_OWNER, token,
                                                  bytes(sealed)).decode()
                except KeyShredded:
                    continue  # erased: the token stays a token
            return values
        except OUTAGE as error:
            raise VaultUnavailable(str(error)) from error

    def restore_reply(self, tenant_id, text):
        try:
            values = self.lookup(tenant_id, set(TOKEN.findall(text)))
        except VaultUnavailable:
            return Restored(text, degraded=True)
        return Restored(TOKEN.sub(lambda m: values.get(m.group(0), m.group(0)), text), degraded=False)

    def restore_args(self, tenant_id, schema, args):
        """Tool arguments with real values in needs_pii fields only; fails closed if they cannot be."""
        gated = {name: value for name, value in args.items()
                 if name in needs_pii_fields(schema) and isinstance(value, str) and TOKEN.search(value)}
        if not gated:
            return dict(args)
        wanted = {token for value in gated.values() for token in TOKEN.findall(value)}
        values = self.lookup(tenant_id, wanted)  # VaultUnavailable propagates: the tool must not run
        missing = wanted - values.keys()
        if missing:
            raise UnknownToken(f"no value for {sorted(missing)} in this tenant's vault")
        restored = {name: TOKEN.sub(lambda m: values[m.group(0)], value) for name, value in gated.items()}
        return {**args, **restored}
