"""Incident diagnostic packet: what a specialist gets when the recovery breaker trips (ADP-04, HL-ADP-02).

Error text in it is masked like any decision input, and safe_text() is the only way to show it: everything is
HTML-escaped, so a tool error that carries markup or a script cannot act in the specialist console.
"""

import html
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class IncidentDiagnosticPacket(BaseModel):
    tenant_id: str
    case_id: str
    failure_reason: str                      # "reflexion trials exhausted", "step ceiling reached", ...
    steps: int                               # execution steps used in this trajectory
    reflexion_trials: int
    trajectory: list[dict[str, Any]]         # attempt, critique, error, ok - errors masked
    last_error: str | None = None
    suggested_human_action: str = "Review the failed attempts and confirm the step's inputs manually."
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def safe_text(self):
        lines = [f"Case {self.case_id} ({self.tenant_id}): {self.failure_reason}",
                 f"{self.steps} steps, {self.reflexion_trials} reflexion trials", ""]
        for attempt in self.trajectory:
            outcome = "ok" if attempt.get("ok") else f"failed: {attempt.get('error')}"
            lines.append(f"Attempt {attempt.get('attempt')}: {outcome}")
            if attempt.get("critique"):
                lines.append(f"  critique: {attempt['critique']}")
        lines += ["", f"Suggested: {self.suggested_human_action}"]
        return html.escape("\n".join(lines))
