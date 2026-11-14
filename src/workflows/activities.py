"""The `run_turn` activity: one statechart turn of a case, safe to retry (ADP-02, MS-ADP-04).

A retry after a crash carries on from the case's last saved stage instead of starting the turn again, and a
retry of a turn that already finished (its result was lost) applies nothing twice: each turn's event id is
stored in the case state. The outcome's checkpoint_id is the case state's version.
"""

from concurrent.futures import ThreadPoolExecutor

from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from core.orchestrator.statechart import build, thread
from workflows.ticket import TASK_QUEUE, TicketWorkflow, TurnOutcome, TurnRequest


class TurnActivities:
    def __init__(self, hooks, store, **build_options):
        self.graph = build(hooks, store, **build_options)

    @activity.defn(name="run_turn")
    def run_turn(self, request: TurnRequest) -> TurnOutcome:
        config = thread(request.tenant_id, request.case_id)
        state = self.graph.get_state(config)
        seen = (state.get("event") or {}).get("id")
        if state.get("pending") and seen != request.event_id:
            raise ApplicationError(f"case {request.case_id} has an unfinished turn from another run",
                                   non_retryable=True)
        if state.get("pending"):  # an earlier attempt of this turn crashed: carry on from its last stage
            self.graph.invoke(None, config)
        elif seen != request.event_id:
            self.graph.invoke({"tenant_id": request.tenant_id, "case_id": request.case_id,
                               "session_id": request.session_id,
                               "event": {**request.event, "id": request.event_id}}, config)
        state, version = self.graph.store.load(request.tenant_id, request.case_id)
        return TurnOutcome(stage=state.get("stage"), checkpoint_id=str(version))


def worker(client, activities, task_queue=TASK_QUEUE):
    return Worker(client, task_queue=task_queue, workflows=[TicketWorkflow], activities=[activities.run_turn],
                  activity_executor=ThreadPoolExecutor(max_workers=8))
