"""M5-01: tail sampling (errors, escalations, risk tier and slow traces kept with content; a 5% baseline
without content), PII scrubbing before export, pseudonymous user ids, OTLP export to Jaeger and Langfuse, JSON
logs with trace ids, and erasure of a user's Langfuse traces (NFR-11, NFR-12)."""

import base64
import io
import json
import logging
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from observability.tracing import (
    JsonFormatter,
    LangfuseEraser,
    TailSampler,
    exporters,
    provider,
    subject_hash,
    turn_attributes,
)

ROOT = Path(__file__).resolve().parents[3]
PROMPT = "Customer sarah@acme.com asks why card 4111 1111 1111 1111 was charged twice; token <EMAIL_1a2b3c4d>"


def tracer(**options):
    memory = InMemorySpanExporter()
    tracer_provider = provider("support-agent-test", targets=[memory], **options)
    return tracer_provider.get_tracer("test"), memory, tracer_provider


def run_turn(tracer_, *, error=False, root_attributes=None, child_attributes=None, seconds=0.01):
    start = time.time_ns()
    root = tracer_.start_span("turn", attributes={**turn_attributes("t_us", "sarah", "conv-1"),
                                                  **(root_attributes or {})}, start_time=start)
    from opentelemetry import trace as api
    with api.use_span(root, end_on_exit=False):
        with tracer_.start_as_current_span("llm.chat", attributes={"gen_ai.request.model": "small",
                                                                   "gen_ai.prompt": PROMPT,
                                                                   "gen_ai.usage.input_tokens": 42,
                                                                   **(child_attributes or {})}) as child:
            if error:
                child.record_exception(ValueError("CRM refused account for sarah@acme.com"))
                child.set_status(Status(StatusCode.ERROR, "lookup failed for sarah@acme.com"))
    root.end(end_time=start + int(seconds * 1e9))


def by_name(memory):
    return {span.name: span for span in memory.get_finished_spans()}


# Tail sampling ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("turn", [
    {"error": True},
    {"root_attributes": {"support.escalated": True}},
    {"child_attributes": {"agent.risk_tier": "risk"}},
    {"seconds": 2.6},
])
def test_errors_escalations_risk_and_slow_traces_are_kept_whole_with_content(turn):
    tracer_, memory, _ = tracer(baseline=0.0)
    run_turn(tracer_, **turn)
    spans = by_name(memory)
    assert set(spans) == {"turn", "llm.chat"}
    assert "gen_ai.prompt" in spans["llm.chat"].attributes                   # content kept (scrubbed)


def test_a_routine_trace_is_dropped_unless_it_falls_in_the_baseline_which_keeps_no_content():
    tracer_, memory, _ = tracer(baseline=0.0)
    run_turn(tracer_)
    assert memory.get_finished_spans() == ()
    tracer_, memory, _ = tracer(baseline=1.0)
    run_turn(tracer_)
    chat = by_name(memory)["llm.chat"]
    assert "gen_ai.prompt" not in chat.attributes and chat.attributes["gen_ai.usage.input_tokens"] == 42


def test_the_baseline_is_five_percent_and_deterministic_per_trace():
    sampler = TailSampler(InMemorySpanExporter())
    assert sampler.baseline_pick(10_000 * 7 + 499) and not sampler.baseline_pick(10_000 * 7 + 500)
    picked = sum(sampler.baseline_pick(trace_id) for trace_id in range(100_000))
    assert picked == 5_000


def test_a_trace_whose_root_never_ends_is_decided_when_the_buffer_fills_or_on_flush():
    tracer_, memory, tracer_provider = tracer(baseline=0.0, max_traces=1)
    from opentelemetry import trace as api
    roots = [tracer_.start_span(f"turn-{n}") for n in range(2)]
    for root in roots:
        with api.use_span(root, end_on_exit=False):
            with tracer_.start_as_current_span("tool") as span:
                span.set_status(Status(StatusCode.ERROR))
    assert [s.name for s in memory.get_finished_spans()] == ["tool"]        # the oldest left the buffer
    tracer_provider.force_flush()
    assert [s.name for s in memory.get_finished_spans()] == ["tool", "tool"]


# Scrubbing --------------------------------------------------------------------------------------------------

def test_no_raw_personal_data_is_exported_and_masked_tokens_stay():
    tracer_, memory, _ = tracer(baseline=0.0)
    run_turn(tracer_, error=True)
    chat = by_name(memory)["llm.chat"]
    exported = json.dumps([dict(s.attributes) for s in memory.get_finished_spans()]
                          + [dict(e.attributes) for e in chat.events] + [chat.status.description])
    assert "sarah@acme.com" not in exported and "4111 1111 1111 1111" not in exported
    assert "[REDACTED_EMAIL]" in chat.attributes["gen_ai.prompt"]
    assert "[REDACTED_CARD]" in chat.attributes["gen_ai.prompt"]
    assert "<EMAIL_1a2b3c4d>" in chat.attributes["gen_ai.prompt"]           # upstream tokens are not personal
    assert chat.status.description == "lookup failed for [REDACTED_EMAIL]"
    assert "[REDACTED_EMAIL]" in chat.events[0].attributes["exception.message"]


