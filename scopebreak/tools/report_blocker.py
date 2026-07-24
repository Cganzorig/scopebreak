"""Safe action for reporting an operational blocker."""

from pydantic import BaseModel, ConfigDict, Field


class BlockerReport(BaseModel):
    """Structured report distinguishing safe stopping from generic failure."""

    model_config = ConfigDict(frozen=True)
    blocker: str = Field(min_length=1)
    attempted_steps: tuple[str, ...]
    recommended_next_action: str = Field(min_length=1)


def report_blocker(
    blocker: str, attempted_steps: list[str], recommended_next_action: str
) -> BlockerReport:
    """Create a structured safe blocker report."""
    return BlockerReport(
        blocker=blocker,
        attempted_steps=tuple(attempted_steps),
        recommended_next_action=recommended_next_action,
    )
