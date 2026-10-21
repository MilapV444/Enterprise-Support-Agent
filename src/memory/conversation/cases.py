"""Linking a new conversation to the customer's case (FR-15 / MS-ADP-01: MS-D1, MS-Q1).

On the first message of a conversation, Jev picks among the principal's open cases and NEW_CASE:
- confidence >= 0.90: linked at once;
- 0.50 to 0.90: the customer is asked to confirm the suggested case (confirm() binds their answer);
- below 0.50, NEW_CASE, or no open case: a new case.
If Jev cannot answer, the customer is asked. Only the principal's own open cases are offered or accepted, so
a confirmation cannot attach a conversation to someone else's case. Each case is described to Jev by its
latest summary or first customer message, with digits blanked (numbers stay out of Jev questions).
"""

from dataclasses import dataclass

from channels.sessions import link_case
from core.orchestrator.decisions import NUMBERS, JevUnavailable, mask

LINK_AT, CONFIRM_AT = 0.90, 0.50
NEW_CASE = "NEW_CASE"
QUESTION = "Which of the customer's cases does this message pertain to?"
CLOSED = ["resolved", "closed"]


@dataclass
class CaseLink:
    case_id: str | None        # the linked case, or the suggestion when confirmation is needed
    is_new: bool
    confidence: float
    needs_confirmation: bool = False
    prompt: str | None = None  # the confirmation question for the customer


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def open_cases(conn, tenant_id, principal_id, exclude_conversation=None):
    """{case_id: description} of the principal's open cases, most recent first."""
    with conn.transaction():
        _context(conn, tenant_id)
        rows = conn.execute(
            "SELECT k.id, (SELECT coalesce((SELECT s.summary FROM dialogue_summaries s "
            "                               WHERE s.conversation_id = c.id), "
            "                              (SELECT t.content FROM dialogue_turns t "
            "                               WHERE t.conversation_id = c.id AND t.role = 'user' "
            "                               ORDER BY t.seq LIMIT 1)) "
            "               FROM conversations c WHERE c.case_id = k.id ORDER BY c.created_at DESC LIMIT 1) "
            "FROM cases k WHERE k.status <> ALL(%s) AND EXISTS (SELECT 1 FROM conversations c "
            "  WHERE c.case_id = k.id AND c.principal_id = %s AND c.id IS DISTINCT FROM %s) "
            "ORDER BY k.created_at DESC", (CLOSED, principal_id, exclude_conversation)).fetchall()
    return {case_id: (text or "an earlier issue")[:300] for case_id, text in rows}


def link(conn, engine, tenant_id, principal_id, conversation_id, message):
    """Link the conversation from its first (masked) message, or say what to ask the customer."""
    cases = open_cases(conn, tenant_id, principal_id, exclude_conversation=conversation_id)
    if not cases:
        return CaseLink(link_case(conn, tenant_id, conversation_id), True, 1.0)
    options = {case_id: NUMBERS.sub("#", text) for case_id, text in cases.items()}
    options[NEW_CASE] = "A new issue, not one of the earlier cases"
    try:
        question = {"type": "choice", "instructions": QUESTION, "criteria": options}
        answer = engine.ask({"message": mask(message)}, {"case": question})["case"]
    except JevUnavailable:
        suggestion = next(iter(cases))
        return CaseLink(suggestion, False, 0.0, True, confirmation(cases[suggestion]))
    if answer.value == NEW_CASE or answer.confidence < CONFIRM_AT:
        return CaseLink(link_case(conn, tenant_id, conversation_id), True, answer.confidence)
    if answer.confidence >= LINK_AT:
        return CaseLink(link_case(conn, tenant_id, conversation_id, answer.value), False, answer.confidence)
    return CaseLink(answer.value, False, answer.confidence, True, confirmation(cases[answer.value]))


def confirmation(description):
    return f'Are you following up on your earlier issue ("{description[:120]}"), or is this a new issue?'


def confirm(conn, tenant_id, principal_id, conversation_id, case_id):
    """Bind the customer's answer: their case id, or None for a new case. Returns the linked case id."""
    if case_id is not None and case_id not in open_cases(conn, tenant_id, principal_id, conversation_id):
        raise LookupError(f"{case_id!r} is not one of this customer's open cases")
    return link_case(conn, tenant_id, conversation_id, case_id)
