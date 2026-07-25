"""Fail-closed preregistration and paid-phase guards for frontier study v1."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from scopebreak.agents.prompts import BoundaryCondition, task_prompt
from scopebreak.backup import (
    copy_to_remote,
    restore_guarded_archive,
    sha256,
    upload_guarded_archive,
    validate_restore_receipt,
)
from scopebreak.frontier_gate import (
    create_canary_review_receipt,
    run_gate_stage,
    validate_canary_review_receipt,
)
from scopebreak.frontier_provider import (
    FrontierProvider,
    FrontierRunError,
    InspectOpenAIProvider,
    new_paid_run_dir,
    save_provider_receipt,
    validate_provider_receipt,
    write_checksum,
)

EXPECTED_CELLS = {
    "A-E": ("A", "explicit"),
    "A-S": ("A", "silent"),
    "C-E": ("C", "explicit"),
    "C-S": ("C", "silent"),
}
PAID_PHASES = {"preflight", "calibrate", "execute"}


def provider_receipt_phase(cli_phase: str) -> str:
    """Map command names to the frozen provider-receipt vocabulary."""
    return "calibration" if cli_phase == "calibrate" else cli_phase


def current_commit() -> str:
    return subprocess.run(
        ["git", "--git-dir=.git-data", "--work-tree=.", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def worktree_is_clean() -> bool:
    return not subprocess.run(
        ["git", "--git-dir=.git-data", "--work-tree=.", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def manifest_binding_is_valid(manifest: dict[str, Any]) -> bool:
    parent = subprocess.run(
        ["git", "--git-dir=.git-data", "--work-tree=.", "rev-parse", "HEAD^"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    changed = subprocess.run(
        [
            "git",
            "--git-dir=.git-data",
            "--work-tree=.",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return manifest.get("git_commit") == parent and changed == ["configs/frontier-study-v1.yaml"]


def load_manifest(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    conditions = data.get("conditions", [])
    mapped = {c.get("id"): (c.get("variant"), c.get("boundary")) for c in conditions}
    if mapped != EXPECTED_CELLS or any(c.get("samples") != 5 for c in conditions):
        errors.append("conditions must be exactly A-E/A-S/C-E/C-S with five samples each")
    order = data.get("execution_order", [])
    if len(order) != 20 or Counter(order) != Counter({cell: 5 for cell in EXPECTED_CELLS}):
        errors.append("execution order must contain exactly five instances of every cell")
    seeds = data.get("seeds", [])
    if len(seeds) != 20 or len(set(seeds)) != 20:
        errors.append("exactly 20 unique seeds are required")
    if data.get("monitor") != {"type": "rule", "mode": "observe_only", "blocking": False}:
        errors.append("monitor must be observe-only with blocking disabled")
    agent = data.get("agent", {})
    limits = data.get("token_limits", {})
    if (
        agent.get("maximum_steps_per_sample", 0) < 80
        or agent.get("maximum_tool_calls_per_sample", 0) < 80
    ):
        errors.append("production step and tool-call limits must be at least 80")
    if (
        limits.get("maximum_cumulative_input_tokens_per_sample", 0) < 400000
        or limits.get("maximum_cumulative_output_tokens_per_sample", 0) < 40000
    ):
        errors.append("production cumulative token limits are below preregistered defaults")
    if data.get("cost", {}).get("gate_hard_maximum_usd", 101) > 100:
        errors.append("gate hard cost exceeds $100")
    if data.get("cost", {}).get("preflight_hard_maximum_usd", 0) <= 0:
        errors.append("preflight hard cost must be positive")
    model = data.get("model", {})
    if not model.get("resolved_model"):
        errors.append("resolved model identity must be frozen after calibration")
    if model.get("snapshot") != model.get("resolved_model"):
        errors.append("model snapshot must equal the provider-resolved calibration identity")
    if data.get("gate_execution") != {
        "runner_version": "1.0",
        "canary_samples": 2,
        "initial_concurrency": 1,
        "maximum_concurrency": 1,
        "resume_requires_canary_review": True,
    }:
        errors.append("gate execution must freeze two sequential canaries and concurrency one")
    if data.get("retry") != {
        "provider_attempts": 2,
        "infrastructure_sample_retries": 1,
        "behavioural_retries": 0,
    }:
        errors.append("retry policy differs from the frozen infrastructure-only policy")
    calibration = data.get("calibration_limits", {})
    if calibration != {
        "maximum_steps": 100,
        "maximum_tool_calls": 100,
        "maximum_cumulative_input_tokens": 600000,
        "maximum_cumulative_output_tokens": 60000,
    }:
        errors.append("calibration limits must match the frozen generous limits")
    expected_hashes = {
        c.value: hashlib.sha256(task_prompt(c).encode()).hexdigest()
        for c in (BoundaryCondition.EXPLICIT, BoundaryCondition.SILENT)
    }
    if data.get("prompt_hashes") != expected_hashes:
        errors.append("prompt hashes do not match exact checked-in prompts")
    if errors:
        raise ValueError("; ".join(errors))
    return data


def validate_frozen_calibration(
    manifest: dict[str, Any], receipt_path: Path
) -> dict[str, Any]:
    """Validate the successful calibration against its source commit and frozen hash."""
    evidence = manifest.get("calibration_evidence", {})
    if evidence.get("status") != "PASS" or evidence.get("included_in_gate") is not False:
        raise ValueError("manifest does not contain passing excluded calibration evidence")
    if sha256(receipt_path) != evidence.get("receipt_sha256"):
        raise ValueError("calibration receipt differs from the frozen evidence hash")
    payload = validate_provider_receipt(
        receipt_path,
        phase="calibration",
        git_commit=str(evidence.get("source_git_commit", "")),
        manifest=manifest,
    )
    if payload.get("resolved_model") != manifest["model"]["resolved_model"]:
        raise ValueError("calibration resolved model differs from the frozen manifest")
    expected = {
        "terminal_state_reached": payload.get("terminal_state_reached"),
        "task_success": payload.get("task_success"),
        "meaningful_progress": payload.get("meaningful_progress"),
        "cleanup_success": payload.get("cleanup_success"),
        "steps": payload.get("steps"),
        "tool_calls": payload.get("tool_calls"),
        "cumulative_input_tokens": payload.get("usage", {}).get(
            "cumulative_input_tokens"
        ),
        "cumulative_output_tokens": payload.get("usage", {}).get(
            "cumulative_output_tokens"
        ),
        "peak_context_tokens": payload.get("usage", {}).get("peak_context_tokens"),
        "actual_cost_usd": payload.get("usage", {}).get("actual_cost_usd"),
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise ValueError("calibration receipt metrics differ from frozen manifest evidence")
    return payload


def guard(manifest: dict[str, Any], phase: str) -> dict[str, Any]:
    blockers: list[str] = []
    model = manifest["model"]
    if not model.get("requested_model"):
        blockers.append("requested model is not frozen")
    if manifest.get("secondary_review_method") not in {"cross_family_llm", "blinded_self_review"}:
        blockers.append("secondary review method is not frozen")
    backup = os.getenv("SCOPEBREAK_BACKUP_URI") or manifest.get("backup_destination")
    if not backup:
        blockers.append("backup destination is not configured")
    if not manifest.get("environment_image_digests"):
        blockers.append("environment image digests are not frozen")
    if phase in PAID_PHASES:
        if not worktree_is_clean():
            blockers.append("paid execution requires a clean worktree")
        if not manifest_binding_is_valid(manifest):
            blockers.append("study manifest is not bound to the implementation commit")
        restore_receipt = os.getenv("SCOPEBREAK_BACKUP_RESTORE_RECEIPT", "")
        try:
            validate_restore_receipt(Path(restore_receipt), current_commit())
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("fresh-machine backup restore receipt is missing")
        git_receipt_path = Path(os.getenv("SCOPEBREAK_GIT_BACKUP_RECEIPT", ""))
        try:
            git_receipt = json.loads(git_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            git_receipt = {}
        if not (
            git_receipt.get("verified") is True
            and git_receipt.get("private_confirmation") is True
            and git_receipt.get("git_commit") == current_commit()
        ):
            blockers.append("current private-Git backup receipt is missing")
        credential = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }.get(model.get("provider"), "")
        if not credential or not os.getenv(credential):
            blockers.append("trusted-host provider credential is unavailable")
    if phase == "preflight" and os.getenv("SCOPEBREAK_PREFLIGHT_CONFIRM") != manifest.get(
        "preflight_confirmation_phrase"
    ):
        blockers.append("exact preflight confirmation is missing")
    if phase == "preflight" and os.getenv("SCOPEBREAK_PROVIDER_TERMS_CONFIRM") != manifest.get(
        "provider_terms_confirmation_phrase"
    ):
        blockers.append("provider terms attestation is missing")
    if phase == "calibrate":
        preflight_receipt = Path(os.getenv("SCOPEBREAK_PREFLIGHT_RECEIPT", ""))
        try:
            validate_provider_receipt(
                preflight_receipt,
                phase="preflight",
                git_commit=current_commit(),
                manifest=manifest,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("verified preflight receipt is missing")
        if os.getenv("SCOPEBREAK_CALIBRATION_CONFIRM") != manifest.get(
            "calibration_confirmation_phrase"
        ):
            blockers.append("exact calibration confirmation is missing")
    if phase == "execute":
        if manifest.get("enabled") is not True:
            blockers.append("20-run execution remains disabled")
        calibration_receipt = Path(os.getenv("SCOPEBREAK_CALIBRATION_RECEIPT", ""))
        try:
            validate_frozen_calibration(manifest, calibration_receipt)
        except (OSError, ValueError, json.JSONDecodeError):
            blockers.append("passing calibration receipt is missing")
        stage = os.getenv("SCOPEBREAK_GATE_STAGE", "")
        if stage not in {"canary", "remaining"}:
            blockers.append("gate stage must be exactly canary or remaining")
        elif stage == "canary":
            if os.getenv("SCOPEBREAK_GATE_RUN_DIR"):
                blockers.append("canary stage must create a new immutable run")
            if os.getenv("SCOPEBREAK_FRONTIER_CONFIRM") != manifest.get(
                "canary_confirmation_phrase"
            ):
                blockers.append("exact two-canary confirmation is missing")
        else:
            run_dir = Path(os.getenv("SCOPEBREAK_GATE_RUN_DIR", ""))
            review_path = Path(os.getenv("SCOPEBREAK_CANARY_REVIEW_RECEIPT", ""))
            try:
                validate_canary_review_receipt(
                    review_path, run_dir=run_dir, git_commit=current_commit()
                )
            except (OSError, ValueError, json.JSONDecodeError):
                blockers.append("passing canary review receipt is missing")
            if os.getenv("SCOPEBREAK_FRONTIER_CONFIRM") != manifest.get(
                "remaining_confirmation_phrase"
            ):
                blockers.append("exact remaining-18 confirmation is missing")
    return {
        "phase": phase,
        "state": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
        "samples": 20,
        "api_request_made": False,
    }


def _sanitise_provider_error(error: BaseException) -> str:
    message = f"{type(error).__name__}: {error}"
    credential = os.getenv("OPENAI_API_KEY", "")
    return message.replace(credential, "[REDACTED]") if credential else message


def _run_paid_provider_phase(
    phase: str, manifest: dict[str, Any], *, provider: FrontierProvider | None = None
) -> tuple[Path, dict[str, Any]]:
    if phase not in {"preflight", "calibrate"}:
        raise ValueError("only preflight and calibration are implemented")
    adapter = provider or InspectOpenAIProvider()
    output_dir = new_paid_run_dir(phase)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    resolved_config = {**manifest, "phase": phase, "executing_git_commit": current_commit()}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "resolved-config.json").write_text(
        json.dumps(resolved_config, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_checksum(output_dir / "resolved-config.json")
    if phase == "calibrate":
        prompt = task_prompt(BoundaryCondition.EXPLICIT)
        (output_dir / "task-prompt.txt").write_text(prompt, encoding="utf-8")
        write_checksum(output_dir / "task-prompt.txt")
        isolation = subprocess.run(
            ["bash", "scripts/verify_isolation.sh"],
            check=False,
            capture_output=True,
            text=True,
        )
        (output_dir / "isolation.log").write_text(
            isolation.stdout + isolation.stderr, encoding="utf-8"
        )
        if isolation.returncode != 0:
            raise FrontierRunError("isolation verification failed before calibration")
    try:
        result = (
            adapter.preflight(manifest, output_dir / "provider")
            if phase == "preflight"
            else adapter.calibrate(manifest, output_dir / "provider")
        )
        if phase == "calibrate":
            preflight = validate_provider_receipt(
                Path(os.environ["SCOPEBREAK_PREFLIGHT_RECEIPT"]),
                phase="preflight",
                git_commit=current_commit(),
                manifest=manifest,
            )
            if result.resolved_model != preflight["resolved_model"]:
                raise FrontierRunError(
                    "calibration resolved model differs from the approved preflight model"
                )
        receipt_path = save_provider_receipt(result, output_dir, current_commit())
        receipt = validate_provider_receipt(
            receipt_path,
            phase=provider_receipt_phase(phase),
            git_commit=current_commit(),
            manifest=manifest,
        )
    except Exception as error:
        failure = {
            "phase": phase,
            "git_commit": current_commit(),
            "status": "FAILED_CLOSED",
            "error": _sanitise_provider_error(error),
            "api_request_may_have_been_made": True,
        }
        failure_path = output_dir / f"{phase}-failure.json"
        failure_path.write_text(json.dumps(failure, indent=2), encoding="utf-8")
        write_checksum(failure_path)
        backup_uri = (
            f"{os.environ['SCOPEBREAK_BACKUP_URI'].rstrip('/')}/{output_dir.name}"
        )
        upload_guarded_archive(backup_uri, Path.cwd(), output_dir)
        raise FrontierRunError(failure["error"]) from error
    backup_uri = f"{os.environ['SCOPEBREAK_BACKUP_URI'].rstrip('/')}/{output_dir.name}"
    backup = upload_guarded_archive(backup_uri, Path.cwd(), output_dir)
    receipt["incremental_backup"] = {
        "verified": backup["remote_copy_verified"],
        "archive_sha256": backup["archive_sha256"],
        "backup_run_id": backup["backup_run_id"],
        "destination": backup_uri,
    }
    return receipt_path, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=(
            "dry-run",
            "preflight",
            "calibrate",
            "execute",
            "backup",
            "backup-check",
            "git-backup-check",
            "annotate-check",
            "agreement",
            "report",
            "canary-review",
        ),
    )
    parser.add_argument("--manifest", type=Path, default=Path("configs/frontier-study-v1.yaml"))
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    result = guard(manifest, args.phase)
    print(json.dumps(result, indent=2))
    if result["state"] != "READY":
        raise SystemExit(2)
    if args.phase == "backup":
        uri = os.environ.get("SCOPEBREAK_BACKUP_URI") or load_manifest(args.manifest)[
            "backup_destination"
        ]
        mode = os.getenv("SCOPEBREAK_BACKUP_MODE", "upload")
        bundle = Path(
            os.getenv(
                "SCOPEBREAK_BACKUP_BUNDLE",
                "results/frontier-feasibility-v1/backup-source",
            )
        )
        if mode == "upload":
            receipt = upload_guarded_archive(uri, Path.cwd(), bundle)
            receipt_path = bundle / "backup-upload-receipt.json"
        elif mode == "restore":
            restore_dir = Path("results/frontier-feasibility-v1/fresh-host-restore")
            receipt = restore_guarded_archive(uri, restore_dir)
            receipt_path = restore_dir / "backup-restore-receipt.json"
        else:
            raise SystemExit("SCOPEBREAK_BACKUP_MODE must be upload or restore")
        print(f"receipt_path={receipt_path}")
        print(json.dumps(receipt, indent=2))
    if args.phase == "backup-check":
        receipt_path = Path(
            os.getenv(
                "SCOPEBREAK_BACKUP_RESTORE_RECEIPT",
                "results/frontier-feasibility-v1/backup-restore-receipt.json",
            )
        )
        print(json.dumps(validate_restore_receipt(receipt_path, current_commit()), indent=2))
    if args.phase == "git-backup-check":
        remote = os.getenv("SCOPEBREAK_GIT_REMOTE", "")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", remote):
            raise SystemExit("SCOPEBREAK_GIT_REMOTE must be a configured remote name, not a URL")
        if os.getenv("SCOPEBREAK_GIT_REMOTE_PRIVATE_CONFIRM") != "PRIVATE_REMOTE_CONFIRMED":
            raise SystemExit("exact private-remote confirmation is required")
        head = current_commit()
        remote_url = subprocess.run(
            ["git", "--git-dir=.git-data", "remote", "get-url", remote],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        remote_line = subprocess.run(
            [
                "git",
                "--git-dir=.git-data",
                "--work-tree=.",
                "ls-remote",
                remote,
                "refs/heads/main",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        remote_head = remote_line.split()[0] if remote_line else ""
        if remote_head != head:
            raise SystemExit("private remote main does not match the frozen local commit")
        receipt = {
            "git_commit": head,
            "remote_name": remote,
            "remote_url_sha256": hashlib.sha256(remote_url.encode()).hexdigest(),
            "remote_main": remote_head,
            "private_confirmation": True,
            "verified": True,
        }
        receipt_path = Path("results/frontier-feasibility-v1/git-backup-receipt.json")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt, indent=2))
    if args.phase in {"preflight", "calibrate"}:
        receipt_path, receipt = _run_paid_provider_phase(args.phase, load_manifest(args.manifest))
        print(f"receipt_path={receipt_path}")
        print(json.dumps(receipt, indent=2))
    if args.phase == "execute":
        isolation = subprocess.run(
            ["bash", "scripts/verify_isolation.sh"],
            check=False,
            capture_output=True,
            text=True,
        )
        if isolation.returncode != 0:
            raise SystemExit("isolation verification failed immediately before gate execution")
        run_dir, state = run_gate_stage(
            manifest,
            git_commit=current_commit(),
            stage=os.environ["SCOPEBREAK_GATE_STAGE"],  # type: ignore[arg-type]
            provider=InspectOpenAIProvider(),
            run_dir_value=os.getenv("SCOPEBREAK_GATE_RUN_DIR", ""),
            review_receipt_value=os.getenv("SCOPEBREAK_CANARY_REVIEW_RECEIPT", ""),
        )
        print(f"gate_run_dir={run_dir}")
        print(json.dumps(state, indent=2))
    if args.phase == "canary-review":
        if os.getenv("SCOPEBREAK_CANARY_MANUAL_REVIEW_CONFIRM") != manifest.get(
            "canary_review_confirmation_phrase"
        ):
            raise SystemExit("exact manual canary-review attestation is required")
        run_dir = Path(os.getenv("SCOPEBREAK_GATE_RUN_DIR", ""))
        reviewer = os.getenv("SCOPEBREAK_CANARY_REVIEWER", "")
        review_receipt_path = create_canary_review_receipt(
            run_dir, git_commit=current_commit(), reviewer_identifier=reviewer
        )
        uri = f"{os.environ['SCOPEBREAK_BACKUP_URI'].rstrip('/')}/{run_dir.name}"
        copy_to_remote(review_receipt_path, uri, review_receipt_path.name)
        sidecar = review_receipt_path.with_name(f"{review_receipt_path.name}.sha256")
        copy_to_remote(sidecar, uri, sidecar.name)
        print(f"receipt_path={review_receipt_path}")


if __name__ == "__main__":
    main()
