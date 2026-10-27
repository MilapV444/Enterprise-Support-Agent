"""M4-02: request coalescing for identical reads, incident mode with the status answer, and latency budgets
per route (NFR-18 / RP-ADP-03)."""

import threading
import time

import pytest

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable, Masked
from reliability.bursts import (
    BUDGETS,
    Budget,
    Deadline,
    Incident,
    Incidents,
    SingleFlight,
    flight_key,
    incident_answer,
)

# Coalescing -------------------------------------------------------------------------------------------------

class Backend:
    def __init__(self, delay=0.1, fail=False):
        self.calls, self.delay, self.fail, self.lock = 0, delay, fail, threading.Lock()

    def __call__(self):
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise TimeoutError("status page timed out")
        return {"status": "degraded"}


def burst(flight, n, call, tenant="t_us", arguments=None, read_only=True):
    start, results = threading.Barrier(n), [None] * n

    def one(i):
        start.wait()
        try:
            results[i] = flight.run(tenant if isinstance(tenant, str) else tenant[i], "status.check",
                                    arguments or {"q": "Is login down?"}, call, read_only)
        except Exception as error:  # noqa: BLE001
            results[i] = error
    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_fifty_identical_reads_make_one_backend_call_and_all_get_its_answer():
    backend = Backend()
    results = burst(SingleFlight(), 50, backend)
    assert backend.calls == 1 and results == [{"status": "degraded"}] * 50


def test_every_waiter_sees_the_leaders_failure_and_the_next_burst_tries_again():
    flight, backend = SingleFlight(), Backend(fail=True)
    results = burst(flight, 10, backend)
    assert backend.calls == 1 and all(isinstance(r, TimeoutError) for r in results)
    backend.fail = False
    again = flight.run("t_us", "status.check", {"q": "Is login down?"}, backend, True)
    assert again == {"status": "degraded"}
    assert backend.calls == 2


def test_the_query_is_normalised_but_tenants_and_actions_never_share_a_call():
    assert flight_key("t_us", "kb.search", {"q": "  Is LOGIN   down? "}) == \
        flight_key("t_us", "kb.search", {"q": "is login down?"})
    assert flight_key("t_us", "kb.search", {"q": "x"}) != flight_key("t_eu", "kb.search", {"q": "x"})
    assert flight_key("t_us", "kb.search", {"q": "x"}) != flight_key("t_us", "status.check", {"q": "x"})
    backend = Backend()
    burst(SingleFlight(), 4, backend, tenant=["t_us", "t_eu", "t_us", "t_eu"])
    assert backend.calls == 2


def test_writes_are_never_coalesced():
    with pytest.raises(ValueError, match="only read-only"):
        SingleFlight().run("t_us", "billing.refund", {"amount": 5}, lambda: None, read_only=False)


def test_a_call_still_running_after_the_window_does_not_take_new_callers():
    clock = [0.0]
    flight = SingleFlight(clock=lambda: clock[0])
    release, started = threading.Event(), threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "old"
    leader = threading.Thread(target=lambda: flight.run("t_us", "a", {}, slow, True))
    leader.start()
    started.wait(5)
    clock[0] = 0.25                                             # past the 200 ms window
    assert flight.run("t_us", "a", {}, lambda: "fresh", True) == "fresh"
    release.set()
    leader.join()


# Incident mode ----------------------------------------------------------------------------------------------

STATUS = ("We are investigating sign-in failures in the EU. Engineers are deploying a fix; updates follow "
          "here.")
EU_LOGIN = Incident("Network degradation in the EU region causing sign-in timeouts", STATUS,
                    tenants=frozenset({"t_eu"}), declared_by="oncall-ana")


class Jev:
    def __init__(self, p_yes=0.95, down=False):
        self.p_yes, self.down, self.seen = p_yes, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"incident": Answer(self.p_yes >= 0.5, max(self.p_yes, 1 - self.p_yes))}


def desk(incident=EU_LOGIN):
    incidents = Incidents()
    incidents.declare(incident)
    return incidents


