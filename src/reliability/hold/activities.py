"""The activities of HeldRequestWorkflow (reliability.hold): the notice, each try, and the hand-over."""

from concurrent.futures import ThreadPoolExecutor

from temporalio import activity
from temporalio.worker import Worker

from channels.api.envelope import EventType
from channels.api.turns import publish
from core.orchestrator.decisions import mask
from data.events import EventLog
from hitl.queues import Domain, Packet, Reason
from reliability.hold import TASK_QUEUE, Attempt, HeldRequestWorkflow, HoldStart
from safety.output.checks import check
from tools.execution import ToolFailure
from tools.execution.calls import ToolCall

HELD = ("This system is not reachable right now. We have kept your request and will send the answer to your "
        "inbox here as soon as it is back.")
HANDED_OVER = "The system is still not reachable, so a specialist will follow up on your request."
STILL_DOWN = {"SYSTEM_UNAVAILABLE", "TRANSIENT"}
AGENT = "svc:enterprise-agent-runtime"


class HoldActivities:
    def __init__(self, executor, connect, queues, answer, domain=Domain.TECHNICAL):
        """executor: tools.execution.Executor (with its identity); connect(): autocommit connection to the
        main database; queues: hitl.queues.Queues; answer(question, screened output) -> the reply text (the
        agent, drafting from fresh data)."""
        self.executor, self.connect, self.queues = executor, connect, queues
        self.answer, self.domain = answer, domain

    def _publish(self, start, event_type, data):
        with self.connect() as conn:
            publish(EventLog(conn), start.tenant_id, start.conversation_id, event_type, data)

    @activity.defn(name="hold_notify")
    def notify(self, start: HoldStart) -> None:
        self._publish(start, EventType.STATUS, {"state": "held", "hold_id": start.hold_id, "text": HELD})

    @activity.defn(name="hold_attempt")
    def attempt(self, start: HoldStart, tries: int) -> Attempt:
        try:
            principal_id, _ = self.executor.identity.session_principal(start.tenant_id, start.session_id)
        except Exception:  # noqa: BLE001 - ended, expired or another tenant's session
            return Attempt("refused", "AUTHENTICATION_EXPIRED")
        call = ToolCall(tool_call_id=f"{start.hold_id}:{tries}", tool_id=start.tool_id,
                        arguments=start.arguments, tenant_id=start.tenant_id, principal_id=principal_id,
                        case_id=start.case_id, checkpoint_id=start.hold_id, session_id=start.session_id)
        try:
            result = self.executor.run(call)
        except ToolFailure as failure:
            return Attempt("down" if failure.code in STILL_DOWN else "refused", failure.code)
        reply = check(self.answer(start.question, result.content))
        if reply.verdict != "deliver":
            return Attempt("refused", "REPLY_HELD")
        self._publish(start, EventType.FINAL,
                      {"text": reply.text, "hold_id": start.hold_id, "deferred": True})
        return Attempt("delivered")

    @activity.defn(name="hold_hand_over")
    def hand_over(self, start: HoldStart, code: str) -> None:
        with self.connect() as conn, conn.transaction():  # whose conversation it is, from its record
            conn.execute("SET LOCAL ROLE app_runtime")
            conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (start.tenant_id,))
            row = conn.execute("SELECT principal_id FROM conversations WHERE id = %s",
                               (start.conversation_id,)).fetchone()
        principal_id = row[0] if row else None
        if principal_id is not None:
            self.queues.escalate(Packet(
                tenant_id=start.tenant_id, case_id=start.case_id, conversation_id=start.conversation_id,
                customer_id=principal_id, handler_id=AGENT, identity_tier="unknown", channel="web",
                reason=Reason.SYSTEM_DEPENDENCY_HELD, domain=self.domain,
                summary=mask(f"{start.tool_id} stayed unavailable ({code}); the request was held").text,
                last_turns=[mask(start.question).text] if start.question else [],
                diagnostic_trace=f"held request {start.hold_id}: {code}"))
        self._publish(start, EventType.HANDOFF,
                      {"state": "queued", "hold_id": start.hold_id, "text": HANDED_OVER, "reason": code})


def worker(client, activities, task_queue=TASK_QUEUE):
    return Worker(client, task_queue=task_queue, workflows=[HeldRequestWorkflow],
                  activities=[activities.notify, activities.attempt, activities.hand_over],
                  activity_executor=ThreadPoolExecutor(max_workers=4))
