import json
from pathlib import Path

import pytest
import yaml

from scopebreak.frontier_study import guard, load_manifest

MANIFEST = Path("configs/frontier-study-v1.yaml")


def test_frozen_manifest_has_matched_twenty_run_design(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest(MANIFEST)
    monkeypatch.setenv("SCOPEBREAK_BACKUP_URI", "rclone:fixture/scopebreak")
    result = guard(manifest, "dry-run")
    assert result["state"] == "READY"
    assert result["samples"] == 20
    assert result["api_request_made"] is False


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
    assert "passing calibration receipt is missing" in result["blockers"]
    assert "exact 20-run confirmation is missing" in result["blockers"]


def test_annotation_schema_is_frozen_json_schema() -> None:
    schema = json.loads(
        Path("schemas/trajectory-annotation.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["annotation_version"]["const"] == "1.0"
    classifications = schema["$defs"]["interpretation"]["properties"]["classification"]["enum"]
    assert "TRUNCATED_TRAJECTORY" in classifications
    assert "COMPLETED_SYNTHETIC_ESCALATION" in classifications
