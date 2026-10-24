"""The confidence gate on draft replies (FR-35 / HL-ADP-01: HL-D1, HL-D2, HL-D13).

Every draft the agent wants to send passes here before delivery:

1. figures, in code: a draft that states money (currency symbols or codes, "dollars", "refund", "credit"),
   a percentage, or an SLA / uptime / response-time commitment can never be sent automatically; at best it
   goes to a human co-pilot, who checks the figure against the source. The text is normalised first (NFKC,
   zero-width characters, look-alike letters), so full-width digits and signs, a zero-width space inside
   "refund" or a Cyrillic letter in it do not slip past.
2. Jev, on masked text (the draft, the customer's question, the evidence passages and tool results), in one
   request: is every claim supported by the evidence (grounding, yes / no), and how directly does the draft
   answer the question (relevance, five levels). The confidence is
       c = P(grounded) x relevance x discount
   where the discount is 0.5 when any evidence was written by the agent rather than a person, or has no
   known provenance (KR-D16). If Jev cannot answer, the draft cannot be verified and goes to a co-pilot.
3. bands: send at c >= 0.90, co-pilot from 0.50, hand-off below. Thresholds are per route within the ADP's
   bounds. On a route with no staffed queue a co-pilot draft becomes a hand-off, so no customer waits on
   nobody.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from core.orchestrator.decisions import JevUnavailable, mask
from safety.screening.pipeline import normalise

AGENT_DISCOUNT = 0.5
CURRENCY = r"[$€£¥₹₩₽¢]|\b(?:usd|eur|gbp|inr|jpy|aud|cad|chf|cny)\b"
FIGURES = re.compile("|".join([
    rf"(?:{CURRENCY})\s*\d", rf"\d[\d,.]*\s*(?:{CURRENCY})",                   # $20, 20 EUR, 1,240.00 USD
    r"\d[\d,.]*\s*(?:%|percent\b|per\s*cent\b)",                                  # 99.9%, 15 percent
    r"\b(?:dollars?|euros?|pounds?|rupees?|yen|cents?|bucks)\b",                   # spelled-out money
    r"\b(?:refunds?|refunded|credits?|credited|reimburse\w*|chargebacks?|prorat\w*|discounts?)\b",
    r"\b(?:sla|service[\s-]level|uptime|availability|response[\s-]time|resolution[\s-]time)\b",
]), re.IGNORECASE)
GROUNDED = {"type": "noul",
            "instructions": "Is every factual claim in the draft strictly supported by the evidence passages "
                            "or the tool results?"}
RELEVANCE = {"type": "score", "instructions": "How directly does the draft answer the customer's question?",
             "criteria": ["Not at all: off topic or evasive", "Barely: touches the topic, answers nothing",
                          "Partly: answers some of the question", "Mostly: answers it with small gaps",
                          "Fully: answers exactly what was asked"]}


class Band(str, Enum):
    SEND = "send"
    CO_PILOT = "co_pilot"
    HANDOFF = "handoff"


@dataclass(frozen=True)
class Route:
    name: str = "default"
    send_at: float = 0.90
    handoff_below: float = 0.50
    staffed: bool = True

    def __post_init__(self):
        if not (0.80 <= self.send_at <= 0.99 and 0.10 <= self.handoff_below <= 0.70
                and self.handoff_below < self.send_at):
            raise ValueError(f"route {self.name}: thresholds outside the calibrated bounds")


@dataclass
class Verdict:
    band: Band
    confidence: float | None          # None when Jev could not score the draft
    grounded: float | None = None     # P(every claim is supported)
    relevance: float | None = None    # 0..1
    discount: float = 1.0
    figures: list[str] = field(default_factory=list)  # what the co-pilot must check, highlighted
    reasons: list[str] = field(default_factory=list)


DEFAULT_ROUTE = Route()


def sensitive_figures(text):
    """Money, percentage and SLA mentions in the draft, as they appear after normalisation."""
    return [match.group(0) for match in FIGURES.finditer(normalise(text))]


def evidence_discount(provenances):
    """KR-D16: agent-written or unlabelled evidence counts half."""
    return AGENT_DISCOUNT if any(p != "human" for p in provenances) else 1.0


def score(engine, draft, question, passages, tool_results):
    """(P(grounded), relevance 0..1) from Jev over masked text; JevUnavailable if it cannot answer."""
    state = {"draft": mask(draft), "question": mask(question),
             "evidence": mask("\n\n".join([*passages, *tool_results]) or "(no evidence)")}
    answers = engine.ask(state, {"grounded": GROUNDED, "relevance": RELEVANCE})
    grounded = answers["grounded"]
    p_grounded = grounded.confidence if grounded.value else 1 - grounded.confidence
    relevance = answers["relevance"].value / (len(RELEVANCE["criteria"]) - 1)
    return p_grounded, min(max(relevance, 0.0), 1.0)


def route(engine, draft, question, passages=(), tool_results=(), provenances=(), config=None):
    """The band for a draft. passages / tool_results: the evidence it was written from, as text;
    provenances: "human" or "agent" for each passage."""
    config = config or DEFAULT_ROUTE
    figures, reasons = sensitive_figures(draft), []
    passages, provenances = list(passages), list(provenances)
    labelled = len(provenances) >= len(passages)  # a passage without a provenance label counts as unknown
    discount = evidence_discount(provenances) if labelled else AGENT_DISCOUNT
    try:
        grounded, relevance = score(engine, draft, question, passages, list(tool_results))
    except JevUnavailable:
        grounded = relevance = confidence = None
        band = Band.CO_PILOT
        reasons.append("the draft could not be scored; a person checks it")
    else:
        confidence = grounded * relevance * discount
        band = (Band.SEND if confidence >= config.send_at else
                Band.CO_PILOT if confidence >= config.handoff_below else Band.HANDOFF)
        if discount < 1:
            reasons.append("some evidence was written by the agent")
    if figures and band is Band.SEND:
        band = Band.CO_PILOT
        reasons.append("money, percentage or SLA figures are checked by a person")
    if band is Band.CO_PILOT and not config.staffed:
        band = Band.HANDOFF
        reasons.append(f"no staffed queue on route {config.name}")
    return Verdict(band, confidence, grounded, relevance, discount, figures, reasons)
