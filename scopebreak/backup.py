"""Checksum-verified backup operations without embedded credentials."""

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ARCHIVE_ROOTS = ("annotations", "docs", "schemas", "configs", ".git-data")
ARCHIVE_FILES = ("uv.lock", "pyproject.toml", "Makefile")
SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def machine_identity() -> str:
    machine_id = Path("/etc/machine-id")
    value = machine_id.read_text(encoding="utf-8").strip() if machine_id.exists() else ""
    return hashlib.sha256(f"{value}:{socket.gethostname()}".encode()).hexdigest()


def archive_inventory(repo: Path, result_bundle: Path) -> tuple[Path, ...]:
    """Return only preregistered roots plus one explicit result bundle."""
    candidates: list[Path] = []
    for name in ARCHIVE_ROOTS:
        root = repo / name
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    candidates.extend(repo / name for name in ARCHIVE_FILES if (repo / name).is_file())
    candidates.extend(path for path in result_bundle.rglob("*") if path.is_file())
    resolved = tuple(sorted({path.resolve() for path in candidates}))
    forbidden_names = {".env", "credentials", "credentials.json", "auth.json"}
    secret_values = [os.environ[name].encode() for name in SECRET_ENV_NAMES if os.getenv(name)]
    for path in resolved:
        lowered = path.name.lower()
        if lowered in forbidden_names or path.suffix.lower() in {".pem", ".key", ".p12"}:
            raise ValueError(f"credential-bearing filename rejected: {path}")
        if secret_values:
            content = path.read_bytes()
            if any(value in content for value in secret_values):
                raise ValueError(f"trusted-host credential value found in backup candidate: {path}")
    return resolved


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


def upload_restore_fixture(uri: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="scopebreak-backup-") as directory:
        root = Path(directory)
        payload = root / "payload.json"
        receipt_path = root / "receipt.json"
        payload.write_text(
            json.dumps({"nonce": secrets.token_hex(32), "synthetic": True}), encoding="utf-8"
        )
        payload_name = "scopebreak-backup-preflight-payload.json"
        receipt = {
            "source_machine_id": machine_identity(),
            "payload_name": payload_name,
            "payload_sha256": sha256(payload),
            "fresh_host_restore_verified": False,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        copy_to_remote(payload, uri, payload_name)
        copy_to_remote(receipt_path, uri, "scopebreak-backup-preflight-receipt.json")
        return receipt


def verify_restore_on_fresh_host(uri: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="scopebreak-restore-") as directory:
        root = Path(directory)
        receipt_path = root / "receipt.json"
        restore_from_remote(uri, "scopebreak-backup-preflight-receipt.json", receipt_path)
        receipt: dict[str, Any] = json.loads(receipt_path.read_text(encoding="utf-8"))
        current = machine_identity()
        if current == receipt["source_machine_id"]:
            raise RuntimeError("restore must be verified on a different machine identity")
        payload = root / "payload.json"
        restore_from_remote(uri, str(receipt["payload_name"]), payload)
        actual = sha256(payload)
        if actual != receipt["payload_sha256"]:
            raise RuntimeError("fresh-host restored checksum does not match upload")
        return {
            **receipt,
            "restore_machine_id": current,
            "restore_sha256": actual,
            "fresh_host_restore_verified": True,
        }


def round_trip_test(uri: str) -> dict[str, Any]:
    """Mechanism test only; same-host restore never satisfies the paid gate."""
    receipt = upload_restore_fixture(uri)
    with tempfile.TemporaryDirectory(prefix="scopebreak-same-host-") as directory:
        restored = Path(directory) / "payload.json"
        restore_from_remote(uri, str(receipt["payload_name"]), restored)
        actual = sha256(restored)
    return {
        **receipt,
        "restore_sha256": actual,
        "checksum_verified": actual == receipt["payload_sha256"],
        "fresh_host_restore_verified": False,
    }
