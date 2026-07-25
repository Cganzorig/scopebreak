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
    restore_guarded_archive,
    upload_guarded_archive,
    validate_restore_receipt,
)

EXPECTED_CELLS = {
    "A-E": ("A", "explicit"),
    "A-S": ("A", "silent"),
    "C-E": ("C", "explicit"),
    "C-S": ("C", "silent"),
}
PAID_PHASES = {"preflight", "calibrate", "execute"}


def current_commit() -> str:
    return subprocess.run(
        ["git", "--git-dir=.git-data", "--work-tree=.", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
    expected_hashes = {
        c.value: hashlib.sha256(task_prompt(c).encode()).hexdigest()
        for c in (BoundaryCondition.EXPLICIT, BoundaryCondition.SILENT)
    }
    if data.get("prompt_hashes") != expected_hashes:
        errors.append("prompt hashes do not match exact checked-in prompts")
    if errors:
        raise ValueError("; ".join(errors))
    return data


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
    if phase == "calibrate" and not os.getenv("SCOPEBREAK_PREFLIGHT_RECEIPT"):
        blockers.append("verified preflight receipt is missing")
    if phase == "execute":
        if not os.getenv("SCOPEBREAK_CALIBRATION_RECEIPT"):
            blockers.append("passing calibration receipt is missing")
        if os.getenv("SCOPEBREAK_FRONTIER_CONFIRM") != manifest["confirmation_phrase"]:
            blockers.append("exact 20-run confirmation is missing")
    return {
        "phase": phase,
        "state": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
        "samples": 20,
        "api_request_made": False,
    }


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
        ),
    )
    parser.add_argument("--manifest", type=Path, default=Path("configs/frontier-study-v1.yaml"))
    args = parser.parse_args()
    result = guard(load_manifest(args.manifest), args.phase)
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
        elif mode == "restore":
            receipt = restore_guarded_archive(
                uri, Path("results/frontier-feasibility-v1/fresh-host-restore")
            )
        else:
            raise SystemExit("SCOPEBREAK_BACKUP_MODE must be upload or restore")
        receipt_path = Path(f"results/frontier-feasibility-v1/backup-{mode}-receipt.json")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
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
    if args.phase in PAID_PHASES:
        raise SystemExit(
            "Paid adapter remains disarmed until its phase implementation "
            "and receipts are verified."
        )


if __name__ == "__main__":
    main()
