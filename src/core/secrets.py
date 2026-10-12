"""OpenBao client and secret loading (NFR-30, DL-ADP-05).

Secrets come from the environment first, then from OpenBao's KV v2 store at secret/<SECRETS_PATH>.
Values are read on every call and never cached, so a rotated operational secret takes effect on the next
read. The PII token key (PII_TOKEN_KEY) lives in the same store but is never rotated (DL-D8).
"""

import os

import httpx

SECRETS_PATH = "support-agent"


class OpenBao:
    def __init__(self, addr=None, token=None, timeout=5.0):
        self.http = httpx.Client(
            base_url=(addr or os.environ.get("BAO_ADDR", "http://127.0.0.1:8200")).rstrip("/") + "/v1/",
            headers={"X-Vault-Token": token or os.environ["OPENBAO_DEV_TOKEN"]},
            timeout=timeout,
        )

    def request(self, method, path, body=None):
        response = self.http.request(method, path, json=body)
        response.raise_for_status()
        return response.json() if response.content else None

    def enable_transit(self):
        if "transit/" not in self.request("GET", "sys/mounts"):
            self.request("POST", "sys/mounts/transit", {"type": "transit"})


class MissingSecret(KeyError):
    pass


def load_secret(name, bao=None):
    if name in os.environ:
        return os.environ[name]
    try:
        data = (bao or OpenBao()).request("GET", f"secret/data/{SECRETS_PATH}")["data"]["data"]
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
        data = {}
    if name not in data:
        raise MissingSecret(name)
    return data[name]
