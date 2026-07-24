"""Explicit terminal action for successful, incomplete, blocked, or stopped work."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CompletionStatus(StrEnum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    STOPPED = "stopped"


class TaskResult(BaseModel):
    """Structured terminal report."""

    model_config = ConfigDict(frozen=True)
    status: CompletionStatus
    summary: str = Field(min_length=1)
    tests_passed: bool = False


def submit_task_result(
    status: CompletionStatus, summary: str, tests_passed: bool = False
) -> TaskResult:
    """Create a terminal task result."""
    return TaskResult(status=status, summary=summary, tests_passed=tests_passed)
