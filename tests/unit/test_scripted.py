from scopebreak.agents.scripted import (
    escalation_scripted,
    honest_scripted,
    permission_scripted,
    probing_scripted,
)
from scopebreak.telemetry.event_schema import EventType, Timeline


def test_scripted_trajectories_cover_required_behaviours() -> None:
    honest = honest_scripted()
    assert all(event.synthetic_harm_stage == 0 for event in honest)
    assert any(event.event_type is EventType.FUNCTIONAL_TEST for event in honest)

    permission = permission_scripted()
    assert any(event.event_type is EventType.PERMISSION_REQUEST for event in permission)

    probing = probing_scripted()
    assert max(event.synthetic_harm_stage for event in probing) == 3

    escalation = escalation_scripted()
    assert {event.synthetic_harm_stage for event in escalation} >= set(range(1, 8))
    assert any(event.timeline is Timeline.PROPOSAL for event in escalation)
    assert any(event.timeline is Timeline.EXECUTION for event in escalation)
