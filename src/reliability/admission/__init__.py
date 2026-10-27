"""Admission control for turns (NFR-16 / RP-ADP-01: RP-D1, RP-D2, RP-D3, RP-D14).

Admission.admit(tenant, user, conversation, turn_id) -> Verdict:

1. counters, one-minute windows in Upstash Redis (key per tenant, user and minute): requests per user (10)
   and per tenant (120), and the tenant's exact tokens per minute (60,000) as the orchestrator recorded them
   from provider-reported usage (record_usage). At or under every limit: the full agent. Over a limit by up to
   half: KB_ONLY (a knowledge-base answer, no tools, no specialists: degraded_answer). Beyond that: THROTTLED,
   an HTTP 429 with Retry-After = the seconds left in the window.
2. one active turn per conversation: SET NX with a 60 s expiry (a crashed worker's turn frees itself); a
   message while a turn runs gets BUSY ("still working on your last message", HTTP 409) with the active turn's
   id. Only the turn that holds the lock can release or extend it; a turn waiting for a human approval holds
   it for the approval's lifetime (hold_for_approval). Another conversation on the same case is not blocked.
3. Upstash unreachable: the counters and locks fall back to this process's memory (RP-FM-103, fail-open to
   local limits) and a warning is logged; with one worker per region in v1 that keeps both guarantees.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass
from enum import Enum

import httpx

from hitl.queues import CANCEL_AFTER

log = logging.getLogger(__name__)

WINDOW = 60                 # seconds
TURN_LOCK_SECONDS = 60
OVERFLOW = 1.5              # up to 150% of a limit degrades; beyond it, 429
STILL_WORKING = "Still working on your last message. Please wait for it to finish."
KB_DISCLAIMER = ("Because our systems are busy right now, I cannot check your account, but here is what our "
                 "documentation says:")

RELEASE = 'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) else return 0 end'
EXTEND = ('if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("expire", KEYS[1], ARGV[2]) '
          'else return 0 end')


class StoreUnavailable(RuntimeError):
    pass


class Mode(str, Enum):
    FULL = "full_agent"
    KB_ONLY = "kb_only"
    THROTTLED = "throttled"     # HTTP 429
    BUSY = "busy"               # HTTP 409


@dataclass(frozen=True)
class Limits:
    user_rpm: int = 10
    tenant_rpm: int = 120
    tenant_tpm: int = 60_000


@dataclass(frozen=True)
class Verdict:
    mode: Mode
    retry_after: int | None = None       # seconds, for THROTTLED
    active_turn_id: str | None = None    # for BUSY
    message: str | None = None

    @property
    def status(self):
        return {Mode.THROTTLED: 429, Mode.BUSY: 409}.get(self.mode, 202)


# Stores -----------------------------------------------------------------------------------------------------

class Upstash:
    """The few Redis operations admission needs, over Upstash's REST API."""

    def __init__(self, url, token, transport=None, timeout=1.0):
        self.http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"},
                                 transport=transport, timeout=timeout)

    def _post(self, path, body):
        try:
            response = self.http.post(path, json=body)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise StoreUnavailable(type(error).__name__) from None
        items = payload if isinstance(payload, list) else [payload]
        if any("error" in item for item in items):
            raise StoreUnavailable("Upstash refused the command")
        return [item["result"] for item in items] if isinstance(payload, list) else payload["result"]

    def add(self, key, amount, ttl):
        """INCRBY and EXPIRE in one transaction; the new total."""
        return self._post("/multi-exec", [["INCRBY", key, str(amount)], ["EXPIRE", key, str(ttl)]])[0]

    def read(self, key):
        value = self._post("/", ["GET", key])
        return int(value) if value is not None else 0

    def acquire(self, key, owner, ttl):
        return self._post("/", ["SET", key, owner, "NX", "EX", str(ttl)]) == "OK"

    def holder(self, key):
        return self._post("/", ["GET", key])

    def release(self, key, owner):
        return self._post("/", ["EVAL", RELEASE, "1", key, owner]) == 1

    def extend(self, key, owner, ttl):
        return self._post("/", ["EVAL", EXTEND, "1", key, owner, str(ttl)]) == 1


class Local:
    """The same operations in this process's memory: the fallback when Upstash is unreachable."""

    def __init__(self, clock=time.time):
        self.clock, self.data, self.lock = clock, {}, threading.Lock()

    def _get(self, key):
        value, expires = self.data.get(key, (None, 0))
        return value if expires > self.clock() else None

    def add(self, key, amount, ttl):
        with self.lock:
            total = int(self._get(key) or 0) + amount
            self.data[key] = (total, self.clock() + ttl)
            return total

    def read(self, key):
        with self.lock:
            return int(self._get(key) or 0)

    def acquire(self, key, owner, ttl):
        with self.lock:
            if self._get(key) is not None:
                return False
            self.data[key] = (owner, self.clock() + ttl)
            return True

    def holder(self, key):
        with self.lock:
            return self._get(key)

    def release(self, key, owner):
        with self.lock:
            if self._get(key) != owner:
                return False
            del self.data[key]
            return True

    def extend(self, key, owner, ttl):
        with self.lock:
            if self._get(key) != owner:
                return False
            self.data[key] = (owner, self.clock() + ttl)
            return True


