import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import scopebreak.frontier_gate as gate
from scopebreak.agents.prompts import BoundaryCondition
from scopebreak.frontier_gate import (
    build_gate_plan,
    create_canary_review_receipt,
    create_provider_recovery_receipt,
    load_gate_state,
    run_gate_stage,
)
from scopebreak.frontier_provider import (
    ProviderInfrastructureInterruption,
    ProviderRunResult,
    RetryableInfrastructureError,
    UsageSummary,
    save_provider_receipt,
)
from scopebreak.frontier_study import load_manifest
from scopebreak.settings.package_recovery.variants import ShortcutVariant
from scopebreak.telemetry.collector import EventCollector
from scopebreak.telemetry.event_schema import (
    Authorisation,
    EventSource,
    EventType,
    Outcome,
    Timeline,
)

MANIFEST = Path("configs/frontier-study-v1.yaml")


class MockGateProvider:
    def __init__(
        self,
        *,
        cost: float = 0.1,
        truncate: bool = False,
        infrastructure_failures: int = 0,
        malformed_tool_calls: int = 0,
        provider_interruptions: int = 0,
    ) -> None:
        self.cost = cost
        self.truncate = truncate
        self.infrastructure_failures = infrastructure_failures
        self.malformed_tool_calls = malformed_tool_calls
        self.provider_interruptions = provider_interruptions
        self.calls: list[str] = []

    def preflight(self, manifest: Mapping[str, Any], output_dir: Path) -> ProviderRunResult:
        raise AssertionError("gate tests must not call preflight")

    def calibrate(self, manifest: Mapping[str, Any], output_dir: Path) -> ProviderRunResult:
        raise AssertionError("gate tests must not call calibration")

    def run_sample(
        self,
        manifest: Mapping[str, Any],
        output_dir: Path,
        *,
        sample_id: str,
        cell: str,
        variant: str,
        boundary: str,
        seed: int,
        cost_limit_usd: float,
    ) -> ProviderRunResult:
        del cell, cost_limit_usd
        self.calls.append(sample_id)
        if self.infrastructure_failures:
            self.infrastructure_failures -= 1
            raise RetryableInfrastructureError("mock Docker start failure")
        if self.provider_interruptions:
            self.provider_interruptions -= 1
            output_dir.mkdir(parents=True, exist_ok=False)
            raise ProviderInfrastructureInterruption(
                "mock provider quota failure",
                classification="PROVIDER_QUOTA_EXHAUSTED",
                provider_error_code="insufficient_quota",
                usage=UsageSummary(
                    cumulative_input_tokens=80,
                    cumulative_output_tokens=10,
                    reasoning_tokens=2,
                    peak_context_tokens=80,
                    context_tokens_by_turn=(80,),
                    provider_latency_seconds_by_turn=(0.01,),
                    actual_cost_usd=0.0007,
                    cost_source="mock_recovered",
                ),
            )
        output_dir.mkdir(parents=True, exist_ok=False)
        inspect_log = output_dir / "inspect" / "mock.eval"
        inspect_log.parent.mkdir(parents=True)
        inspect_log.write_bytes(b"mock inspect log")
        collector = EventCollector(
            sample_id, ShortcutVariant(variant), BoundaryCondition(boundary), seed
        )
        collector.record(
            step=1,
            timeline=Timeline.EXECUTION,
            source=EventSource.SCORER,
            event_type=EventType.FUNCTIONAL_TEST,
            outcome=Outcome.SUCCEEDED,
            operator_authorisation=Authorisation.AUTHORISED,
        )
        collector.write_jsonl(output_dir / "telemetry.jsonl")
        (output_dir / "scores.json").write_text("{}", encoding="utf-8")
        (output_dir / "environment-image-digests.json").write_text(
            "{}", encoding="utf-8"
        )
        return ProviderRunResult(
            phase="trajectory",
            requested_model=str(manifest["model"]["requested_model"]),
            resolved_model=str(manifest["model"]["resolved_model"]),
            reasoning_effort=str(manifest["model"]["reasoning_effort"]),
            temperature=float(manifest["model"]["temperature"]),
            inspect_log=str(inspect_log),
            usage=UsageSummary(
                cumulative_input_tokens=100,
                cumulative_output_tokens=20,
                reasoning_tokens=5,
                peak_context_tokens=100,
                context_tokens_by_turn=(100,),
                provider_latency_seconds_by_turn=(0.01,),
                actual_cost_usd=self.cost,
                cost_source="mock",
            ),
            tool_call_verified=True,
            credential_validated=True,
            provider_terms_attested=True,
            tool_calls=2,
            steps=2,
            wall_clock_runtime_seconds=0.1,
            terminal_state_reached=not self.truncate,
            terminal_reason="submit_task_result" if not self.truncate else "unterminated",
            truncation_reason="steps" if self.truncate else None,
            task_success=not self.truncate,
            meaningful_progress=True,
            cleanup_success=True,
            malformed_tool_calls=self.malformed_tool_calls,
            repeated_tool_calls=0,
            late_tool_reliability=True,
        )


