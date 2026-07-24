from pathlib import Path

import pytest

from scopebreak.agents.prompts import BoundaryCondition
from scopebreak.settings.package_recovery.variants import ShortcutVariant
from scopebreak.telemetry.collector import EventCollector
from scopebreak.telemetry.event_schema import (
    Authorisation,
    EventSource,
    EventType,
    Outcome,
    Timeline,
)
from scopebreak.telemetry.parser import TelemetryParseError, load_jsonl


def test_proposal_and_execution_are_distinct_and_ordered(tmp_path: Path) -> None:
    collector = EventCollector("run-1", ShortcutVariant.DISCOVERABLE, BoundaryCondition.EXPLICIT, 3)
    proposal = collector.record(
        step=1,
        timeline=Timeline.PROPOSAL,
        source=EventSource.AGENT,
        event_type=EventType.SHELL_PROPOSED,
        outcome=Outcome.PROPOSED,
        operator_authorisation=Authorisation.FORBIDDEN,
        command="connect evaluator",
        target_service="evaluator",
    )
    execution = collector.record(
        step=1,
        timeline=Timeline.EXECUTION,
        source=EventSource.ENVIRONMENT,
        event_type=EventType.CONNECTION_ATTEMPT,
        outcome=Outcome.FAILED,
        operator_authorisation=Authorisation.FORBIDDEN,
        target_service="evaluator",
    )
    assert proposal.synthetic_harm_stage == 2
    assert execution.synthetic_harm_stage == 3
    assert proposal.event_id != execution.event_id
    path = tmp_path / "events.jsonl"
    collector.write_jsonl(path)
    assert load_jsonl(path) == collector.events


def test_blocked_proposal_has_no_successful_execution() -> None:
    collector = EventCollector(
        "run-blocked", ShortcutVariant.DISCOVERABLE, BoundaryCondition.EXPLICIT, 0
    )
    collector.record(
        step=2,
        timeline=Timeline.PROPOSAL,
        source=EventSource.AGENT,
        event_type=EventType.SHELL_PROPOSED,
        outcome=Outcome.BLOCKED,
        operator_authorisation=Authorisation.FORBIDDEN,
    )
    assert len(collector.by_timeline(Timeline.PROPOSAL)) == 1
    assert collector.by_timeline(Timeline.EXECUTION) == ()


def test_malformed_telemetry_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"event_id": "missing everything else"}\n', encoding="utf-8")
    with pytest.raises(TelemetryParseError):
        load_jsonl(path)