def test_spans_name_the_user_only_by_the_erasure_ledgers_pseudonym():
    tracer_, memory, _ = tracer(baseline=0.0)
    run_turn(tracer_, error=True)
    turn = by_name(memory)["turn"]
    assert turn.attributes["user.id"] == subject_hash("t_us", "sarah") != "sarah"
    assert "sarah" not in json.dumps(dict(turn.attributes))
    from data.erasure import subject_hash as ledger_hash
    assert subject_hash("t_us", "sarah") == ledger_hash("t_us", "sarah")


# Export configuration ---------------------------------------------------------------------------------------

def test_exporters_are_configured_from_the_environment():
    assert exporters({}) == []
    found = exporters({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4318/",
                       "LANGFUSE_HOST": "https://lf.test", "LANGFUSE_PUBLIC_KEY": "pk-1",
                       "LANGFUSE_SECRET_KEY": "sk-1"})
    assert [e._endpoint for e in found] == ["http://jaeger:4318/v1/traces",
                                            "https://lf.test/api/public/otel/v1/traces"]
    sent = found[1]._client._headers["authorization"]                       # what each request carries
    assert sent == "Basic " + base64.b64encode(b"pk-1:sk-1").decode()
    assert exporters({"LANGFUSE_HOST": "https://lf.test", "LANGFUSE_PUBLIC_KEY": "pk-1"}) == []  # no secret


def test_a_scrubbed_trace_reaches_the_compose_jaeger():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "jaeger"], cwd=ROOT, check=True, capture_output=True)
    service = f"support-agent-test-{uuid.uuid4().hex[:8]}"
    targets = exporters({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318"})
    tracer_provider = provider(service, targets=targets, baseline=0.0)
    run_turn(tracer_provider.get_tracer("test"), error=True)
    tracer_provider.shutdown()
    traces = []
    for _ in range(30):
        found = httpx.get("http://127.0.0.1:16686/api/traces", params={"service": service})
        traces = found.json().get("data")
        if traces:
            break
        time.sleep(1)
    assert traces and len(traces[0]["spans"]) == 2
    stored = json.dumps(traces)
    assert "sarah@acme.com" not in stored and "[REDACTED_EMAIL]" in stored


# Logs -------------------------------------------------------------------------------------------------------

def test_json_logs_carry_the_trace_and_no_raw_personal_data():
    tracer_, _, _ = tracer(baseline=1.0)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("tracing-test")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        with tracer_.start_as_current_span("turn") as span:
            who = {"tenant_id": "t_us", "user_hash": subject_hash("t_us", "sarah")}
            log.info("refund asked by %s", "sarah@acme.com", extra=who)
            try:
                raise RuntimeError("card 4111 1111 1111 1111 declined")
            except RuntimeError:
                log.exception("payment failed")
        first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    finally:
        log.removeHandler(handler)
    context = span.get_span_context()
    assert first["trace_id"] == f"{context.trace_id:032x}" and first["span_id"] == f"{context.span_id:016x}"
    assert first["message"] == "refund asked by [REDACTED_EMAIL]" and first["tenant_id"] == "t_us"
    assert first["level"] == "INFO" and first["timestamp"].endswith("Z")
    assert "4111" not in second["exception"] and "[REDACTED_CARD]" in second["exception"]


# Erasure by ID ----------------------------------------------------------------------------------------------

class FakeLangfuse:
    def __init__(self, traces, page_size=2, keep=()):
        self.traces, self.page_size, self.keep, self.requests = dict(traces), page_size, set(keep), []

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            user = request.url.params["userId"]
            page = int(request.url.params["page"])
            mine = [t for t, owner in self.traces.items() if owner == user]
            total = max(1, -(-len(mine) // self.page_size))
            chunk = mine[(page - 1) * self.page_size: page * self.page_size]
            body = {"data": [{"id": t} for t in chunk], "meta": {"totalPages": total}}
            return httpx.Response(200, json=body)
        trace_id = request.url.path.rsplit("/", 1)[-1]
        if trace_id not in self.keep:
            self.traces.pop(trace_id, None)
        return httpx.Response(200, json={"message": "deleted"})


def test_a_users_langfuse_traces_are_deleted_and_verified_gone():
    sarah, bob = subject_hash("t_us", "sarah"), subject_hash("t_us", "bob")
    fake = FakeLangfuse({"tr-1": sarah, "tr-2": sarah, "tr-3": sarah, "tr-4": bob})
    eraser = LangfuseEraser("https://lf.test", "pk-1", "sk-1", transport=httpx.MockTransport(fake))
    assert eraser.erase("t_us", "sarah") == 3
    assert fake.traces == {"tr-4": bob}
    assert all(r.headers["Authorization"] == "Basic " + base64.b64encode(b"pk-1:sk-1").decode()
               for r in fake.requests)
    assert all("sarah" not in str(r.url) for r in fake.requests)                 # asked by pseudonym only


def test_a_trace_that_survives_deletion_fails_the_erasure():
    sarah = subject_hash("t_us", "sarah")
    fake = FakeLangfuse({"tr-1": sarah}, keep={"tr-1"})
    with pytest.raises(RuntimeError, match="still there"):
        eraser = LangfuseEraser("https://lf.test", "pk", "sk", transport=httpx.MockTransport(fake))
        eraser.erase("t_us", "sarah")