def fake_backup(uri: str, repo: Path, bundle: Path) -> dict[str, Any]:
    del repo
    digest = hashlib.sha256(f"{uri}:{bundle}".encode()).hexdigest()
    return {
        "remote_copy_verified": True,
        "archive_sha256": digest,
        "inventory_sha256": digest,
        "backup_run_id": "mock-backup",
    }


@pytest.fixture
def gate_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "results" / "frontier-feasibility-v1"
    monkeypatch.setattr(gate, "GATE_ROOT", root)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", f"file://{tmp_path / 'remote'}")
    return root


def test_frozen_plan_has_exact_interleaved_twenty_samples() -> None:
    plan = build_gate_plan(load_manifest(MANIFEST))
    assert len(plan) == 20
    assert len({sample.sample_id for sample in plan}) == 20
    assert [sample.cell for sample in plan[:2]] == ["C-E", "A-S"]
    counts = {
        cell: sum(sample.cell == cell for sample in plan) for cell in {s.cell for s in plan}
    }
    assert counts == {
        "A-E": 5,
        "A-S": 5,
        "C-E": 5,
        "C-S": 5,
    }


def test_canary_stage_runs_exactly_two_then_remaining_resumes(
    gate_environment: Path,
) -> None:
    del gate_environment
    manifest = load_manifest(MANIFEST)
    provider = MockGateProvider()
    run_dir, state = run_gate_stage(
        manifest,
        git_commit="test-commit",
        stage="canary",
        provider=provider,
        backup=fake_backup,
    )
    assert state["status"] == "CANARY_REVIEW_REQUIRED"
    assert state["next_index"] == 2
    assert provider.calls == [sample.sample_id for sample in build_gate_plan(manifest)[:2]]
    review = create_canary_review_receipt(
        run_dir, git_commit="test-commit", reviewer_identifier="human-test-reviewer"
    )
    resumed_dir, final = run_gate_stage(
        manifest,
        git_commit="test-commit",
        stage="remaining",
        provider=provider,
        backup=fake_backup,
        run_dir_value=str(run_dir),
        review_receipt_value=str(review),
    )
    assert resumed_dir == run_dir
    assert final["status"] == "GATE_COMPLETE"
    assert final["next_index"] == 20
    assert len(provider.calls) == 20
    assert len(final["completed_samples"]) == 20


def test_only_pre_model_infrastructure_failure_is_retried(
    gate_environment: Path,
) -> None:
    del gate_environment
    provider = MockGateProvider(infrastructure_failures=1)
    run_dir, state = run_gate_stage(
        load_manifest(MANIFEST),
        git_commit="test-commit",
        stage="canary",
        provider=provider,
        backup=fake_backup,
    )
    assert len(provider.calls) == 3
    assert len(state["infrastructure_attempts"]) == 1
    assert state["completed_samples"][0]["attempts"] == 2
    assert (run_dir / state["completed_samples"][0]["sample_id"] / "attempt-01").is_dir()


def test_two_early_truncations_stop_and_are_not_retried(
    gate_environment: Path,
) -> None:
    provider = MockGateProvider(truncate=True)
    with pytest.raises(RuntimeError, match="two of the first four"):
        run_gate_stage(
            load_manifest(MANIFEST),
            git_commit="test-commit",
            stage="canary",
            provider=provider,
            backup=fake_backup,
        )
    assert len(provider.calls) == 2
    run_dir = next(gate_environment.iterdir())
    state = load_gate_state(run_dir)
    assert state["status"] == "STOPPED"
    assert state["truncated_first_four"] == 2


def test_cost_projection_above_ceiling_stops_after_first_sample(
    gate_environment: Path,
) -> None:
    provider = MockGateProvider(cost=6.0)
    with pytest.raises(RuntimeError, match="projected gate cost"):
        run_gate_stage(
            load_manifest(MANIFEST),
            git_commit="test-commit",
            stage="canary",
            provider=provider,
            backup=fake_backup,
        )
    assert len(provider.calls) == 1
    state = load_gate_state(next(gate_environment.iterdir()))
    assert state["projected_gate_cost_usd"] == 120.0
    assert state["status"] == "STOPPED"


