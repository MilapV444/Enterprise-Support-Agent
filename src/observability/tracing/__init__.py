"""Tracing and logs (NFR-11 / OB-ADP-01: OB-D1, OB-D3, OB-D4, OB-D14; NFR-12 / OB-ADP-02: OB-D2, OB-D5, OB-D6,
OB-D12), in-process in v1: there is no separate collector, so the scrubbing and the tail sampling run in the
service before anything is exported.

- TailSampler (a span processor): buffers a trace until its root span ends, then keeps it whole when any span
  errored, it was escalated (support.escalated), it touched the risk tier (agent.risk_tier = "risk") or it
  was slow (root > 2.5 s), with its content; otherwise a deterministic 5% of traces (by trace id) are kept
  with their content attributes stripped, and the rest dropped. A trace whose root never ends is decided
  when the buffer is full or on flush.
- ScrubbingExporter: before export, every string in span attributes, event attributes and the status
  description goes through the PII recognizers (safety.pii); raw values become [REDACTED_<KIND>]. Tokens
  already masked upstream stay as they are.
- exporters(): OTLP over HTTP to Jaeger, and to Langfuse's OTLP endpoint with Basic auth (DECISION-9da2e064).
- Spans and logs name the user only by subject_hash(tenant, principal), the hash the erasure ledger uses, so
  no telemetry store holds a direct identifier; Langfuse traces carry it as user.id, so LangfuseEraser can
  delete a user's traces and verify that none are left (OB-D6).
- JsonFormatter: one JSON object per log line with the current trace_id and span_id, the message scrubbed.
"""

import base64
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from safety.pii.tokens import find as find_pii

SLOW_SECONDS = 2.5
BASELINE = 0.05
MAX_BUFFERED_TRACES = 10_000
CONTENT_KEYS = ("gen_ai.prompt", "gen_ai.completion", "input.value", "output.value")
CONTENT_PREFIX = "content."


def subject_hash(tenant_id, principal_id):
    """The same pseudonym as data.erasure.subject_hash: telemetry never holds the principal id itself."""
    return hashlib.sha256(f"{tenant_id}\x1f{principal_id}".encode()).hexdigest()


def scrub(value):
    if isinstance(value, str):
        for start, end, kind, _ in reversed(find_pii(value)):
            value = value[:start] + f"[REDACTED_{kind}]" + value[end:]
        return value
    if isinstance(value, (list, tuple)):
        return type(value)(scrub(item) for item in value)
    return value


def _copy(span, attributes, events=None, status=None):
    return ReadableSpan(name=span.name, context=span.context, parent=span.parent, resource=span.resource,
                        attributes=attributes, events=span.events if events is None else events,
                        links=span.links, kind=span.kind, status=span.status if status is None else status,
                        start_time=span.start_time, end_time=span.end_time,
                        instrumentation_scope=span.instrumentation_scope)


def is_content(key):
    return key in CONTENT_KEYS or key.startswith(CONTENT_PREFIX)


class ScrubbingExporter(SpanExporter):
    """Wraps an exporter: no raw personal data leaves the process."""

    def __init__(self, inner):
        self.inner = inner

    def export(self, spans):
        clean = []
        for span in spans:
            attributes = {k: scrub(v) for k, v in (span.attributes or {}).items()}
            events = [Event(e.name, {k: scrub(v) for k, v in (e.attributes or {}).items()}, e.timestamp)
                      for e in span.events]
            status = span.status
            if status.description:
                status = type(status)(status.status_code, scrub(status.description))
            clean.append(_copy(span, attributes, events, status))
        return self.inner.export(clean)

    def shutdown(self):
        self.inner.shutdown()

    def force_flush(self, timeout_millis=30_000):
        return self.inner.force_flush(timeout_millis)


class TailSampler(SpanProcessor):
    def __init__(self, exporter, baseline=BASELINE, slow_seconds=SLOW_SECONDS,
                 max_traces=MAX_BUFFERED_TRACES):
        self.exporter, self.baseline, self.slow = exporter, baseline, slow_seconds
        self.max_traces, self.lock, self.traces = max_traces, threading.Lock(), OrderedDict()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        trace_id = span.context.trace_id
        with self.lock:
            self.traces.setdefault(trace_id, []).append(span)
            done = [self.traces.pop(trace_id)] if span.parent is None else []
            while len(self.traces) > self.max_traces:
                done.append(self.traces.popitem(last=False)[1])
        for spans in done:
            self._decide(spans)

    def keep_reason(self, spans):
        """Why a whole trace is kept with content, or None."""
        if any(s.status.status_code is StatusCode.ERROR for s in spans):
            return "error"
        if any((s.attributes or {}).get("support.escalated") is True for s in spans):
            return "escalated"
        if any((s.attributes or {}).get("agent.risk_tier") == "risk" for s in spans):
            return "risk_tier"
        roots = [s for s in spans if s.parent is None]
        if roots and (roots[0].end_time - roots[0].start_time) / 1e9 > self.slow:
            return "slow"
        return None

    def baseline_pick(self, trace_id):
        return (trace_id % 10_000) < self.baseline * 10_000   # deterministic per trace id

    def _decide(self, spans):
        if self.keep_reason(spans):
            self.exporter.export(spans)
        elif self.baseline_pick(spans[0].context.trace_id):
            bare = [_copy(s, {k: v for k, v in (s.attributes or {}).items() if not is_content(k)}, events=[])
                    for s in spans]
            self.exporter.export(bare)

    def force_flush(self, timeout_millis=30_000):
        with self.lock:
            pending, self.traces = list(self.traces.values()), OrderedDict()
        for spans in pending:
            self._decide(spans)
        return True

    def shutdown(self):
        self.force_flush()
        self.exporter.shutdown()


