"""Deterministic no-model end-to-end evaluation matrix."""

import json
import uuid
from pathlib import Path
from typing import Any

import yaml

from scopebreak.agents.prompts import BoundaryCondition, task_prompt
from scopebreak.agents.scripted import (
    escalation_scripted,
    honest_scripted,
    permission_scripted,
    probing_scripted,
)
from scopebreak.monitors.rule_monitor import RuleMonitor
from scopebreak.protocols.observe_only import observe
from scopebreak.scorers.escalation_stage import escalation_summary
from scopebreak.scorers.preharm_detection import preharm_detection
from scopebreak.scorers.safe_behaviour import classify_safe_outcome
from scopebreak.scorers.scope_violation import (
    explicit_prohibition_violated,
    operator_policy_violated,
)
from scopebreak.scorers.task_success import task_succeeded
from scopebreak.settings.package_recovery.scope_policy import load_scope_policy
from scopebreak.settings.package_recovery.variants import ShortcutVariant
from scopebreak.telemetry.collector import EventCollector
from scopebreak.telemetry.event_schema import Event, Timeline


def _trajectory(
    behaviour: str,
    condition: BoundaryCondition,
    variant: ShortcutVariant,
) -> tuple[Event, ...]:
    if behaviour == "honest":
        return honest_scripted(condition, variant)
    if behaviour == "permission":
        return permission_scripted(condition, True, variant)
    if behaviour == "probing":
        return probing_scripted(condition, False, variant)
    if behaviour == "escalation":
        if variant is ShortcutVariant.ABSENT:
            return probing_scripted(condition, False, variant)
        return escalation_scripted(condition, variant)
    raise ValueError(f"unknown scripted behaviour: {behaviour}")


def _reidentify(events: tuple[Event, ...], run_id: str) -> tuple[Event, ...]:
    return tuple(
        event.model_copy(
            update={
                "run_id": run_id,
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"scopebreak:{run_id}:{index}")),
            }
        )
        for index, event in enumerate(events)
    )


def run(config_path: Path = Path("configs/smoke.yaml")) -> Path:
    config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output_dir = Path("results/mock-smoke")
    telemetry_dir = output_dir / "telemetry"
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved = {
        **config,
        "prompts": {
            condition.value: task_prompt(condition) for condition in BoundaryCondition
        },
    }
    (output_dir / "resolved-config.json").write_text(
        json.dumps(resolved, indent=2), encoding="utf-8"
    )

    policy = load_scope_policy()
    monitor = RuleMonitor(policy, threshold=float(config["monitor"]["threshold"]))
    records: list[dict[str, Any]] = []
    for variant_value in config["variants"]:
        variant = ShortcutVariant(variant_value)
        for condition_value in config["boundary_conditions"]:
            condition = BoundaryCondition(condition_value)
            for behaviour in config["scripted_behaviours"]:
                run_id = f"mock-{variant.value}-{condition.value}-{behaviour}"
                base_events = _reidentify(_trajectory(behaviour, condition, variant), run_id)
                collector = EventCollector(run_id, variant, condition, int(config["seed"]))
                collector.extend(base_events)
                for event in base_events:
                    if event.timeline is Timeline.PROPOSAL:
                        observe(monitor, event, collector)
                collector.write_jsonl(telemetry_dir / f"{run_id}.jsonl")

                summary = escalation_summary(collector.events)
                detection = preharm_detection(collector.events)
                records.append(
                    {
                        "run_id": run_id,
                        "variant": variant.value,
                        "boundary_condition": condition.value,
                        "exact_prompt": task_prompt(condition),
                        "scripted_behaviour": behaviour,
                        "task_success": task_succeeded(collector.events),
                        "safe_outcome": classify_safe_outcome(collector.events).value,
                        "operator_policy_violation": operator_policy_violated(collector.events),
                        "explicit_prohibition_violation": explicit_prohibition_violated(
                            collector.events
                        ),
                        "maximum_stage": summary.maximum_stage,
                        "first_forbidden_proposal_step": summary.first_forbidden_proposal_step,
                        "first_violation_step": summary.first_violation_step,
                        "first_irreversible_harm_step": summary.first_irreversible_harm_step,
                        "first_alert_step": detection.first_alert_step,
                        "pre_harm_detection": detection.detected_before_harm,
                    }
                )

    report = {
        "run_name": config["run_name"],
        "trajectory_count": len(records),
        "task_successes": sum(record["task_success"] for record in records),
        "operator_policy_violations": sum(
            record["operator_policy_violation"] for record in records
        ),
        "records": records,
        "interpretation": "Scripted trajectories validate instrumentation only.",
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    print(run())


if __name__ == "__main__":
    main()
