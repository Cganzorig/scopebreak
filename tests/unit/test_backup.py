from pathlib import Path

import pytest

from scopebreak.backup import archive_inventory, round_trip_test, verify_restore_on_fresh_host


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
    (repo / "docs/guide.md").write_text("safe", encoding="utf-8")
    (repo / ".env").write_text("OPENAI_API_KEY=not-archived", encoding="utf-8")
    result = repo / "results/run"
    (result / "sample/log.eval").write_text("observable", encoding="utf-8")
    inventory = archive_inventory(repo, result)
    assert (repo / "docs/guide.md").resolve() in inventory
    assert (repo / ".env").resolve() not in inventory

    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-for-test")
    (result / "sample/log.eval").write_text("secret-value-for-test", encoding="utf-8")
    with pytest.raises(ValueError, match="credential value"):
        archive_inventory(repo, result)
