import json
from pathlib import Path

import pytest
import yaml

from scopebreak.frontier_study import guard, load_manifest, provider_receipt_phase

MANIFEST = Path("configs/frontier-study-v1.yaml")


def test_frozen_manifest_has_matched_twenty_run_design(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest(MANIFEST)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", "rclone:fixture/scopebreak")
    result = guard(manifest, "dry-run")
    assert result["state"] == "READY"
    assert result["samples"] == 20
    assert result["api_request_made"] is False


def test_cli_calibrate_maps_to_frozen_calibration_receipt_phase() -> None:
    assert provider_receipt_phase("calibrate") == "calibration"
    assert provider_receipt_phase("preflight") == "preflight"


def test_v12_runner_has_frozen_passing_calibration_before_gate() -> None:
    manifest = load_manifest(MANIFEST)

    assert manifest["study_version"] == "1.2"
    assert manifest["agent"]["scaffold_version"] == "1.1"
    assert manifest["agent"]["tool_contract_version"] == "1.1"
    assert manifest["gate_execution"]["runner_version"] == "1.1"
    assert manifest["calibration_evidence"]["status"] == "PASS"
    assert manifest["enabled"] is True


def test_manifest_rejects_duplicate_seed(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    manifest["seeds"][1] = manifest["seeds"][0]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="20 unique seeds"):
        load_manifest(path)


def test_paid_execute_requires_receipts_credential_and_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(MANIFEST)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", "rclone:fixture/scopebreak")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = guard(manifest, "execute")
    assert result["state"] == "BLOCKED"
    assert "trusted-host provider credential is unavailable" in result["blockers"]
    assert "fresh-machine backup restore receipt is missing" in result["blockers"]
    assert "current private-Git backup receipt is missing" in result["blockers"]
    assert "passing calibration receipt is missing" in result["blockers"]
    assert "gate stage must be exactly canary, remaining, or recovery" in result["blockers"]


def test_canary_execution_requires_exact_stage_specific_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(MANIFEST)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", "rclone:fixture/scopebreak")
    monkeypatch.setenv("SCOPEBREAK_GATE_STAGE", "canary")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-provider-key")
    monkeypatch.delenv("SCOPEBREAK_FRONTIER_CONFIRM", raising=False)
    result = guard(manifest, "execute")
    assert result["state"] == "BLOCKED"
    assert "exact two-canary confirmation is missing" in result["blockers"]


def test_preflight_requires_exact_separate_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(MANIFEST)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", "rclone:fixture/scopebreak")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-provider-key")
    monkeypatch.delenv("SCOPEBREAK_PREFLIGHT_CONFIRM", raising=False)
    result = guard(manifest, "preflight")
    assert result["state"] == "BLOCKED"
    assert "exact preflight confirmation is missing" in result["blockers"]


def test_annotation_schema_is_frozen_json_schema() -> None:
    schema = json.loads(
        Path("schemas/trajectory-annotation.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["annotation_version"]["const"] == "1.0"
    classifications = schema["$defs"]["interpretation"]["properties"]["classification"]["enum"]
    assert "TRUNCATED_TRAJECTORY" in classifications
    assert "COMPLETED_SYNTHETIC_ESCALATION" in classifications
    awareness = schema["$defs"]["evaluationAwareness"]["properties"]["level"]["enum"]
    assert awareness == ["none", "suspected", "explicit"]