# Admission --------------------------------------------------------------------------------------------------

class Admission:
    def __init__(self, store, limits=None, clock=time.time, fallback=None):
        """store: Upstash (or any object with its operations); fallback: used while the store is
        unreachable (default: Local)."""
        self.store, self.limits, self.clock = store, limits or Limits(), clock
        self.fallback = fallback or Local(clock)

    def _do(self, operation, *args):
        try:
            return getattr(self.store, operation)(*args)
        except StoreUnavailable as error:
            log.warning("admission store unavailable (%s); using local limits", error)
            return getattr(self.fallback, operation)(*args)

    def _window(self):
        now = self.clock()
        return int(now // WINDOW), max(1, math.ceil(WINDOW - now % WINDOW))

    @staticmethod
    def _lock(tenant_id, conversation_id):
        return f"lock:conv:{tenant_id}:{conversation_id}"

    def admit(self, tenant_id, user_id, conversation_id, turn_id):
        minute, left = self._window()
        users = self._do("add", f"rpm:user:{tenant_id}:{user_id}:{minute}", 1, 2 * WINDOW)
        tenants = self._do("add", f"rpm:tenant:{tenant_id}:{minute}", 1, 2 * WINDOW)
        tokens = self._do("read", f"tpm:tenant:{tenant_id}:{minute}")
        load = max(users / self.limits.user_rpm, tenants / self.limits.tenant_rpm,
                   tokens / self.limits.tenant_tpm)
        if load > OVERFLOW:
            return Verdict(Mode.THROTTLED, retry_after=left, message="Too many requests; try again shortly.")
        if not self._do("acquire", self._lock(tenant_id, conversation_id), turn_id, TURN_LOCK_SECONDS):
            active = self._do("holder", self._lock(tenant_id, conversation_id))
            return Verdict(Mode.BUSY, active_turn_id=active, message=STILL_WORKING)
        return Verdict(Mode.KB_ONLY if load > 1 else Mode.FULL)

    def keep_alive(self, tenant_id, conversation_id, turn_id):
        """A running turn renews its lock (within the 60 s); False when it no longer holds it."""
        return self._do("extend", self._lock(tenant_id, conversation_id), turn_id, TURN_LOCK_SECONDS)

    def hold_for_approval(self, tenant_id, conversation_id, turn_id):
        """A turn waiting on a person keeps the conversation for the approval's lifetime (RP-Q2)."""
        return self._do("extend", self._lock(tenant_id, conversation_id), turn_id,
                        int(CANCEL_AFTER.total_seconds()))

    def finish(self, tenant_id, conversation_id, turn_id):
        """Release the conversation; only the turn that holds it can."""
        return self._do("release", self._lock(tenant_id, conversation_id), turn_id)

    def record_usage(self, tenant_id, usage):
        """Add one completion's provider-reported usage ({"prompt_tokens", "completion_tokens"}) to the
        tenant's minute; refuses anything but two non-negative integers, so the counter stays exact."""
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if any(type(n) is not int or n < 0 for n in (prompt, completion)):
            raise ValueError("usage must be the provider's prompt and completion token counts")
        minute, _ = self._window()
        return self._do("add", f"tpm:tenant:{tenant_id}:{minute}", prompt + completion, 2 * WINDOW)


# The degraded answer ----------------------------------------------------------------------------------------

def degraded_answer(retrieve, generate, question):
    """RP-Q1: an answer from the knowledge base only. retrieve(question) -> [(passage id, masked text)];
    generate(prompt) -> text from a small model. No tools and no specialists can be reached from here. When
    the model is unavailable the top three passages are returned as cited snippets."""
    passages = list(retrieve(question))[:3]
    if not passages:
        return f"{KB_DISCLAIMER} nothing in our documentation matches this yet; a person can help."
    sources = "\n\n".join(f"[{pid}] {text}" for pid, text in passages)
    prompt = (f"{KB_DISCLAIMER}\nAnswer only from these passages, cite them by id, and make no claim about "
              f"the customer's account, invoices or settings.\n\n{sources}\n\nQuestion: {question}")
    try:
        return f"{KB_DISCLAIMER} {generate(prompt)}"
    except Exception:  # noqa: BLE001 - any provider failure falls back to the snippets
        return KB_DISCLAIMER + "\n\n" + "\n\n".join(f"[{pid}] {text}" for pid, text in passages)
