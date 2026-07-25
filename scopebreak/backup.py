"""Checksum-verified backup operations without embedded credentials."""

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_root(uri: str) -> Path | None:
    if uri.startswith("file://"):
        return Path(uri.removeprefix("file://"))
    if uri.startswith("/"):
        return Path(uri)
    return None


def copy_to_remote(source: Path, uri: str, remote_name: str) -> None:
    local = _local_root(uri)
    if local is not None:
        local.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local / remote_name)
        return
    if uri.startswith("rclone:"):
        remote = uri.removeprefix("rclone:").rstrip("/")
        subprocess.run(
            ["rclone", "copyto", str(source), f"{remote}/{remote_name}"], check=True
        )
        return
    raise ValueError(
        "backup URI must be file:///absolute/path, /absolute/path, or rclone:remote/path"
    )


def restore_from_remote(uri: str, remote_name: str, destination: Path) -> None:
    local = _local_root(uri)
    if local is not None:
        shutil.copy2(local / remote_name, destination)
        return
    if uri.startswith("rclone:"):
        remote = uri.removeprefix("rclone:").rstrip("/")
        subprocess.run(
            ["rclone", "copyto", f"{remote}/{remote_name}", str(destination)], check=True
        )
        return
    raise ValueError("unsupported backup URI")


def round_trip_test(uri: str) -> dict[str, Any]:
    """Upload harmless bytes, restore separately, and compare checksums."""
    with tempfile.TemporaryDirectory(prefix="scopebreak-backup-") as directory:
        root = Path(directory)
        source = root / "backup-test.json"
        restored = root / "restored.json"
        source.write_text(
            json.dumps({"study": "scopebreak-frontier-feasibility-v1", "synthetic": True}),
            encoding="utf-8",
        )
        remote_name = "scopebreak-backup-preflight.json"
        expected = sha256(source)
        copy_to_remote(source, uri, remote_name)
        restore_from_remote(uri, remote_name, restored)
        actual = sha256(restored)
        if actual != expected:
            raise RuntimeError("restored backup checksum does not match upload")
        return {
            "backup_uri": uri,
            "remote_name": remote_name,
            "sha256": expected,
            "restore_sha256": actual,
            "verified": True,
        }
