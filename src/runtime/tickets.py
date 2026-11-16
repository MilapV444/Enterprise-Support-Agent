"""Ticket proposals in the turn loop (FR-45, FR-47; DECISION-368069f5).

A billing request that needs our team to act on one of the customer's own charges (a refund, a duplicate or
wrong charge, a dispute) becomes a ticket proposal instead of a recited procedure:

- wants(): Jev decides whether the customer asks the team to act and which category fits; when Jev cannot
  answer, a keyword match decides, so a refund request is never lost to an outage. Numbers never reach Jev.
- the details come from the customer's own words, in code: the invoice number (the latest one mentioned) and
  the amount (stated, else the invoice's); the invoice must be one of the signed-in customer's own
  (own_invoice(), a read of the Nimbus invoices under the tenant's row-level security).
- only a signed-in customer (T1 and up) gets a proposal; a guest gets a card asking to sign in first.
- the proposal is hitl.tickets.Tickets.propose(): nothing is raised until the customer confirms, and the
  reply never says money was refunded.

Every hand-off offers a ticket too (FR-46): the category comes from the staff-only team or the triage intent,
the queue from the category, the reason is the hand-off's own. In a conversation that already has a raised
ticket, a message that would be handed off again is added to that ticket as a note and acknowledged.
"""

import re

from core.orchestrator.decisions import JevUnavailable, Masked
from hitl.tickets import Tickets

INVOICE = re.compile(r"\binv[-_][a-z0-9][a-z0-9-]*[a-z0-9]\b", re.IGNORECASE)
AMOUNT = re.compile(
    r"(?:\$|\bUS\$|\bUSD)\s?(?P<a>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.(?P<ac>[0-9]{1,2}))?"
    r"|\b(?P<b>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.(?P<bc>[0-9]{1,2}))?\s?(?:USD\b|dollars?\b)",
    re.IGNORECASE)
ASKS = re.compile(r"\b(refund|charged twice|double[- ]?charged|duplicate (charge|payment)|overcharg\w*|"
                  r"wrong (charge|amount)|dispute|money back)\b", re.IGNORECASE)
QUESTIONS = {
    "wants_ticket": {"type": "noul", "instructions": (
        "Is the customer asking our billing team to act on one of their own charges or invoices (a refund, "
        "a duplicate or wrong charge, a dispute), rather than asking how something works?"),
        "criteria": {"true": "They want the team to act on their own charge or invoice",
                     "false": "They are asking a question about how billing works"}},
    "category": {"type": "choice", "instructions": "Which kind of ticket fits the request?",
                 "criteria": {"refund": "Money the customer already paid should come back",
                              "billing": "Another problem with a charge or an invoice"}},
}
SUBJECTS = {"refund": "Refund request", "billing": "Billing problem"}
ASK = {"invoice": "the invoice number (it starts with inv-, for example inv-acme-1)",
       "own_invoice": "an invoice number from your own account: I could not find that one on your account"}
SIGN_IN = ("I can raise a ticket for this with our billing team once you are signed in. Please sign in with "
           "your email code first, then tell me again and I will set it up.")


def wants(decide, thread):
    """(wants a ticket, category) for the masked thread; Jev first, a keyword match when Jev cannot answer."""
    try:
        answers = decide.ask({"message": Masked(thread)}, QUESTIONS)
        if answers["wants_ticket"].value is True and answers["wants_ticket"].confidence >= 0.5:
            return True, answers["category"].value
        return False, None
    except JevUnavailable:
        return (True, "refund") if ASKS.search(thread) else (False, None)


def latest_invoice(texts):
    found = [m.group(0).lower() for text in texts for m in INVOICE.finditer(text)]
    return found[-1] if found else None


def amount_cents(texts):
    """The latest amount the customer stated, in cents (US dollars), or None."""
    cents = None
    for text in texts:
        for m in AMOUNT.finditer(text):
            whole, part = (m.group("a"), m.group("ac")) if m.group("a") else (m.group("b"), m.group("bc"))
            cents = int(whole.replace(",", "")) * 100 + int((part or "0").ljust(2, "0"))
    return cents