def test_a_question_about_the_incident_gets_the_status_answer_without_the_agent():
    jev = Jev()
    answer = incident_answer(DecisionEngine(jev), desk(), "t_eu", Masked("I can't log in since this morning"))
    assert answer == STATUS
    assert jev.seen[0]["incident"] == EU_LOGIN.brief
    assert jev.seen[0]["message"] == "I can't log in since this morning"


@pytest.mark.parametrize("p_yes, expected", [(0.80, STATUS), (0.79, None), (0.2, None)])
def test_only_a_confident_match_is_diverted(p_yes, expected):
    assert incident_answer(DecisionEngine(Jev(p_yes)), desk(), "t_eu", Masked("Login broken?")) == expected


def test_no_incident_another_tenant_or_jev_down_means_the_normal_path():
    message = Masked("Login broken?")
    assert incident_answer(DecisionEngine(Jev()), Incidents(), "t_eu", message) is None
    assert incident_answer(DecisionEngine(Jev()), desk(), "t_us", message) is None
    assert incident_answer(DecisionEngine(Jev(down=True)), desk(), "t_eu", message) is None
    everyone = Incident("Global outage", STATUS)
    assert incident_answer(DecisionEngine(Jev()), desk(everyone), "t_us", message) == STATUS


def test_a_cleared_incident_diverts_nothing():
    incidents = desk()
    incidents.clear()
    assert incident_answer(DecisionEngine(Jev()), incidents, "t_eu", Masked("Login broken?")) is None


def test_the_status_answer_still_passes_the_output_checks():
    leaky = Incident("Outage", "Use the admin key sk_live_4eC39HqLyjWDarjtT1zdp7dc meanwhile.")
    assert incident_answer(DecisionEngine(Jev()), desk(leaky), "t_eu", Masked("Login broken?")) is None
    linked = Incident("Outage", "Status: http://status.example.net/eu")
    answer = incident_answer(DecisionEngine(Jev()), desk(linked), "t_eu", Masked("Login broken?"))
    assert answer == "Status: [link removed]"


# Latency budgets --------------------------------------------------------------------------------------------

def test_the_route_budgets_are_the_decided_ones_and_their_steps_fit():
    assert {r: (b.target, b.hard) for r, b in BUDGETS.items()} == {
        "faq": (5.0, 8.0), "diagnostic": (20.0, 28.0), "multi_specialist": (45.0, 60.0)}
    assert all(sum(b.steps.values()) <= b.target for b in BUDGETS.values())
    for bad in ({"target": 5.0, "hard": 4.0}, {"target": 5.0, "hard": 8.0, "steps": {"a": 6.0}},
                {"target": 0.0, "hard": 8.0}):
        with pytest.raises(ValueError):
            Budget("x", fallback="f", **bad)


def test_a_slow_retrieval_on_an_faq_turn_skips_reranking_to_stay_within_five_seconds():
    clock = [0.0]
    deadline = Deadline("faq", clock=lambda: clock[0])
    after = ("generation", "safety")
    assert deadline.status_due() == 1.0
    clock[0] = 2.0                                     # retrieval on time
    assert deadline.fits("rerank", then=after)         # 2.0 + 0.5 + 1.5 + 0.3 <= 5
    clock[0] = 3.5                                     # retrieval took 3.5 s, not its 2 s
    assert deadline.status_due() == 0.0
    assert not deadline.fits("rerank", then=after)     # 3.5 + 0.5 + 1.8 > 5: skip it
    assert deadline.timeout("generation") == 1.5        # the required steps still get their time


def test_step_timeouts_never_run_past_the_hard_ceiling_and_then_the_fallback_applies():
    clock = [0.0]
    deadline = Deadline("faq", clock=lambda: clock[0])
    assert deadline.timeout("generation") == 1.5
    clock[0] = 7.5
    assert deadline.timeout("generation") == pytest.approx(0.5) and not deadline.expired()
    clock[0] = 8.0
    assert deadline.timeout("generation") == 0 and deadline.expired()
    assert deadline.budget.fallback == "top_snippet"
    assert BUDGETS["multi_specialist"].fallback == "human_co_pilot"