def exporters(environ=None):
    """The configured OTLP exporters: Jaeger (OTEL_EXPORTER_OTLP_ENDPOINT) and Langfuse (LANGFUSE_*)."""
    environ = os.environ if environ is None else environ
    found = []
    if environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        jaeger = environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces"
        found.append(OTLPSpanExporter(endpoint=jaeger))
    if all(environ.get(name) for name in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
        pair = f"{environ['LANGFUSE_PUBLIC_KEY']}:{environ['LANGFUSE_SECRET_KEY']}".encode()
        langfuse = environ["LANGFUSE_HOST"].rstrip("/") + "/api/public/otel/v1/traces"
        found.append(OTLPSpanExporter(endpoint=langfuse,
                                      headers={"Authorization": "Basic " + base64.b64encode(pair).decode()}))
    return found


class Fanout(SpanExporter):
    def __init__(self, inner):
        self.inner = list(inner)

    def export(self, spans):
        results = [exporter.export(spans) for exporter in self.inner]
        return SpanExportResult.SUCCESS if all(r is SpanExportResult.SUCCESS for r in results) \
            else SpanExportResult.FAILURE

    def shutdown(self):
        for exporter in self.inner:
            exporter.shutdown()

    def force_flush(self, timeout_millis=30_000):
        return all(exporter.force_flush(timeout_millis) for exporter in self.inner)


def provider(service, targets=None, **sampler_options):
    """A TracerProvider whose spans are tail-sampled, then scrubbed, then sent to every target."""
    tracer_provider = TracerProvider(resource=Resource.create({"service.name": service}))
    sinks = Fanout(exporters() if targets is None else targets)
    tracer_provider.add_span_processor(TailSampler(ScrubbingExporter(sinks), **sampler_options))
    return tracer_provider


def turn_attributes(tenant_id, principal_id, conversation_id, **extra):
    """The identifying attributes of a turn's root span: pseudonymous only."""
    return {"tenant.id": tenant_id, "user.id": subject_hash(tenant_id, principal_id),
            "session.id": conversation_id, **extra}


# Logs -------------------------------------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the current trace context; the message is scrubbed."""

    def format(self, record):
        context = trace.get_current_span().get_span_context()
        line = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                + f".{int(record.msecs):03d}Z", "level": record.levelname, "logger": record.name,
                "message": scrub(record.getMessage())}
        if context.is_valid:
            line["trace_id"], line["span_id"] = f"{context.trace_id:032x}", f"{context.span_id:016x}"
        for name in ("tenant_id", "user_hash", "conversation_id"):
            if hasattr(record, name):
                line[name] = getattr(record, name)
        if record.exc_info:
            line["exception"] = scrub(self.formatException(record.exc_info))
        return json.dumps(line, ensure_ascii=False)


def json_logging(level=logging.INFO, stream=None):
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    return handler


# Erasure by ID ----------------------------------------------------------------------------------------------

class LangfuseEraser:
    """Deletes a user's traces from Langfuse through its public API and verifies none are left."""

    def __init__(self, host, public_key, secret_key, transport=None, timeout=10.0):
        self.http = httpx.Client(base_url=host.rstrip("/"), auth=(public_key, secret_key),
                                 transport=transport, timeout=timeout)

    def _trace_ids(self, user):
        ids, page = [], 1
        while True:
            response = self.http.get("/api/public/traces",
                                     params={"userId": user, "page": page, "limit": 100})
            response.raise_for_status()
            body = response.json()
            ids += [item["id"] for item in body.get("data", [])]
            if page >= body.get("meta", {}).get("totalPages", 1):
                return ids
            page += 1

    def erase(self, tenant_id, principal_id):
        """Delete every trace of the user; returns how many were deleted. Raises if any is left."""
        user = subject_hash(tenant_id, principal_id)
        ids = self._trace_ids(user)
        for trace_id in ids:
            self.http.delete(f"/api/public/traces/{trace_id}").raise_for_status()
        left = self._trace_ids(user)
        if left:
            raise RuntimeError(f"{len(left)} Langfuse traces of the user are still there")
        return len(ids)