def own_invoice(connect, tenant_id, principal_id, invoice_id):
    """The amount in cents of the customer's own invoice; None when it is not theirs or does not exist."""
    with connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))
        row = conn.execute("SELECT round(amount_usd * 100)::bigint FROM nimbus_invoices WHERE tenant_id = %s "
                           "AND principal_id = %s AND lower(invoice_id) = %s",
                           (tenant_id, principal_id, invoice_id)).fetchone()
    return row[0] if row else None


def missing_question(missing):
    """One question that names exactly what is still missing."""
    return "To raise a ticket for this, I need " + " and ".join(ASK[m] for m in missing) + "."


def money(cents, currency="USD"):
    return f"{currency} {cents // 100:,}.{cents % 100:02d}"


def propose(connect, state, who, ticket):
    """The proposal for this conversation and invoice (the same one again when the turn is retried)."""
    return Tickets(connect).propose(
        state["tenant_id"], who["principal_id"], state["case_id"],
        f"{ticket['category']}:{ticket['invoice']}",
        category=ticket["category"], subject=f"{SUBJECTS[ticket['category']]}: {ticket['invoice']}",
        queue="queue_billing", reason="billing request", description=ticket["reason"],
        invoice_id=ticket["invoice"], amount_cents=ticket["amount_cents"], currency="USD",
        turn_id=who.get("turn_id"))


def proposal_reply(proposal):
    amount = f" for {money(proposal.amount_cents)}" if proposal.amount_cents is not None else ""
    return (f"I can raise a {proposal.category} ticket{amount} on invoice {proposal.invoice_id} with our "
            "billing team. Nothing has been raised or changed yet: use Raise ticket to confirm, and the team "
            "will follow up on the ticket.")


def proposal_card(proposal):
    return {"kind": "ticket_proposal", "title": f"Raise ticket {proposal.number}?", **proposal.card(),
            "actions": [{"type": "confirm_ticket", "proposal": proposal.number, "label": "Raise ticket"}]}


SIGN_IN_CARD = {"kind": "sign_in", "title": "Sign in to raise a ticket",
                "actions": [{"type": "sign_in", "label": "Sign in with your email"}]}


# Hand-offs (TK-04, FR-46): every route to a person offers a ticket; once one is raised, later messages are
# added to it as notes

INTENT_CATEGORY = {"BILLING_INQUIRY": "billing", "TECHNICAL_OUTAGE": "technical", "PASSWORD_RESET": "account",
                   "SUBSCRIPTION_UPDATE": "account"}
TEAM_CATEGORY = {"billing": "billing", "security": "security"}  # runtime.TEAMS team names (B26)
QUEUE = {"refund": "queue_billing", "billing": "queue_billing", "technical": "queue_technical",
         "account": "queue_account", "security": "queue_account", "general": "queue_senior"}  # hitl.queues
TITLES = {"refund": "Refund request", "billing": "Billing", "technical": "Technical problem",
          "account": "Account", "security": "Security", "general": "Support request"}
OFFER = "Raise a ticket below and the team will follow up on it."
SIGN_IN_OFFER = "Sign in with your email code to raise a ticket the team will follow up on."


def handoff_category(intent, team=None):
    return TEAM_CATEGORY.get(team) or INTENT_CATEGORY.get(intent, "general")


def propose_handoff(connect, tenant_id, principal_id, conversation_id, turn_id, category, reason, masked):
    """A proposal for this hand-off turn (the same one again when the turn is retried)."""
    subject = f"{TITLES[category]}: {' '.join(masked.split())[:80]}"
    return Tickets(connect).propose(tenant_id, principal_id, conversation_id, f"handoff:{turn_id}",
                                    category=category, subject=subject, queue=QUEUE[category], reason=reason,
                                    description=masked, turn_id=turn_id)


def handoff_card(proposal):
    return {**proposal_card(proposal), "title": f"Raise ticket {proposal.number} so the team follows up?"}


def ticket_card(ticket):
    return {"kind": "ticket", "title": f"Ticket {ticket.number}", **ticket.card()}


def noted_reply(ticket):
    return (f"I've added this to your ticket {ticket.number}. The team working on it will see it; you can "
            "follow the ticket under My tickets.")
