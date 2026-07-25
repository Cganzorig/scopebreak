import json
from pathlib import Path

import pytest

from scopebreak.backup import (
    _rclone_remote,
    archive_inventory,
    round_trip_test,
    sha256,
    validate_restore_receipt,
    verify_restore_on_fresh_host,
)


def test_rclone_uri_is_translated_to_remote_syntax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = "ganzorig:\n"

    monkeypatch.setattr("scopebreak.backup.subprocess.run", lambda *args, **kwargs: Completed())
    assert (
        _rclone_remote("rclone:ganzorig/scopebreak-research/frontier-feasibility-v1")
        == "ganzorig:scopebreak-research/frontier-feasibility-v1"
    )


def test_rclone_uri_rejects_unconfigured_or_malformed_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = "other:\n"

    monkeypatch.setattr("scopebreak.backup.subprocess.run", lambda *args, **kwargs: Completed())
    with pytest.raises(ValueError, match="not configured"):
        _rclone_remote("rclone:ganzorig/scopebreak-research")
    with pytest.raises(ValueError, match="remote/path"):
        _rclone_remote("rclone:ganzorig")


def test_backup_round_trip_restores_identical_checksum(tmp_path: Path) -> None:
    receipt = round_trip_test(f"file://{tmp_path / 'remote'}")
    assert receipt["checksum_verified"] is True
    assert receipt["fresh_host_restore_verified"] is False
    assert receipt["payload_sha256"] == receipt["restore_sha256"]
    with pytest.raises(RuntimeError, match="different machine identity"):
        verify_restore_on_fresh_host(f"file://{tmp_path / 'remote'}")


def test_archive_inventory_is_allowlisted_and_rejects_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "results/run/sample").mkdir(parents=True)
    (repo / "results/run/sample/backup-support").mkdir()
    (repo / "results/run/backup-support").mkdir()
    (repo / "docs/guide.md").write_text("safe", encoding="utf-8")
    (repo / ".env").write_text("OPENAI_API_KEY=not-archived", encoding="utf-8")
    result = repo / "results/run"
    (result / "sample/log.eval").write_text("observable", encoding="utf-8")
    (result / "sample/backup-support/scopebreak-history.bundle").write_text(
        "nested", encoding="utf-8"
    )
    (result / "backup-support/scopebreak-history.bundle").write_text(
        "selected", encoding="utf-8"
    )
    inventory = archive_inventory(repo, result)
    assert (repo / "docs/guide.md").resolve() in inventory
    assert (repo / ".env").resolve() not in inventory
    assert (result / "backup-support/scopebreak-history.bundle").resolve() in inventory
    assert (result / "sample/backup-support/scopebreak-history.bundle").resolve() not in inventory

    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-for-test")
    (result / "sample/log.eval").write_text("secret-value-for-test", encoding="utf-8")
    with pytest.raises(ValueError, match="credential value"):
        archive_inventory(repo, result)


def test_restore_receipt_is_checksum_bound_and_rejects_same_host(tmp_path: Path) -> None:
    receipt = {
        "backup_run_id": "test",
        "source_uri": "rclone:fixture/path",
        "source_machine_id": "same",
        "restore_machine_id": "same",
        "restore_timestamp": "2026-07-25T00:00:00Z",
        "git_commit": "abc",
        "archive_sha256": "one",
        "restored_archive_sha256": "one",
        "inventory_sha256": "two",
        "restored_inventory_sha256": "two",
        "checksum_match": True,
        "archive_opened": True,
        "git_history_verified": True,
        "credential_scan_passed": True,
        "fresh_host_restore_verified": True,
    }
    path = tmp_path / "backup-restore-receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    sidecar = tmp_path / "backup-restore-receipt.json.sha256"
    sidecar.write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="identities must differ"):
        validate_restore_receipt(path, "abc")
