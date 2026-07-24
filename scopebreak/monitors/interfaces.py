"""Common monitor result interface."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from scopebreak.telemetry.event_schema import Event


class MonitorDecisionKind(StrEnum):
    ALLOW = "allow"
    FLAG = "flag"
    BLOCK = "block"
    ESCALATE = "escalate"


class MonitorDecision(BaseModel):
    """Structured monitor output; observe-only uses allow or flag."""

    model_config = ConfigDict(frozen=True)
    suspicion_score: float = Field(ge=0, le=1)
    decision: MonitorDecisionKind
    reason: str
    evidence_event_ids: tuple[str, ...]


class ActionMonitor(Protocol):
    def evaluate(self, proposed_event: Event) -> MonitorDecision: ...
