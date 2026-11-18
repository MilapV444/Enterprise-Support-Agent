"""The agent's own support desk as a tool system (FR-45; DECISION-368069f5).

support_desk.raise_ticket opens the customer's ticket proposal (hitl.tickets) when the customer confirms it:

- a low-risk write, from tier T1: the on-behalf-of token for "status-tools" (T1, case:update) that the
  Executor mints from the customer's live session names the tenant and the customer, so nothing in the call's
  arguments decides whose ticket it is;
- its only argument is the proposal's number (TA-ADP-02): every other field comes from the proposal row;
- confirming twice returns the same ticket, so a retried call raises nothing more; someone else's, an
  unknown or an expired proposal is REJECTED;
- code calls it on the customer's confirmation. It is offered to no model and to no specialist: its only stage
  is CUSTOMER_ACTION, which no statechart stage is called.

register(registry, connect, identity) adds it to a registry; SYSTEMS is its entry for the
tools.execution.Executor.
Through the Executor every call is audited (tools.audit) and runs against the live session.
"""

from pydantic import BaseModel

from channels.identity.tiers import Tier
from hitl.queues import Refused
from hitl.tickets import Tickets, number_id
from tools.execution import System, ToolFailure, current
from tools.schemas import arg

AUDIENCE = "status-tools"
RAISE = "support_desk.raise_ticket"
CUSTOMER_ACTION = "CUSTOMER_ACTION"  # not a statechart stage: Registry.permitted never offers the tool
SYSTEMS = {"support_desk": System("support_desk", frozenset(), "obo", AUDIENCE, idempotent_writes=True)}


class RaiseTicket(BaseModel):
    proposal: str = arg(False, personal=False, pattern=r"^TKT-[0-9]{5,}$")  # an id the agent issued


def register(registry, connect, identity):
    """Add support_desk.raise_ticket to `registry` (before it is frozen)."""
    tickets = Tickets(connect)

    def raise_ticket(args):
        claims = identity.verify_obo(current().credential, AUDIENCE)
        try:
            ticket = tickets.confirm(claims["tid"], claims["sub"], number_id(args.proposal))
        except Refused as refused:  # not this customer's proposal, unknown or expired
            raise ToolFailure("REJECTED", str(refused)) from refused
        return {"ticket": ticket.card()}

    registry.tool(RAISE, args=RaiseTicket, description="Raise the support ticket the customer has confirmed",
                  risk="low_risk_write", stages={CUSTOMER_ACTION}, min_tier=Tier.T1_VERIFIED,
                  author="claude")(raise_ticket)  # reviewed_by: set when a person reviews it
    return registry
