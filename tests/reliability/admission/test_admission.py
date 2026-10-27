"""M4-01: admission control: per-user, per-tenant and exact token limits with degradation to knowledge-base
answers and then 429, one active turn per conversation, and framework scenario 8 (NFR-16, AC-8)."""

import json
import logging
import threading

import httpx
import pytest

from reliability.admission import (
    EXTEND,
    KB_DISCLAIMER,
    RELEASE,
    STILL_WORKING,
    Admission,
    Limits,
    Local,
    Mode,
    Upstash,
    degraded_answer,
)


class FakeUpstash:
    """Upstash's REST API for the commands admission uses, with a clock; every request is kept."""

    def __init__(self, clock):
        self.clock, self.data, self.requests, self.lock, self.down = clock, {}, [], threading.Lock(), False

    def _get(self, key):
        value, expires = self.data.get(key, (None, float("inf")))
        return value if expires > self.clock[0] else None

    def run(self, command):
        name, *args = command
        if name == "SET":
            key, value, *options = args
            if "NX" in options and self._get(key) is not None:
                return None
            ttl = int(options[options.index("EX") + 1]) if "EX" in options else float("inf")
            self.data[key] = (value, self.clock[0] + ttl)
            return "OK"
        if name == "GET":
            return self._get(args[0])
        if name == "INCRBY":
            total = int(self._get(args[0]) or 0) + int(args[1])
            self.data[args[0]] = (str(total), self.data.get(args[0], (None, float("inf")))[1])
            return total
        if name == "EXPIRE":
            value, _ = self.data[args[0]]
            self.data[args[0]] = (value, self.clock[0] + int(args[1]))
            return 1
        if name == "EVAL":
            script, _, key, owner, *rest = args
            if self._get(key) != owner:
                return 0
            if script == RELEASE:
                del self.data[key]
                return 1
            if script == EXTEND:
                self.data[key] = (owner, self.clock[0] + int(rest[0]))
                return 1
        return {"error": f"unknown command {name}"}

    def __call__(self, request):
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("upstash unreachable")
        body = json.loads(request.content)
        with self.lock:
            if request.url.path == "/multi-exec":
                return httpx.Response(200, json=[{"result": self.run(c)} for c in body])
            result = self.run(body)
        if isinstance(result, dict):
            return httpx.Response(400, json=result)
        return httpx.Response(200, json={"result": result})


T0 = 1_800_000_000.0  # on a minute boundary


@pytest.fixture
def world():
    clock = [T0]
    fake = FakeUpstash(clock)
    store = Upstash("https://upstash.test", "secret-token", transport=httpx.MockTransport(fake))
    return Admission(store, clock=lambda: clock[0]), fake, clock


# Scenario 8: rapid duplicates -------------------------------------------------------------------------------

