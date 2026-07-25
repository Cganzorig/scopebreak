"""Resumable, fail-closed orchestration for the matched 20-run frontier gate."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from scopebreak.agents.prompts import BoundaryCondition, task_prompt
from scopebreak.backup import copy_to_remote, sha256, upload_guarded_archive
from scopebreak.frontier_provider import (
    FrontierProvider,
    FrontierRunError,
    ProviderRunResult,
    RetryableInfrastructureError,
    save_provider_receipt,
    write_checksum,
)
from scopebreak.telemetry.parser import load_jsonl

GATE_ROOT = Path("results/frontier-feasibility-v1")
CANARY_COUNT = 2
TOTAL_SAMPLES = 20
CANARY_REVIEW_FIELDS = (
    "correct_prompt",
    "correct_variant",
    "correct_seed",
    "correct_model_identity",
    "telemetry_complete",
    "cleanup_verified",
    "incremental_backup_verified",
    "manual_full_trajectory_reviewed",
    "approve_remaining_18",
)


class GateSampleSpec(BaseModel):
    """One immutable position in the preregistered execution order."""

    model_config = ConfigDict(frozen=True)
    index: int = Field(ge=1, le=TOTAL_SAMPLES)
    sample_id: str
    cell: str
    variant: Literal["A", "C"]
    boundary: Literal["explicit", "silent"]
    seed: int = Field(ge=0)


BackupFunction = Callable[[str, Path, Path], dict[str, Any]]


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def build_gate_plan(manifest: Mapping[str, Any]) -> tuple[GateSampleSpec, ...]:
    """Bind every frozen order position to one independently recorded seed."""
    order = list(manifest["execution_order"])
    seeds = list(manifest["seeds"])
    if len(order) != TOTAL_SAMPLES or len(seeds) != TOTAL_SAMPLES:
        raise ValueError("gate plan must contain exactly 20 order positions and seeds")
    cells = {
        str(condition["id"]): (str(condition["variant"]), str(condition["boundary"]))
        for condition in manifest["conditions"]
    }
    plan: list[GateSampleSpec] = []
    for offset, (cell, seed) in enumerate(zip(order, seeds, strict=True), start=1):
        variant_value, boundary_value = cells[cell]
        variant = cast(Literal["A", "C"], variant_value)
        boundary = cast(Literal["explicit", "silent"], boundary_value)
        sample_id = f"{offset:02d}-{cell}-{int(seed)}"
        plan.append(
            GateSampleSpec(
                index=offset,
                sample_id=sample_id,
                cell=cell,
                variant=variant,
                boundary=boundary,
                seed=int(seed),
            )
        )
    if len({sample.sample_id for sample in plan}) != TOTAL_SAMPLES:
        raise ValueError("gate sample IDs are not unique")
    return tuple(plan)


def gate_plan_sha256(plan: tuple[GateSampleSpec, ...]) -> str:
    body = json.dumps([sample.model_dump() for sample in plan], sort_keys=True).encode()
    return hashlib.sha256(body).hexdigest()


def new_gate_run_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return GATE_ROOT / f"{timestamp}-gate-{secrets.token_hex(4)}"


def _state_path(run_dir: Path) -> Path:
    return run_dir / "gate-run-state.json"


def _write_state(run_dir: Path, state: Mapping[str, Any]) -> None:
    path = _state_path(run_dir)
    _write_json(path, state)
    write_checksum(path)


def _checksum_valid(path: Path) -> bool:
    sidecar = path.with_name(f"{path.name}.sha256")
    return (
        path.is_file()
        and sidecar.is_file()
        and sha256(path) == sidecar.read_text(encoding="utf-8").split()[0]
    )


def load_gate_state(run_dir: Path) -> dict[str, Any]:
    path = _state_path(run_dir)
    sidecar = path.with_name(f"{path.name}.sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("gate state and checksum sidecar are required")
    if sha256(path) != sidecar.read_text(encoding="utf-8").split()[0]:
        raise ValueError("gate state checksum mismatch")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _safe_existing_run_dir(value: str) -> Path:
    path = Path(value)
    if not value or not path.is_dir():
        raise ValueError("SCOPEBREAK_GATE_RUN_DIR must name an existing gate run")
    resolved = path.resolve()
    root = GATE_ROOT.resolve()
    if not resolved.is_relative_to(root) or "-gate-" not in path.name:
        raise ValueError("gate run directory is outside the immutable result root")
    return path


def _validate_result(
    result: ProviderRunResult,
    manifest: Mapping[str, Any],
    sample_dir: Path,
    remaining_cost: float,
) -> None:
    if result.phase != "trajectory":
        raise FrontierRunError("provider returned the wrong gate result phase")
    model = manifest["model"]
    if result.requested_model != model["requested_model"]:
        raise FrontierRunError("trajectory requested model differs from the manifest")
    if result.resolved_model != model["resolved_model"]:
        raise FrontierRunError("trajectory resolved model differs from frozen calibration")
    if result.reasoning_effort != model["reasoning_effort"] or float(
        result.temperature
    ) != float(model["temperature"]):
        raise FrontierRunError("trajectory model parameters differ from the manifest")
    if result.provider_errors or result.credential_exposure_detected:
        raise FrontierRunError("trajectory contains a provider or credential-exposure error")
    if not result.cleanup_success:
        raise FrontierRunError("trajectory cleanup did not pass")
    if result.malformed_tool_calls:
        raise FrontierRunError("trajectory contains malformed tool calls")
    if not result.terminal_state_reached and result.truncation_reason is None:
        raise FrontierRunError("trajectory is neither terminal nor explicitly truncated")
    if result.terminal_state_reached and result.truncation_reason is not None:
        raise FrontierRunError("trajectory cannot be terminal and truncated")
    if result.usage.actual_cost_usd > remaining_cost:
        raise FrontierRunError("trajectory exceeds the remaining gate cost ceiling")
    required = (
        sample_dir / "provider" / "telemetry.jsonl",
        sample_dir / "provider" / "scores.json",
        sample_dir / "provider" / "environment-image-digests.json",
        Path(result.inspect_log),
    )
    if any(not path.is_file() or path.stat().st_size == 0 for path in required):
        raise FrontierRunError("trajectory telemetry or Inspect artifacts are incomplete")
    load_jsonl(sample_dir / "provider" / "telemetry.jsonl")


def _backup_artifact(
    *,
    backup: BackupFunction,
    backup_uri: str,
    bundle: Path,
) -> dict[str, Any]:
    receipt = backup(backup_uri, Path.cwd(), bundle)
    if receipt.get("remote_copy_verified") is not True:
        raise FrontierRunError("incremental off-instance backup verification failed")
    return receipt


def _copy_final_backup_record(uri: str, path: Path) -> None:
    copy_to_remote(path, uri, path.name)
    sidecar = path.with_name(f"{path.name}.sha256")
    copy_to_remote(sidecar, uri, sidecar.name)


def _initial_state(
    run_dir: Path,
    manifest: Mapping[str, Any],
    git_commit: str,
    plan: tuple[GateSampleSpec, ...],
) -> dict[str, Any]:
    return {
        "study_name": manifest["study_name"],
        "run_id": run_dir.name,
        "git_commit": git_commit,
        "plan_sha256": gate_plan_sha256(plan),
        "status": "RUNNING_CANARIES",
        "next_index": 0,
        "completed_samples": [],
        "infrastructure_attempts": [],
        "total_actual_cost_usd": 0.0,
        "projected_gate_cost_usd": 0.0,
        "truncated_first_four": 0,
        "stop_reason": None,
    }


def create_canary_review_receipt(
    run_dir: Path,
    *,
    git_commit: str,
    reviewer_identifier: str,
) -> Path:
    """Checksum-bind a manual-review attestation after verifying both canary bundles."""
    state = load_gate_state(run_dir)
    if state.get("git_commit") != git_commit or state.get("status") != "CANARY_REVIEW_REQUIRED":
        raise ValueError("canary state is stale or not ready for review")
    completed = state.get("completed_samples", [])
    if len(completed) != CANARY_COUNT:
        raise ValueError("exactly two completed canaries are required")
    resolved_path = run_dir / "resolved-study-manifest.json"
    if not _checksum_valid(resolved_path):
        raise ValueError("resolved study manifest checksum is invalid")
    resolved: dict[str, Any] = json.loads(resolved_path.read_text(encoding="utf-8"))
    plan = resolved.get("gate_plan", [])
    sample_ids = [str(sample["sample_id"]) for sample in completed]
    for index, sample_id in enumerate(sample_ids):
        sample_dir = run_dir / sample_id
        manifest_path = sample_dir / "trajectory-manifest.json"
        backup_path = sample_dir / "backup-verification.json"
        prompt_path = sample_dir / "task-prompt.txt"
        spec_path = sample_dir / "sample-spec.json"
        if not all(
            _checksum_valid(path)
            for path in (manifest_path, backup_path, prompt_path, spec_path)
        ):
            raise ValueError("canary trajectory or backup manifest is missing")
        trajectory = json.loads(manifest_path.read_text(encoding="utf-8"))
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        expected_spec = plan[index] if len(plan) > index else None
        attempt = int(trajectory.get("attempt", 0))
        receipt_path = sample_dir / f"attempt-{attempt:02d}" / "trajectory-receipt.json"
        provider_dir = sample_dir / f"attempt-{attempt:02d}" / "provider"
        if not _checksum_valid(receipt_path):
            raise ValueError("canary provider receipt checksum is invalid")
        provider_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        prompt_hash = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        if (
            expected_spec is None
            or spec != expected_spec
            or trajectory.get("sample_id") != sample_id
            or trajectory.get("cell") != spec.get("cell")
            or trajectory.get("variant") != spec.get("variant")
            or trajectory.get("boundary") != spec.get("boundary")
            or trajectory.get("seed") != spec.get("seed")
            or trajectory.get("prompt_sha256") != prompt_hash
            or prompt_hash != resolved.get("prompt_hashes", {}).get(spec.get("boundary"))
            or trajectory.get("requested_model")
            != resolved.get("model", {}).get("requested_model")
            or trajectory.get("resolved_model")
            != resolved.get("model", {}).get("resolved_model")
            or provider_receipt.get("git_commit") != git_commit
            or provider_receipt.get("requested_model") != trajectory.get("requested_model")
            or provider_receipt.get("resolved_model") != trajectory.get("resolved_model")
            or trajectory.get("cleanup_success") is not True
            or trajectory.get("telemetry_complete") is not True
            or backup.get("remote_copy_verified") is not True
            or not (provider_dir / "telemetry.jsonl").is_file()
            or not (provider_dir / "scores.json").is_file()
            or not Path(str(provider_receipt.get("inspect_log", ""))).is_file()
        ):
            raise ValueError("canary automatic integrity checks did not pass")
    if not reviewer_identifier.strip():
        raise ValueError("a non-empty reviewer identifier is required")
    receipt = {
        "review_version": "1.0",
        "run_id": run_dir.name,
        "git_commit": git_commit,
        "reviewer_identifier": reviewer_identifier,
        "review_timestamp": datetime.now(UTC).isoformat(),
        "sample_ids": sample_ids,
        **{field: True for field in CANARY_REVIEW_FIELDS},
    }
    path = run_dir / "canary-review-receipt.json"
    if path.exists():
        raise ValueError("canary review receipt is immutable and already exists")
    _write_json(path, receipt)
    write_checksum(path)
    return path


def validate_canary_review_receipt(
    receipt_path: Path,
    *,
    run_dir: Path,
    git_commit: str,
) -> dict[str, Any]:
    sidecar = receipt_path.with_name(f"{receipt_path.name}.sha256")
    if not receipt_path.is_file() or not sidecar.is_file():
        raise ValueError("canary review receipt and sidecar are required")
    if sha256(receipt_path) != sidecar.read_text(encoding="utf-8").split()[0]:
        raise ValueError("canary review receipt checksum mismatch")
    receipt: dict[str, Any] = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("run_id") != run_dir.name or receipt.get("git_commit") != git_commit:
        raise ValueError("canary review receipt is stale or for another run")
    if receipt.get("review_version") != "1.0" or not str(
        receipt.get("reviewer_identifier", "")
    ).strip():
        raise ValueError("canary review receipt has no valid reviewer identity")
    if receipt.get("sample_ids") != [
        str(sample["sample_id"])
        for sample in load_gate_state(run_dir).get("completed_samples", [])[:CANARY_COUNT]
    ]:
        raise ValueError("canary review receipt names the wrong samples")
    if any(receipt.get(field) is not True for field in CANARY_REVIEW_FIELDS):
        raise ValueError("canary review receipt does not attest every required check")
    return receipt


def _trajectory_manifest(
    *,
    spec: GateSampleSpec,
    manifest: Mapping[str, Any],
    result: ProviderRunResult,
    attempt: int,
) -> dict[str, Any]:
    prompt = task_prompt(BoundaryCondition(spec.boundary))
    return {
        "sample_id": spec.sample_id,
        "execution_index": spec.index,
        "cell": spec.cell,
        "variant": spec.variant,
        "boundary": spec.boundary,
        "seed": spec.seed,
        "attempt": attempt,
        "requested_model": result.requested_model,
        "resolved_model": result.resolved_model,
        "reasoning_effort": result.reasoning_effort,
        "temperature": result.temperature,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "environment_image_digests": manifest["environment_image_digests"],
        "monitor": manifest["monitor"],
        "maximum_steps": manifest["agent"]["maximum_steps_per_sample"],
        "maximum_tool_calls": manifest["agent"]["maximum_tool_calls_per_sample"],
        "maximum_cumulative_input_tokens": manifest["token_limits"][
            "maximum_cumulative_input_tokens_per_sample"
        ],
        "maximum_cumulative_output_tokens": manifest["token_limits"][
            "maximum_cumulative_output_tokens_per_sample"
        ],
        "steps": result.steps,
        "tool_calls": result.tool_calls,
        "terminal_state_reached": result.terminal_state_reached,
        "terminal_reason": result.terminal_reason,
        "truncation_reason": result.truncation_reason,
        "task_success": result.task_success,
        "usage": result.usage.model_dump(mode="json"),
        "cleanup_success": result.cleanup_success,
        "telemetry_complete": True,
        "backup_verified": False,
    }


def run_gate_stage(
    manifest: dict[str, Any],
    *,
    git_commit: str,
    stage: Literal["canary", "remaining"],
    provider: FrontierProvider,
    backup: BackupFunction = upload_guarded_archive,
    run_dir_value: str = "",
    review_receipt_value: str = "",
) -> tuple[Path, dict[str, Any]]:
    """Run exactly the selected sequential stage and stop on every failed guard."""
    plan = build_gate_plan(manifest)
    backup_root = str(os.environ["SCOPEBREAK_BACKUP_URI"]).rstrip("/")
    if stage == "canary":
        if run_dir_value:
            raise ValueError("a canary stage must create a new immutable gate run")
        run_dir = new_gate_run_dir()
        run_dir.mkdir(parents=True, exist_ok=False)
        state = _initial_state(run_dir, manifest, git_commit, plan)
        resolved = {
            **manifest,
            "executing_git_commit": git_commit,
            "gate_plan": [sample.model_dump() for sample in plan],
            "gate_plan_sha256": gate_plan_sha256(plan),
        }
        _write_json(run_dir / "resolved-study-manifest.json", resolved)
        write_checksum(run_dir / "resolved-study-manifest.json")
        _write_state(run_dir, state)
        stop_index = CANARY_COUNT
    else:
        run_dir = _safe_existing_run_dir(run_dir_value)
        state = load_gate_state(run_dir)
        if state.get("git_commit") != git_commit or state.get(
            "plan_sha256"
        ) != gate_plan_sha256(plan):
            raise ValueError("gate run state is stale or has a different plan")
        if state.get("status") != "CANARY_REVIEW_REQUIRED" or state.get(
            "next_index"
        ) != CANARY_COUNT:
            raise ValueError("remaining stage requires exactly two completed canaries")
        validate_canary_review_receipt(
            Path(review_receipt_value), run_dir=run_dir, git_commit=git_commit
        )
        state["status"] = "RUNNING_REMAINING"
        _write_state(run_dir, state)
        stop_index = TOTAL_SAMPLES

    retry_limit = int(manifest["retry"]["infrastructure_sample_retries"])
    gate_ceiling = float(manifest["cost"]["gate_hard_maximum_usd"])
    while int(state["next_index"]) < stop_index:
        spec = plan[int(state["next_index"])]
        sample_dir = run_dir / spec.sample_id
        sample_dir.mkdir(parents=False, exist_ok=False)
        _write_json(sample_dir / "sample-spec.json", spec.model_dump(mode="json"))
        write_checksum(sample_dir / "sample-spec.json")
        prompt = task_prompt(BoundaryCondition(spec.boundary))
        (sample_dir / "task-prompt.txt").write_text(prompt, encoding="utf-8")
        write_checksum(sample_dir / "task-prompt.txt")
        result: ProviderRunResult | None = None
        attempt_used = 0
        for attempt in range(1, retry_limit + 2):
            attempt_used = attempt
            attempt_dir = sample_dir / f"attempt-{attempt:02d}"
            attempt_dir.mkdir(parents=False, exist_ok=False)
            remaining_cost = gate_ceiling - float(state["total_actual_cost_usd"])
            if remaining_cost <= 0:
                raise FrontierRunError("gate hard cost ceiling has been exhausted")
            try:
                result = provider.run_sample(
                    manifest,
                    attempt_dir / "provider",
                    sample_id=spec.sample_id,
                    cell=spec.cell,
                    variant=spec.variant,
                    boundary=spec.boundary,
                    seed=spec.seed,
                    cost_limit_usd=remaining_cost,
                )
                _validate_result(result, manifest, attempt_dir, remaining_cost)
                save_provider_receipt(result, attempt_dir, git_commit)
                break
            except RetryableInfrastructureError as error:
                failure = {
                    "sample_id": spec.sample_id,
                    "attempt": attempt,
                    "git_commit": git_commit,
                    "classification": "INFRASTRUCTURE_FAILURE",
                    "retryable": attempt <= retry_limit,
                    "api_request_made": False,
                    "error": f"{type(error).__name__}: {error}",
                }
                _write_json(attempt_dir / "failure.json", failure)
                write_checksum(attempt_dir / "failure.json")
                failure_uri = f"{backup_root}/{run_dir.name}/{spec.sample_id}/attempt-{attempt:02d}"
                _backup_artifact(backup=backup, backup_uri=failure_uri, bundle=attempt_dir)
                state["infrastructure_attempts"].append(failure)
                _write_state(run_dir, state)
                if attempt > retry_limit:
                    state["status"] = "STOPPED"
                    state["stop_reason"] = "infrastructure retry exhausted"
                    _write_state(run_dir, state)
                    raise
            except Exception as error:
                credential = os.environ.get("OPENAI_API_KEY", "")
                message = f"{type(error).__name__}: {error}"
                if credential:
                    message = message.replace(credential, "[REDACTED]")
                failure = {
                    "sample_id": spec.sample_id,
                    "attempt": attempt,
                    "git_commit": git_commit,
                    "classification": "FAILED_CLOSED",
                    "retryable": False,
                    "api_request_may_have_been_made": True,
                    "error": message,
                }
                _write_json(attempt_dir / "failure.json", failure)
                write_checksum(attempt_dir / "failure.json")
                failure_uri = (
                    f"{backup_root}/{run_dir.name}/{spec.sample_id}/attempt-{attempt:02d}"
                )
                _backup_artifact(backup=backup, backup_uri=failure_uri, bundle=attempt_dir)
                state["status"] = "STOPPED"
                state["stop_reason"] = "non-retryable sample failure"
                state["failed_sample"] = failure
                _write_state(run_dir, state)
                _copy_final_backup_record(
                    f"{backup_root}/{run_dir.name}", _state_path(run_dir)
                )
                raise FrontierRunError(message) from error
        if result is None:
            raise FrontierRunError("sample attempt loop ended without a preserved result")
        attempt_dir = sample_dir / f"attempt-{attempt_used:02d}"
        trajectory = _trajectory_manifest(
            spec=spec,
            manifest=manifest,
            result=result,
            attempt=attempt_used,
        )
        _write_json(sample_dir / "trajectory-manifest.json", trajectory)
        write_checksum(sample_dir / "trajectory-manifest.json")
        sample_uri = f"{backup_root}/{run_dir.name}/{spec.sample_id}"
        backup_receipt = _backup_artifact(backup=backup, backup_uri=sample_uri, bundle=sample_dir)
        backup_record = {
            "sample_id": spec.sample_id,
            "destination": sample_uri,
            "remote_copy_verified": True,
            "archive_sha256": backup_receipt["archive_sha256"],
            "inventory_sha256": backup_receipt["inventory_sha256"],
            "backup_run_id": backup_receipt["backup_run_id"],
        }
        _write_json(sample_dir / "backup-verification.json", backup_record)
        write_checksum(sample_dir / "backup-verification.json")
        _copy_final_backup_record(sample_uri, sample_dir / "backup-verification.json")
        trajectory["backup_verified"] = True
        _write_json(sample_dir / "trajectory-manifest.json", trajectory)
        write_checksum(sample_dir / "trajectory-manifest.json")
        _copy_final_backup_record(sample_uri, sample_dir / "trajectory-manifest.json")

        completed = {
            "sample_id": spec.sample_id,
            "cell": spec.cell,
            "seed": spec.seed,
            "attempts": attempt_used,
            "terminal": result.terminal_state_reached,
            "truncation_reason": result.truncation_reason,
            "task_success": result.task_success,
            "steps": result.steps,
            "tool_calls": result.tool_calls,
            "actual_cost_usd": result.usage.actual_cost_usd,
            "backup_verified": True,
        }
        state["completed_samples"].append(completed)
        state["next_index"] = int(state["next_index"]) + 1
        state["total_actual_cost_usd"] = round(
            float(state["total_actual_cost_usd"]) + result.usage.actual_cost_usd, 8
        )
        completed_count = len(state["completed_samples"])
        state["projected_gate_cost_usd"] = round(
            float(state["total_actual_cost_usd"]) / completed_count * TOTAL_SAMPLES, 8
        )
        state["truncated_first_four"] = sum(
            sample.get("truncation_reason") is not None
            for sample in state["completed_samples"][:4]
        )
        if float(state["total_actual_cost_usd"]) >= gate_ceiling:
            state["status"] = "STOPPED"
            state["stop_reason"] = "actual gate cost reached the hard ceiling"
        elif float(state["projected_gate_cost_usd"]) > gate_ceiling:
            state["status"] = "STOPPED"
            state["stop_reason"] = "projected gate cost exceeds the hard ceiling"
        elif int(state["truncated_first_four"]) >= 2:
            state["status"] = "STOPPED"
            state["stop_reason"] = "two of the first four trajectories truncated"
        elif not result.late_tool_reliability or result.malformed_tool_calls:
            state["status"] = "STOPPED"
            state["stop_reason"] = "tool integration degraded"
        _write_state(run_dir, state)
        run_uri = f"{backup_root}/{run_dir.name}"
        _copy_final_backup_record(run_uri, _state_path(run_dir))
        if state["status"] == "STOPPED":
            raise FrontierRunError(str(state["stop_reason"]))

    run_uri = f"{backup_root}/{run_dir.name}"
    if stop_index == CANARY_COUNT:
        state["status"] = "CANARY_REVIEW_REQUIRED"
        _write_state(run_dir, state)
        _copy_final_backup_record(run_uri, _state_path(run_dir))
    else:
        state["status"] = "FULL_BACKUP_REQUIRED"
        _write_state(run_dir, state)
        full_uri = f"{run_uri}/full-run"
        full_backup = _backup_artifact(backup=backup, backup_uri=full_uri, bundle=run_dir)
        full_record = {
            "run_id": run_dir.name,
            "destination": full_uri,
            "remote_copy_verified": True,
            "archive_sha256": full_backup["archive_sha256"],
            "inventory_sha256": full_backup["inventory_sha256"],
            "backup_run_id": full_backup["backup_run_id"],
        }
        _write_json(run_dir / "full-backup-verification.json", full_record)
        write_checksum(run_dir / "full-backup-verification.json")
        _copy_final_backup_record(full_uri, run_dir / "full-backup-verification.json")
        state["status"] = "GATE_COMPLETE"
        state["full_backup_verified"] = True
        state["full_backup_archive_sha256"] = full_backup["archive_sha256"]
        _write_state(run_dir, state)
        _copy_final_backup_record(run_uri, _state_path(run_dir))
    return run_dir, state
