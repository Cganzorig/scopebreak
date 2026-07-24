"""Deterministic two-timeline event collector."""

import json
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from scopebreak.agents.prompts import BoundaryCondition
from scopebreak.settings.package_recovery.variants import ShortcutVariant
from scopebreak.telemetry.event_schema import (
    Authorisation,
    Event,
    EventSource,
    EventType,
    Outcome,
    Timeline,
    event_stage,
)


class EventCollector:
    """Append-only collector with stable event IDs and insertion ordering."""

    def __init__(
        self,
        run_id: str,
        variant: ShortcutVariant,
        boundary_condition: BoundaryCondition,
        seed: int,
    ) -> None:
        self.run_id = run_id
        self.variant = variant
        self.boundary_condition = boundary_condition
        self.seed = seed
        self._events: list[Event] = []

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def by_timeline(self, timeline: Timeline) -> tuple[Event, ...]:
        return tuple(event for event in self._events if event.timeline is timeline)

    def record(
        self,
        *,
        step: int,
        timeline: Timeline,
        source: EventSource,
        event_type: EventType,
        outcome: Outcome,
        operator_authorisation: Authorisation = Authorisation.UNKNOWN,
        **values: Any,
    ) -> Event:
        sequence = len(self._events)
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"scopebreak:{self.run_id}:{sequence}"))
        event = Event(
            event_id=event_id,
            run_id=self.run_id,
            variant=self.variant,
            boundary_condition=self.boundary_condition,
            seed=self.seed,
            step=step,
            timeline=timeline,
            source=source,
            event_type=event_type,
            outcome=outcome,
            operator_authorisation=operator_authorisation,
            synthetic_harm_stage=event_stage(event_type, operator_authorisation),
            **values,
        )
        self._events.append(event)
        return event

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(event.model_dump_json() for event in self._events)
        path.write_text(body + ("\n" if body else ""), encoding="utf-8")

    def extend(self, events: Iterable[Event]) -> None:
        for event in events:
            if event.run_id != self.run_id:
                raise ValueError("cannot mix run IDs in one collector")
            self._events.append(event)

    def as_json(self) -> str:
        return json.dumps([event.model_dump(mode="json") for event in self._events])
