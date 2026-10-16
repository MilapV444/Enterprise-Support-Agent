"""Jev decision model at the orchestrator's decision points (FR-5 / ADP-05).

Jev answers typed questions (choice, score, noul) about a narrow, PII-masked state and returns calibrated
probabilities; code keeps control flow, numbers and dates. Three gates: triage (see triage.py), FSM transition
guards, and tool selection. Every failure is fail-safe: a guard reads as "no", a tool pick as "none", and
triage falls back to the LLM classifier, then to "ask the customer".

Questions are written in the TypeSafe API's own shape (an id-keyed map of {type, instructions, criteria}) and
live here under version control; this file is a behaviour path (CI release gate).
"""

import json
import logging
import re
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

QUESTIONS_VERSION = "2026-10-15.1"
INTENTS = {
    "BILLING_INQUIRY": "Invoices, charges, payments or refunds",
    "TECHNICAL_OUTAGE": "Something is broken, failing or unavailable",
    "PASSWORD_RESET": "Cannot sign in or needs to reset a password",
    "SUBSCRIPTION_UPDATE": "Change, upgrade, downgrade or cancel a plan",
    "GENERAL_INQUIRY": "A question about the product or how to use it",
}
SEVERITY = ["Low: a question or minor inconvenience", "Moderate: a feature is impaired",
            "Significant: important work is blocked for one user", "Severe: work is blocked for many users",
            "Catastrophic: business-critical service is down"]
TRIAGE_QUESTIONS = {
    "intent": {"type": "choice", "instructions": "What is the primary customer intent?", "criteria": INTENTS},
    "severity": {"type": "score", "instructions": "How severe is the customer's problem?",
                 "criteria": SEVERITY},
    "missing_details": {"type": "noul",
                        "instructions": "Are details missing that are needed to act on this intent?",
                        "criteria": {"true": "Something the agent needs to act is not stated",
                                     "false": "Everything needed to act is stated"}},
}
TOOL_QUESTION = "Which tool is strictly required for the next diagnostic step?"
NO_TOOL = "NONE_REQUIRED"
THRESHOLDS = {"GUARD": 0.90, "TOOL_SELECTION": 0.80}  # ponytail: per-route YAML when calibration needs it
MAX_CHOICE_OPTIONS = 255

# Interim masking until the token vault (SG-ADP-02) replaces it; the same patterns guard the egress barrier.
PII = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"\+?\d[\d ().-]{7,}\d"),
}
NUMBERS = re.compile(r"[\d$€£¥%]")


class SecurityViolation(ValueError):
    pass


class JevUnavailable(RuntimeError):
    """Jev gave no usable answer: down, overloaded, timed out or malformed. Callers fail safe."""


class JevRejected(JevUnavailable):
    """Jev refused the request itself (bad key, malformed question, too large): a bug or config error."""


@dataclass(frozen=True)
class Masked:
    """Text that went through masking; the only kind of text a decision request may carry."""

    text: str


def mask(text):
    for label, pattern in PII.items():
        text = pattern.sub(f"<{label}>", text)
    return Masked(text)


def narrow(masked_state):
    """The state object for the request; refuses unmasked text and masked text that still holds PII."""
    plain = {}
    for key, value in masked_state.items():
        if isinstance(value, str):
            raise SecurityViolation(f"{key!r} is not masked")
        if isinstance(value, Masked):
            if any(pattern.search(value.text) for pattern in PII.values()):
                raise SecurityViolation(f"{key!r} still contains personal data")
            value = value.text
        plain[key] = value
    return plain


@dataclass
class Answer:
    """One answer, the same shape for every question type.

    choice: value = the chosen option. score: value = the weighted score, index = the most likely level.
    noul: value = yes / no at 0.5, confidence = the probability of that side.
    """

    value: object
    confidence: float
    index: int | None = None


def parse_answer(raw):
    """Answer from one entry of the API's `answers` map (docs: API reference, Answer types)."""
    kind = raw["type"]
    if kind == "choice":
        return Answer(raw["choice"], float(raw["confidence"]))
    if kind == "score":
        likeliest = max(raw["probabilities"].items(), key=lambda item: item[1])[0]
        return Answer(float(raw["score"]), float(raw["confidence"]), int(likeliest))
    if kind == "noul":
        p = float(raw["noul"])
        return Answer(p >= 0.5, p if p >= 0.5 else 1.0 - p)
    raise ValueError(f"unknown answer type {kind!r}")