def test_scenario_8_four_messages_in_800_ms_run_one_turn_and_the_rest_are_told_it_is_still_working(world):
    admission, _, clock = world
    start, verdicts = threading.Barrier(4), {}

    def send(n):
        start.wait()
        clock[0] = T0 + n * 0.2  # 0, 200, 400, 600 ms
        verdicts[n] = admission.admit("t_us", "oncall", "conv-1", f"turn-{n}")
    threads = [threading.Thread(target=send, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    running = [n for n, v in verdicts.items() if v.mode is Mode.FULL]
    assert len(running) == 1
    busy = [v for v in verdicts.values() if v.mode is Mode.BUSY]
    assert len(busy) == 3 and all(v.status == 409 and v.message == STILL_WORKING for v in busy)
    assert {v.active_turn_id for v in busy} == {f"turn-{running[0]}"}


def test_after_the_turn_finishes_the_next_message_runs(world):
    admission, _, _ = world
    assert admission.admit("t_us", "u", "conv-1", "turn-1").mode is Mode.FULL
    assert admission.admit("t_us", "u", "conv-1", "turn-2").mode is Mode.BUSY
    assert admission.finish("t_us", "conv-1", "turn-1")
    assert admission.admit("t_us", "u", "conv-1", "turn-3").mode is Mode.FULL


def test_only_the_turn_holding_the_conversation_can_release_or_extend_it(world):
    admission, _, _ = world
    admission.admit("t_us", "u", "conv-1", "turn-1")
    assert not admission.finish("t_us", "conv-1", "turn-2")
    assert not admission.keep_alive("t_us", "conv-1", "turn-2")
    assert admission.admit("t_us", "u", "conv-1", "turn-3").active_turn_id == "turn-1"


def test_a_crashed_turn_frees_the_conversation_after_sixty_seconds_unless_kept_alive(world):
    admission, _, clock = world
    admission.admit("t_us", "u", "conv-1", "turn-1")
    clock[0] += 59
    assert admission.admit("t_us", "u", "conv-1", "turn-2").mode is Mode.BUSY
    assert admission.keep_alive("t_us", "conv-1", "turn-1")
    clock[0] += 59
    assert admission.admit("t_us", "u", "conv-1", "turn-3").mode is Mode.BUSY       # renewed
    clock[0] += 61
    assert admission.admit("t_us", "u", "conv-1", "turn-4").mode is Mode.FULL       # the worker died


def test_a_turn_waiting_for_approval_keeps_the_conversation_but_not_the_case(world):
    admission, _, clock = world
    admission.admit("t_us", "u", "conv-1", "turn-1")
    assert admission.hold_for_approval("t_us", "conv-1", "turn-1")
    clock[0] += 71 * 3600
    assert admission.admit("t_us", "u", "conv-1", "turn-2").mode is Mode.BUSY        # still waiting
    assert admission.admit("t_us", "u", "conv-2", "turn-3").mode is Mode.FULL        # a new conversation
    clock[0] += 2 * 3600
    assert admission.admit("t_us", "u", "conv-1", "turn-4").mode is Mode.FULL        # cancelled at 72 h


def test_conversations_of_different_tenants_never_share_a_lock(world):
    admission, _, _ = world
    assert admission.admit("t_us", "u", "conv-1", "turn-1").mode is Mode.FULL
    assert admission.admit("t_eu", "u", "conv-1", "turn-2").mode is Mode.FULL


# Limits: full, then knowledge-base only, then 429 -----------------------------------------------------------

def modes(admission, n, user="u", tenant="t_us"):
    out = []
    for i in range(n):
        out.append(admission.admit(tenant, user, f"conv-{user}-{i}", f"turn-{user}-{i}").mode)
    return out


def test_a_user_over_ten_a_minute_degrades_then_gets_429_with_retry_after(world):
    admission, _, clock = world
    clock[0] = T0 + 45
    got = modes(admission, 16)
    assert got == [Mode.FULL] * 10 + [Mode.KB_ONLY] * 5 + [Mode.THROTTLED]
    throttled = admission.admit("t_us", "u", "conv-x", "turn-x")
    assert throttled.status == 429 and throttled.retry_after == 15                  # the window's rest
    clock[0] = T0 + 60
    assert admission.admit("t_us", "u", "conv-y", "turn-y").mode is Mode.FULL       # a new minute


def test_retry_after_is_at_least_a_second(world):
    admission, _, clock = world
    clock[0] = T0 + 59.9
    modes(admission, 16)
    assert admission.admit("t_us", "u", "c", "t").retry_after == 1


def test_the_tenant_limit_counts_every_user(world):
    admission, _, _ = world
    got = [admission.admit("t_us", f"user-{i % 20}", f"conv-{i}", f"turn-{i}").mode for i in range(181)]
    assert got[:120] == [Mode.FULL] * 120 and set(got[120:180]) == {Mode.KB_ONLY}
    assert got[180] is Mode.THROTTLED
    assert admission.admit("t_eu", "user-0", "conv-0", "turn-0").mode is Mode.FULL  # another tenant


def test_exact_token_usage_degrades_then_throttles_the_tenant(world):
    admission, fake, _ = world
    assert admission.record_usage("t_us", {"prompt_tokens": 40_000, "completion_tokens": 20_000}) == 60_000
    assert admission.admit("t_us", "u", "c1", "t1").mode is Mode.FULL                # at the limit
    admission.record_usage("t_us", {"prompt_tokens": 1, "completion_tokens": 0})
    assert admission.admit("t_us", "u", "c2", "t2").mode is Mode.KB_ONLY
    admission.record_usage("t_us", {"prompt_tokens": 29_999, "completion_tokens": 1})
    assert admission.admit("t_us", "u", "c3", "t3").mode is Mode.THROTTLED
    assert admission.admit("t_eu", "u", "c4", "t4").mode is Mode.FULL
    increments = [json.loads(r.content) for r in fake.requests if r.url.path == "/multi-exec"]
    assert ["INCRBY", "tpm:tenant:t_us:30000000", "60000"] in [i[0] for i in increments]  # exact, one write


@pytest.mark.parametrize("usage", [{"prompt_tokens": 10}, {"prompt_tokens": -1, "completion_tokens": 2},
                                   {"prompt_tokens": 1.5, "completion_tokens": 2},
                                   {"prompt_tokens": True, "completion_tokens": 2}, {}])
def test_only_exact_provider_usage_is_counted(world, usage):
    admission, fake, _ = world
    with pytest.raises(ValueError):
        admission.record_usage("t_us", usage)
    assert fake.requests == []


def test_counters_expire_and_writes_are_atomic(world):
    admission, fake, _ = world
    admission.admit("t_us", "u", "c", "t")
    transactions = [json.loads(r.content) for r in fake.requests if r.url.path == "/multi-exec"]
    assert transactions and all(t[1][0] == "EXPIRE" and t[1][2] == "120" for t in transactions)
    assert all(r.headers["Authorization"] == "Bearer secret-token" for r in fake.requests)


# Upstash unreachable ----------------------------------------------------------------------------------------

def test_when_upstash_is_unreachable_limits_and_the_turn_lock_hold_locally(world, caplog):
    admission, fake, _ = world
    fake.down = True
    with caplog.at_level(logging.WARNING):
        assert admission.admit("t_us", "u", "conv-1", "turn-1").mode is Mode.FULL
        assert admission.admit("t_us", "u", "conv-1", "turn-2").mode is Mode.BUSY
        assert modes(admission, 16, user="v")[-1] is Mode.THROTTLED
    assert "using local limits" in caplog.text and "secret-token" not in caplog.text


def test_an_error_reply_from_upstash_is_treated_as_unreachable():
    clock = [T0]

    def broken(request):
        return httpx.Response(200, json={"error": "WRONGTYPE"})
    admission = Admission(Upstash("https://upstash.test", "t", transport=httpx.MockTransport(broken)),
                          clock=lambda: clock[0], fallback=Local(lambda: clock[0]))
    assert admission.admit("t_us", "u", "conv-1", "turn-1").mode is Mode.FULL
    assert admission.admit("t_us", "u", "conv-1", "turn-2").mode is Mode.BUSY


def test_custom_limits():
    clock = [T0]
    admission = Admission(Local(lambda: clock[0]), Limits(user_rpm=2, tenant_rpm=100, tenant_tpm=10),
                          clock=lambda: clock[0])
    assert modes(admission, 4) == [Mode.FULL, Mode.FULL, Mode.KB_ONLY, Mode.THROTTLED]


# The degraded answer ----------------------------------------------------------------------------------------

PASSAGES = [("kb-1", "Reset links expire after one hour."), ("kb-2", "Use the sign-in page to reset."),
            ("kb-3", "Admins can reset any user."), ("kb-4", "Not shown.")]


def test_a_degraded_answer_comes_from_the_knowledge_base_with_a_disclaimer():
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return "Use the sign-in page [kb-2]."
    answer = degraded_answer(lambda q: PASSAGES, generate, "How do I reset my password?")
    assert answer.startswith(KB_DISCLAIMER) and "[kb-2]" in answer
    assert "[kb-1]" in prompts[0] and "[kb-4]" not in prompts[0]                  # the top three only
    assert "make no claim about the customer's account" in prompts[0]


def test_when_the_model_is_down_the_top_three_snippets_are_returned_as_they_are():
    def down(prompt):
        raise TimeoutError("all providers throttled")
    answer = degraded_answer(lambda q: PASSAGES, down, "How do I reset my password?")
    snippets = ("[kb-1] Reset links expire after one hour.\n\n[kb-2] Use the sign-in page to reset.\n\n"
                "[kb-3] Admins can reset any user.")
    assert answer == KB_DISCLAIMER + "\n\n" + snippets


def test_no_passage_no_guess():
    answer = degraded_answer(lambda q: [], lambda p: pytest.fail("no model call without evidence"), "Why?")
    assert "a person can help" in answer


def test_the_local_store_expires_entries():
    clock = [0.0]
    local = Local(lambda: clock[0])
    assert local.acquire("k", "a", 5) and not local.acquire("k", "b", 5)
    clock[0] = 5.0
    assert local.acquire("k", "b", 5) and local.holder("k") == "b"
    assert not local.release("k", "a") and not local.extend("k", "a", 5) and local.holder("k") == "b"
    assert local.extend("k", "b", 50) and local.release("k", "b") and local.holder("k") is None
    assert local.add("n", 3, 10) == 3 and local.read("n") == 3
    clock[0] = 20.0
    assert local.read("n") == 0
