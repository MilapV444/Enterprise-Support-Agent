"""The `run_turn` activity: one LangGraph turn of a case, safe to retry (ADP-02, MS-ADP-04).

A retry after a crash carries on from the case's last checkpoint instead of starting the turn again, and a
retry of a turn that already finished (its result was lost) applies nothing twice: each turn's event id is
stored in the thread state.
"""

from concurrent.futures import ThreadPoolExecutor

from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from core.orchestrator.statechart import build, postgres_checkpointer, thread
from workflows.ticket import TASK_QUEUE, TicketWorkflow, TurnOutcome, TurnRequest


class TurnActivities:
    def __init__(self, hooks, dsn, **build_options):
        self.hooks, self.dsn, self.build_options = hooks, dsn, build_options

    @activity.defn(name="run_turn")
    def run_turn(self, request: TurnRequest) -> TurnOutcome:
        config = thread(request.tenant_id, request.case_id)
        with postgres_checkpointer(self.dsn) as saver:
            graph = build(self.hooks, saver, **self.build_options)
            snapshot = graph.get_state(config)
            seen = (snapshot.values.get("event") or {}).get("id")
            if snapshot.next and seen != request.event_id:
                raise ApplicationError(f"case {request.case_id} has an unfinished turn from another run",
                                       non_retryable=True)
            if snapshot.next:  # an earlier attempt of this turn crashed: carry on from its last checkpoint
                graph.invoke(None, config)
            elif seen != request.event_id:
                graph.invoke({"tenant_id": request.tenant_id, "case_id": request.case_id,
                              "session_id": request.session_id,
                              "event": {**request.event, "id": request.event_id}}, config)
            snapshot = graph.get_state(config)
        return TurnOutcome(stage=snapshot.values.get("stage"),
                           checkpoint_id=snapshot.config["configurable"].get("checkpoint_id"))


def worker(client, activities, task_queue=TASK_QUEUE):
    return Worker(client, task_queue=task_queue, workflows=[TicketWorkflow], activities=[activities.run_turn],
                  activity_executor=ThreadPoolExecutor(max_workers=8))