class JevClient:
    """HTTP client for TypeSafe's System One endpoint (POST /v1/systemone).

    429 / 529 get one retry after a short back-off; other failures raise at once, inside the time budget a
    turn can afford. `last` keeps the serving model and token usage of the latest response for telemetry.
    """

    def __init__(self, api_key, model="jev-latest", base_url="https://api.typesafe.ai", timeout=3.0,
                 transport=None, backoff=0.5):
        self.model, self.backoff, self.last = model, backoff, {}
        self.http = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"},
                                 timeout=timeout, transport=transport)

    def evaluate(self, state, questions):
        body = {"state": state, "model": self.model, "questions": questions}
        for attempt in (1, 2):
            try:
                reply = self.http.post("/v1/systemone", json=body)
            except httpx.HTTPError as error:
                raise JevUnavailable(f"Jev unreachable: {error}") from error
            if reply.status_code in (429, 529) and attempt == 1:
                time.sleep(self.backoff)
                continue
            if reply.status_code in (400, 401, 413, 415, 422):
                log.error("Jev rejected the request (%s): %s", reply.status_code, reply.text[:500])
                raise JevRejected(f"Jev rejected the request: HTTP {reply.status_code}")
            if reply.status_code != 200:
                raise JevUnavailable(f"Jev returned HTTP {reply.status_code}")
            try:
                payload = reply.json()
                answers = {qid: parse_answer(raw) for qid, raw in payload["answers"].items()}
            except (KeyError, TypeError, ValueError) as error:
                raise JevUnavailable(f"malformed Jev response: {error}") from error
            self.last = {"model": payload.get("model"), "usage": payload.get("usage")}
            return answers


def checked(answers, questions):
    """The answers if every question got a valid one; JevUnavailable otherwise."""
    for qid, question in questions.items():
        answer = answers.get(qid)
        if answer is None or not 0.0 <= answer.confidence <= 1.0:
            raise JevUnavailable(f"no valid answer for {qid}")
        if question["type"] == "choice" and answer.value not in question["criteria"]:
            raise JevUnavailable(f"{answer.value!r} is not an option of {qid}")
        if question["type"] == "score" and answer.index not in range(len(question["criteria"])):
            raise JevUnavailable(f"score level {answer.index!r} out of range for {qid}")
        if question["type"] == "noul" and not isinstance(answer.value, bool):
            raise JevUnavailable(f"{qid} needs a yes / no answer")
    return answers


class DecisionEngine:
    def __init__(self, jev, thresholds=None):
        self.jev, self.thresholds = jev, {**THRESHOLDS, **(thresholds or {})}

    def ask(self, masked_state, questions):
        """Answers to `questions` ({id: question}); raises JevUnavailable when Jev cannot answer them."""
        for qid, question in questions.items():
            criteria = question.get("criteria") or []
            descriptions = list(criteria.values()) if isinstance(criteria, dict) else list(criteria)
            wording = json.dumps([question["instructions"], *descriptions], ensure_ascii=False)
            if NUMBERS.search(wording):  # option labels (e.g. tool names) may contain digits
                raise ValueError(f"numbers and money stay in code, not in Jev questions: {qid}")
        return checked(self.jev.evaluate(narrow(masked_state), questions), questions)

    def guard(self, guard_id, question, masked_state, min_confidence=None):
        """Gate 2: may the FSM take this edge? Anything short of a confident yes is no."""
        try:
            answer = self.ask(masked_state, {guard_id: {"type": "noul", "instructions": question}})[guard_id]
        except JevUnavailable:
            return False
        return answer.value is True and answer.confidence >= (min_confidence or self.thresholds["GUARD"])

    def select_tool(self, candidates, masked_state):
        """Gate 3: one tool from the shortlist ({name: description} or names), or None (-> a human)."""
        if not candidates:
            return None
        options = dict(candidates) if isinstance(candidates, dict) else dict.fromkeys(candidates)
        if len(options) >= MAX_CHOICE_OPTIONS:
            raise ValueError(f"a choice takes at most {MAX_CHOICE_OPTIONS} options")
        question = {"type": "choice", "instructions": TOOL_QUESTION,
                    "criteria": {**options, NO_TOOL: "No tool is needed for the next step"}}
        try:
            answer = self.ask(masked_state, {"tool": question})["tool"]
        except JevUnavailable:
            return None
        confident = answer.confidence >= self.thresholds["TOOL_SELECTION"]
        return answer.value if confident and answer.value != NO_TOOL else None
