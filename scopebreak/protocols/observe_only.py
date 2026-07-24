"""Observe-only protocol that records but never blocks monitor decisions."""

from scopebreak.monitors.interfaces import ActionMonitor, MonitorDecision
from scopebreak.telemetry.collector import EventCollector
from scopebreak.telemetry.event_schema import (
    Event,
    EventSource,
    EventType,
    Outcome,
    Timeline,
)


def observe(
    monitor: ActionMonitor,
    proposed_event: Event,
    collector: EventCollector,
) -> MonitorDecision:
    """Evaluate and record a proposal without changing its execution."""
    decision = monitor.evaluate(proposed_event)
    collector.record(
        step=proposed_event.step,
        timeline=Timeline.MONITOR,
        source=EventSource.MONITOR,
        event_type=EventType.MONITOR_SCORE,
        outcome=Outcome.SUCCEEDED,
        metadata={
            "suspicion_score": decision.suspicion_score,
            "decision": decision.decision.value,
            "observe_only": True,
        },
    )
    return decision
