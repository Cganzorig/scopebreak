from pathlib import Path

from scopebreak.backup import round_trip_test


def test_backup_round_trip_restores_identical_checksum(tmp_path: Path) -> None:
    receipt = round_trip_test(f"file://{tmp_path / 'remote'}")
    assert receipt["verified"] is True
    assert receipt["sha256"] == receipt["restore_sha256"]
