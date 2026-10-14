"""Gate 1: triage of the latest customer message (ADP-05 into the ADP-01 TRIAGED node).

Jev answers the triage question set in one request; code maps intent and severity onto the statechart's
acuity levels. When Jev is down, an LLM classifier answers the same questions, but its confidence is capped
below the 0.90 an SOP needs, so a fallback guess never runs a procedure on its own. If both fail, the result
asks the customer (acuity 3, confidence 0).
"""

import json

from core.orchestrator.decisions import (
    INTENTS,
    SEVERITY,
    TRIAGE_QUESTIONS,
    Answer,
    JevUnavailable,
    checked,
    mask,
)

SOP_INTENTS = {"BILLING_INQUIRY": "billing_inquiry", "PASSWORD_RESET": "password_reset",
               "SUBSCRIPTION_UPDATE": "subscription_update"}
FALLBACK_MAX_CONFIDENCE = 0.89
ASK_CUSTOMER = {"intent": "UNKNOWN", "acuity": 3, "confidence": 0.0, "missing_params": True,
                "rationale": "no decision available"}


def triage(engine, masked_state, fallback=None):
    """Triage-shaped dict for the statechart (schemas.thread_state.Triage)."""
    source = "jev"
    try:
        answers = engine.ask(masked_state, TRIAGE_QUESTIONS)
    except JevUnavailable:
        if fallback is None:
            return ASK_CUSTOMER
        try:
            answers, source = checked(fallback(masked_state), TRIAGE_QUESTIONS), "fallback"
        except JevUnavailable:
            return ASK_CUSTOMER
    intent, severity = answers["intent"].value, answers["severity"].index
    confidence = min(answers["intent"].confidence, answers["severity"].confidence)
    if source == "fallback":
        confidence = min(confidence, FALLBACK_MAX_CONFIDENCE)
    if intent in SOP_INTENTS:
        acuity = 1 if severity >= 3 else 2
    else:
        acuity = 5 if severity >= 3 else 4
    return {"intent": intent, "acuity": acuity, "confidence": confidence,
            "missing_params": answers["missing_details"].value is True, "sop_name": SOP_INTENTS.get(intent),
            "rationale": f"{source}: {intent}, severity {SEVERITY[severity]}"}


def llm_fallback(complete):
    """Fallback classifier over `complete(prompt) -> str`, any chat model returning JSON."""
    def classify(masked_state):
        prompt = (
            "Classify the customer message. Reply with JSON only: "
            '{"intent": one of ' + json.dumps(INTENTS) + ', "severity": index into ' + json.dumps(SEVERITY)
            + ', "missing_details": true or false, "confidence": 0 to 1}\n\nMessage: '
            + masked_state["message"].text
        )
        try:
            reply = json.loads(complete(prompt))
            confidence = float(reply["confidence"])
            return {"intent": Answer(reply["intent"], confidence),
                    "severity": Answer(SEVERITY[int(reply["severity"])], confidence, int(reply["severity"])),
                    "missing_details": Answer(reply["missing_details"], confidence)}
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise JevUnavailable(f"fallback classifier: {error}") from error
    return classify


def triage_hook(engine, fallback=None):
    """The statechart's `triage(state)` hook: masks the latest message and triages it."""
    def hook(state):
        messages = state.get("messages") or [{}]
        return triage(engine, {"message": mask(messages[-1].get("content", ""))}, fallback)
    return hook