def test_failed_paid_result_preserves_receipt_and_cost(
    gate_environment: Path,
) -> None:
    provider = MockGateProvider(cost=1.25, malformed_tool_calls=1)
    with pytest.raises(RuntimeError, match="malformed tool calls"):
        run_gate_stage(
            load_manifest(MANIFEST),
            git_commit="test-commit",
            stage="canary",
            provider=provider,
            backup=fake_backup,
        )
    run_dir = next(gate_environment.iterdir())
    state = load_gate_state(run_dir)
    sample_dir = run_dir / build_gate_plan(load_manifest(MANIFEST))[0].sample_id
    assert (sample_dir / "attempt-01" / "trajectory-receipt.json").is_file()
    assert state["total_actual_cost_usd"] == 1.25
    assert state["failed_sample"]["actual_cost_usd"] == 1.25
    assert state["failed_sample"]["classification"] == "TOOL_INTEGRATION_FAILURE"


def test_provider_interruption_pauses_without_automatic_retry_and_recovers_once(
    gate_environment: Path,
) -> None:
    del gate_environment
    manifest = load_manifest(MANIFEST)
    provider = MockGateProvider(provider_interruptions=1)
    with pytest.raises(RuntimeError, match="operator recovery"):
        run_gate_stage(
            manifest,
            git_commit="test-commit",
            stage="canary",
            provider=provider,
            backup=fake_backup,
        )
    run_dir = next(gate.GATE_ROOT.iterdir())
    paused = load_gate_state(run_dir)
    assert provider.calls == [build_gate_plan(manifest)[0].sample_id]
    assert paused["status"] == "PROVIDER_RECOVERY_REQUIRED"
    assert paused["next_index"] == 0
    assert paused["total_actual_cost_usd"] == 0.0007
    assert paused["failed_sample"]["actual_cost_usd"] == 0.0007
    assert paused["failed_sample"]["resume_eligible"] is True

    preflight_result = MockGateProvider().run_sample(
        manifest,
        run_dir / "mock-preflight-provider",
        sample_id="preflight",
        cell="A-E",
        variant="A",
        boundary="explicit",
        seed=1,
        cost_limit_usd=1,
    ).model_copy(
        update={
            "phase": "preflight",
            "resolved_model": manifest["model"]["resolved_model"],
        }
    )
    preflight = save_provider_receipt(preflight_result, run_dir / "fresh-preflight", "test-commit")
    recovery = create_provider_recovery_receipt(
        run_dir,
        git_commit="test-commit",
        reviewer_identifier="operator-test",
        preflight_receipt=preflight,
    )
    _, resumed = run_gate_stage(
        manifest,
        git_commit="test-commit",
        stage="recovery",
        provider=provider,
        backup=fake_backup,
        run_dir_value=str(run_dir),
        review_receipt_value=str(recovery),
    )
    assert resumed["status"] == "CANARY_REVIEW_REQUIRED"
    assert resumed["next_index"] == 2
    first = build_gate_plan(manifest)[0].sample_id
    assert (run_dir / first / "attempt-01" / "failure.json").is_file()
    assert (run_dir / first / "attempt-02" / "trajectory-receipt.json").is_file()


def test_failed_provider_replacement_is_not_recoverable_again(
    gate_environment: Path,
) -> None:
    del gate_environment
    manifest = load_manifest(MANIFEST)
    provider = MockGateProvider(provider_interruptions=2)
    with pytest.raises(RuntimeError, match="operator recovery"):
        run_gate_stage(
            manifest,
            git_commit="test-commit",
            stage="canary",
            provider=provider,
            backup=fake_backup,
        )
    run_dir = next(gate.GATE_ROOT.iterdir())
    preflight_result = MockGateProvider().run_sample(
        manifest,
        run_dir / "mock-preflight-provider",
        sample_id="preflight",
        cell="A-E",
        variant="A",
        boundary="explicit",
        seed=1,
        cost_limit_usd=1,
    ).model_copy(update={"phase": "preflight"})
    preflight = save_provider_receipt(preflight_result, run_dir / "fresh-preflight", "test-commit")
    recovery = create_provider_recovery_receipt(
        run_dir,
        git_commit="test-commit",
        reviewer_identifier="operator-test",
        preflight_receipt=preflight,
    )
    with pytest.raises(RuntimeError, match="replacement attempt failed"):
        run_gate_stage(
            manifest,
            git_commit="test-commit",
            stage="recovery",
            provider=provider,
            backup=fake_backup,
            run_dir_value=str(run_dir),
            review_receipt_value=str(recovery),
        )
    stopped = load_gate_state(run_dir)
    assert stopped["status"] == "STOPPED"
    assert stopped["failed_sample"]["resume_eligible"] is False
