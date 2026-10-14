"""Jev decision model at the orchestrator's decision points (FR-5 / ADP-05).

Jev answers typed questions (choice, score, noul) about a narrow, PII-masked state and returns calibrated
confidences; code keeps control flow, numbers and dates. Three gates: triage (see triage.py), FSM transition
guards, and tool selection. Every failure is fail-safe: a guard reads as "no", a tool pick as "none", and
triage falls back to the LLM classifier, then to "ask the customer".

Question wording lives here, under version control, and this file is a behaviour path (CI release gate).
"""

import re
from dataclasses import dataclass

import httpx

QUESTIONS_VERSION = "2026-10-14.1"
INTENTS = ("BILLING_INQUIRY", "TECHNICAL_OUTAGE", "PASSWORD_RESET", "SUBSCRIPTION_UPDATE", "GENERAL_INQUIRY")
SEVERITY = ("LOW", "MODERATE", "SIGNIFICANT", "SEVERE", "CATASTROPHIC")
TRIAGE_QUESTIONS = (
    {"id": "intent", "type": "choice", "question": "What is the primary customer intent?",
     "options": INTENTS},
    {"id": "severity", "type": "score", "question": "How severe is the customer's problem?",
     "levels": SEVERITY},
    {"id": "missing_details", "type": "noul",
     "question": "Are details missing that are needed to act on this intent?"},
)
TOOL_QUESTION = "Which tool is strictly required for the next diagnostic step?"
THRESHOLDS = {"GUARD": 0.90, "TOOL_SELECTION": 0.80}  # ponytail: per-route YAML when calibration needs it

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
    pass


@dataclass(frozen=True)
class Masked:
    """Text that went through masking; the only kind of text a decision request may carry."""

    text: str


def mask(text):
    for label, pattern in PII.items():
        text = pattern.sub(f"<{label}>", text)
    return Masked(text)


def narrow(masked_state):
    """Plain dict for the request; refuses unmasked text and masked text that still holds PII."""
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
    value: object
    confidence: float
    index: int | None = None


class JevClient:
    """HTTP client for the hosted Jev API.

    ponytail: assumed contract (ASSUMPTION in Genesis) until the TypeSafe API docs are in hand:
    POST {base_url}/v1/evaluate {"state", "questions", "version"}
      -> {"answers": {id: {"value", "confidence", "index"}}}
    """

    def __init__(self, base_url, api_key, timeout=3.0, transport=None):
        self.http = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"},
                                 timeout=timeout, transport=transport)

    def evaluate(self, state, questions):
        try:
            reply = self.http.post("/v1/evaluate", json={"state": state, "questions": list(questions),
                                                         "version": QUESTIONS_VERSION})
            reply.raise_for_status()
            return {qid: Answer(a["value"], float(a["confidence"]), a.get("index"))
                    for qid, a in reply.json()["answers"].items()}
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise JevUnavailable(str(error)) from error


def checked(answers, questions):
    """The answers if every question got a valid one; JevUnavailable otherwise."""
    for question in questions:
        answer = answers.get(question["id"])
        if answer is None or not 0.0 <= answer.confidence <= 1.0:
            raise JevUnavailable(f"no valid answer for {question['id']}")
        if question["type"] == "choice" and answer.value not in question["options"]:
            raise JevUnavailable(f"{answer.value!r} is not an option of {question['id']}")
        if question["type"] == "score" and answer.index not in range(len(question["levels"])):
            raise JevUnavailable(f"score index {answer.index!r} out of range for {question['id']}")
        if question["type"] == "noul" and not isinstance(answer.value, bool):
            raise JevUnavailable(f"{question['id']} needs a yes / no answer")
    return answers


class DecisionEngine:
    def __init__(self, jev, thresholds=None):
        self.jev, self.thresholds = jev, {**THRESHOLDS, **(thresholds or {})}

    def ask(self, masked_state, questions):
        """Answers to `questions`; raises JevUnavailable when Jev cannot answer them."""
        for question in questions:
            if NUMBERS.search(question["question"]):
                raise ValueError(f"numbers and money stay in code, not in Jev questions: {question['id']}")
        return checked(self.jev.evaluate(narrow(masked_state), questions), questions)

    def guard(self, guard_id, question, masked_state, min_confidence=None):
        """Gate 2: may the FSM take this edge? Anything short of a confident yes is no."""
        try:
            question = {"id": guard_id, "type": "noul", "question": question}
            answer = self.ask(masked_state, [question])[guard_id]
        except JevUnavailable:
            return False
        return answer.value is True and answer.confidence >= (min_confidence or self.thresholds["GUARD"])

    def select_tool(self, candidates, masked_state):
        """Gate 3: one tool from the shortlist, or None (which sends diagnosis to a human)."""
        if not candidates:
            return None
        question = {"id": "tool", "type": "choice", "question": TOOL_QUESTION,
                    "options": (*candidates, "NONE_REQUIRED")}
        try:
            answer = self.ask(masked_state, [question])["tool"]
        except JevUnavailable:
            return None
        confident = answer.confidence >= self.thresholds["TOOL_SELECTION"]
        return answer.value if confident and answer.value != "NONE_REQUIRED" else None
