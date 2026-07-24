"""Strict JSON Lines telemetry parser."""

import json
from pathlib import Path

from pydantic import ValidationError

from scopebreak.telemetry.event_schema import Event


class TelemetryParseError(ValueError):
    """Malformed telemetry with line context."""


def load_jsonl(path: Path) -> tuple[Event, ...]:
    """Load and validate every non-empty line; never silently skip corruption."""
    events: list[Event] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(Event.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as error:
            message = f"invalid telemetry at {path}:{line_number}: {error}"
            raise TelemetryParseError(message) from error
    return tuple(events)
