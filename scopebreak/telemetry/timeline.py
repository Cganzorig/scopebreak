"""Timeline queries shared by scorers and reports."""

from collections.abc import Iterable

from scopebreak.telemetry.event_schema import Event, Timeline


def proposal_timeline(events: Iterable[Event]) -> tuple[Event, ...]:
    return tuple(event for event in events if event.timeline is Timeline.PROPOSAL)


def execution_timeline(events: Iterable[Event]) -> tuple[Event, ...]:
    return tuple(event for event in events if event.timeline is Timeline.EXECUTION)


def first_stage_step(events: Iterable[Event], minimum_stage: int) -> int | None:
    steps = [event.step for event in events if event.synthetic_harm_stage >= minimum_stage]
    return min(steps) if steps else None
