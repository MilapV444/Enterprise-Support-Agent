"""One-time codes for T1 verification: 6 digits, 10 minutes, single use, 5 attempts (UA-D3).

Only a salted HMAC of the code is stored. Delivery to the email / phone on file is the `send` callable's job.
The table is module-owned (DECISION-d4b79fe1).
"""

import hashlib
import hmac
import os
import secrets

from data.migrate import psql

TTL = "10 minutes"
MAX_ATTEMPTS = 5

SCHEMA_NAME = "identity_0001_otp_challenges.sql"
SCHEMA = """
CREATE TABLE otp_challenges (
  id           text PRIMARY KEY DEFAULT gen_random_uuid()::text,
  tenant_id    text NOT NULL REFERENCES tenants (id),
  principal_id text NOT NULL,
  salt         bytea NOT NULL,
  code_hash    bytea NOT NULL,
  attempts     integer NOT NULL DEFAULT 0,
  expires_at   timestamptz NOT NULL,
  used_at      timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE otp_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE otp_challenges FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON otp_challenges
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE otp_challenges OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE ON otp_challenges TO app_runtime;
"""


class OtpError(PermissionError):
    pass


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def _hash(salt, code):
    return hmac.new(salt, code.encode(), hashlib.sha256).digest()


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def issue(conn, tenant_id, principal_id, send):
    """Create a challenge, hand the code to `send(tenant_id, principal_id, code)`, return the challenge id."""
    code, salt = f"{secrets.randbelow(10**6):06d}", os.urandom(16)
    with conn.transaction():
        _context(conn, tenant_id)
        (challenge_id,) = conn.execute(
            "INSERT INTO otp_challenges (tenant_id, principal_id, salt, code_hash, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + %s::interval) RETURNING id",
            (tenant_id, principal_id, salt, _hash(salt, code), TTL)).fetchone()
        send(tenant_id, principal_id, code)
    return challenge_id


def verify(conn, tenant_id, challenge_id, code):
    """Return the verified principal id, or raise OtpError. Every attempt counts, right or wrong."""
    with conn.transaction():
        _context(conn, tenant_id)
        row = conn.execute(
            "UPDATE otp_challenges SET attempts = attempts + 1 WHERE id = %s AND used_at IS NULL "
            "AND expires_at > now() AND attempts < %s RETURNING principal_id, salt, code_hash",
            (challenge_id, MAX_ATTEMPTS)).fetchone()
        if row is not None and hmac.compare_digest(_hash(bytes(row[1]), str(code)), bytes(row[2])):
            conn.execute("UPDATE otp_challenges SET used_at = now() WHERE id = %s", (challenge_id,))
            return row[0]
    raise OtpError("invalid, expired or used code")
