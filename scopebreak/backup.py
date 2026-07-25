"""Checksum-verified backup operations without embedded credentials."""

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from datetime import UTC, datetime
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
REQUIRED_RESTORE_FIELDS = (
    "backup_run_id",
    "source_uri",
    "source_machine_id",
    "restore_machine_id",
    "restore_timestamp",
    "git_commit",
    "archive_sha256",
    "restored_archive_sha256",
    "inventory_sha256",
    "restored_inventory_sha256",
    "checksum_match",
    "archive_opened",
    "git_history_verified",
    "credential_scan_passed",
    "fresh_host_restore_verified",
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
    for path in result_bundle.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(result_bundle)
        nested_support = (
            "backup-support" in relative.parts and relative.parts[0] != "backup-support"
        )
        if (
            nested_support
            or path.name.endswith((".tar.zst", ".tar.zst.sha256"))
            or path.name.startswith("backup-upload-receipt")
            or path.name.startswith("backup-restore-receipt")
        ):
            continue
        candidates.append(path)
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


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-data", "--work-tree=.", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_checksum(path: Path) -> Path:
    checksum_path = path.with_name(f"{path.name}.sha256")
    checksum_path.write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")
    return checksum_path


def _read_checksum(path: Path) -> str:
    return path.read_text(encoding="utf-8").split()[0]


def _scan_archive_names(names: list[str]) -> None:
    forbidden = {".env", "credentials", "credentials.json", "auth.json"}
    for name in names:
        path = Path(name)
        if path.name.lower() in forbidden or path.suffix.lower() in {".pem", ".key", ".p12"}:
            raise ValueError(f"credential-bearing archive member rejected: {name}")


def create_archive(repo: Path, result_bundle: Path, archive: Path) -> dict[str, Any]:
    """Create a zstd archive from a fixed repository allowlist and one result bundle."""
    repo = repo.resolve()
    result_bundle = result_bundle.resolve()
    allowed_results = (repo / "results/frontier-feasibility-v1").resolve()
    if not result_bundle.is_relative_to(allowed_results):
        raise ValueError("result bundle must be under results/frontier-feasibility-v1")
    result_bundle.mkdir(parents=True, exist_ok=True)
    support = result_bundle / "backup-support"
    support.mkdir(parents=True, exist_ok=True)
    history_bundle = support / "scopebreak-history.bundle"
    subprocess.run(
        [
            "git",
            "--git-dir=.git-data",
            "--work-tree=.",
            "bundle",
            "create",
            str(history_bundle),
            "--all",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "--git-dir=.git-data", "bundle", "verify", str(history_bundle)],
        cwd=repo,
        check=True,
    )

    inventory_path = support / "backup-inventory.json"
    inventory = archive_inventory(repo, result_bundle)
    entries = [
        {"path": str(path.relative_to(repo)), "sha256": sha256(path)}
        for path in inventory
        if path != inventory_path.resolve()
    ]
    inventory_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    members = [entry["path"] for entry in entries] + [str(inventory_path.relative_to(repo))]
    _scan_archive_names(members)

    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as names:
        names.write("\n".join(members) + "\n")
        names.flush()
        subprocess.run(
            [
                "tar",
                "--zstd",
                "-cf",
                str(archive),
                "-C",
                str(repo),
                "--files-from",
                names.name,
            ],
            check=True,
        )
    return {
        "archive_sha256": sha256(archive),
        "inventory_sha256": sha256(inventory_path),
        "inventory_path": str(inventory_path.relative_to(repo)),
        "git_commit": _git(repo, "rev-parse", "HEAD"),
        "credential_scan_passed": True,
        "member_count": len(members),
    }


def _local_root(uri: str) -> Path | None:
    if uri.startswith("file://"):
        return Path(uri.removeprefix("file://"))
    if uri.startswith("/"):
        return Path(uri)
    return None


def _rclone_remote(uri: str) -> str | None:
    """Translate the public rclone:remote/path URI into rclone's remote:path form."""
    if not uri.startswith("rclone:"):
        return None
    value = uri.removeprefix("rclone:").strip().rstrip("/")
    remote_name, separator, remote_path = value.partition("/")
    if not separator or not remote_name or not remote_path:
        raise ValueError("rclone backup URI must be rclone:remote/path")
    if ":" in remote_name:
        raise ValueError("rclone remote name must not contain ':'")
    configured = subprocess.run(
        ["rclone", "listremotes"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    expected = f"{remote_name}:"
    if expected not in configured:
        raise ValueError(f"rclone remote is not configured: {remote_name}")
    return f"{expected}{remote_path}"


def copy_to_remote(source: Path, uri: str, remote_name: str) -> None:
    local = _local_root(uri)
    if local is not None:
        local.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local / remote_name)
        return
    remote = _rclone_remote(uri)
    if remote is not None:
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
    remote = _rclone_remote(uri)
    if remote is not None:
        subprocess.run(
            ["rclone", "copyto", f"{remote}/{remote_name}", str(destination)], check=True
        )
        return
    raise ValueError("unsupported backup URI")


def upload_guarded_archive(uri: str, repo: Path, result_bundle: Path) -> dict[str, Any]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"scopebreak-frontier-feasibility-v1-{run_id}.tar.zst"
    archive = result_bundle / archive_name
    details = create_archive(repo, result_bundle, archive)
    checksum = _write_checksum(archive)
    receipt: dict[str, Any] = {
        "backup_run_id": run_id,
        "source_uri": uri,
        "source_machine_id": machine_identity(),
        "upload_timestamp": datetime.now(UTC).isoformat(),
        "archive_name": archive_name,
        "archive_sha256": details["archive_sha256"],
        "inventory_sha256": details["inventory_sha256"],
        "inventory_path": details["inventory_path"],
        "git_commit": details["git_commit"],
        "credential_scan_passed": details["credential_scan_passed"],
        "member_count": details["member_count"],
        "remote_copy_verified": False,
        "fresh_host_restore_verified": False,
    }
    receipt_path = result_bundle / "backup-upload-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt_checksum = _write_checksum(receipt_path)
    for path in (archive, checksum, receipt_path, receipt_checksum):
        copy_to_remote(path, uri, path.name)
    with tempfile.TemporaryDirectory(prefix="scopebreak-upload-verify-") as directory:
        restored_archive = Path(directory) / archive.name
        restore_from_remote(uri, archive.name, restored_archive)
        if sha256(restored_archive) != details["archive_sha256"]:
            raise RuntimeError("uploaded archive checksum verification failed")
    receipt["remote_copy_verified"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt_checksum = _write_checksum(receipt_path)
    copy_to_remote(receipt_path, uri, receipt_path.name)
    copy_to_remote(receipt_checksum, uri, receipt_checksum.name)
    with tempfile.TemporaryDirectory(prefix="scopebreak-receipt-verify-") as directory:
        restored_receipt = Path(directory) / receipt_path.name
        restored_checksum = Path(directory) / receipt_checksum.name
        restore_from_remote(uri, receipt_path.name, restored_receipt)
        restore_from_remote(uri, receipt_checksum.name, restored_checksum)
        if sha256(restored_receipt) != _read_checksum(restored_checksum):
            raise RuntimeError("uploaded receipt checksum verification failed")
    return receipt


def restore_guarded_archive(uri: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_receipt = output_dir / "backup-upload-receipt.json"
    upload_checksum = output_dir / "backup-upload-receipt.json.sha256"
    restore_from_remote(uri, upload_receipt.name, upload_receipt)
    restore_from_remote(uri, upload_checksum.name, upload_checksum)
    if sha256(upload_receipt) != _read_checksum(upload_checksum):
        raise RuntimeError("upload receipt checksum mismatch")
    source: dict[str, Any] = json.loads(upload_receipt.read_text(encoding="utf-8"))
    current_machine = machine_identity()
    if current_machine == source["source_machine_id"]:
        raise RuntimeError("restore must be verified on a different machine identity")

    archive = output_dir / str(source["archive_name"])
    archive_checksum = output_dir / f"{source['archive_name']}.sha256"
    restore_from_remote(uri, archive.name, archive)
    restore_from_remote(uri, archive_checksum.name, archive_checksum)
    restored_hash = sha256(archive)
    checksum_match = (
        restored_hash == source["archive_sha256"] == _read_checksum(archive_checksum)
    )
    if not checksum_match:
        raise RuntimeError("restored archive checksum mismatch")

    listing = subprocess.run(
        ["tar", "--zstd", "-tf", str(archive)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    _scan_archive_names(listing)
    extracted = output_dir / "extracted"
    extracted.mkdir()
    subprocess.run(["tar", "--zstd", "-xf", str(archive), "-C", str(extracted)], check=True)
    inventory_path = extracted / str(source["inventory_path"])
    restored_inventory_hash = sha256(inventory_path)
    if restored_inventory_hash != source["inventory_sha256"]:
        raise RuntimeError("restored inventory checksum mismatch")
    inventory: list[dict[str, str]] = json.loads(inventory_path.read_text(encoding="utf-8"))
    for entry in inventory:
        restored = extracted / entry["path"]
        if not restored.is_file() or sha256(restored) != entry["sha256"]:
            raise RuntimeError(f"restored member checksum mismatch: {entry['path']}")

    bundle = extracted / "results/frontier-feasibility-v1"
    bundles = list(bundle.rglob("scopebreak-history.bundle"))
    if len(bundles) != 1:
        raise RuntimeError("archive must contain exactly one Git history bundle")
    verification_repo = output_dir / "bundle-verify.git"
    subprocess.run(["git", "init", "--bare", str(verification_repo)], check=True)
    subprocess.run(
        ["git", f"--git-dir={verification_repo}", "bundle", "verify", str(bundles[0])],
        check=True,
    )
    heads = subprocess.run(
        ["git", "bundle", "list-heads", str(bundles[0])],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if str(source["git_commit"]) not in heads:
        raise RuntimeError("Git bundle does not contain the source commit")
    restored_git = output_dir / "restored-git"
    subprocess.run(["git", "clone", str(bundles[0]), str(restored_git)], check=True)
    restored_head = subprocess.run(
        ["git", "-C", str(restored_git), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if restored_head != source["git_commit"]:
        raise RuntimeError("reconstructed Git history does not resolve to the source commit")

    receipt = {
        "backup_run_id": source["backup_run_id"],
        "source_uri": uri,
        "source_machine_id": source["source_machine_id"],
        "restore_machine_id": current_machine,
        "restore_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": source["git_commit"],
        "archive_sha256": source["archive_sha256"],
        "restored_archive_sha256": restored_hash,
        "inventory_sha256": source["inventory_sha256"],
        "restored_inventory_sha256": restored_inventory_hash,
        "checksum_match": checksum_match,
        "archive_opened": True,
        "git_history_verified": True,
        "credential_scan_passed": source["credential_scan_passed"],
        "fresh_host_restore_verified": True,
    }
    receipt_path = output_dir / "backup-restore-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    _write_checksum(receipt_path)
    return receipt


def validate_restore_receipt(receipt_path: Path, expected_commit: str) -> dict[str, Any]:
    checksum_path = receipt_path.with_name(f"{receipt_path.name}.sha256")
    if not receipt_path.is_file() or not checksum_path.is_file():
        raise ValueError("restore receipt and checksum sidecar are required")
    if sha256(receipt_path) != _read_checksum(checksum_path):
        raise ValueError("restore receipt checksum mismatch")
    receipt: dict[str, Any] = json.loads(receipt_path.read_text(encoding="utf-8"))
    missing = [field for field in REQUIRED_RESTORE_FIELDS if field not in receipt]
    if missing:
        raise ValueError(f"restore receipt missing fields: {', '.join(missing)}")
    if receipt["source_machine_id"] == receipt["restore_machine_id"]:
        raise ValueError("source and restore machine identities must differ")
    for field in (
        "checksum_match",
        "archive_opened",
        "git_history_verified",
        "credential_scan_passed",
        "fresh_host_restore_verified",
    ):
        if receipt[field] is not True:
            raise ValueError(f"restore receipt did not pass {field}")
    if receipt["archive_sha256"] != receipt["restored_archive_sha256"]:
        raise ValueError("archive hashes differ")
    if receipt["inventory_sha256"] != receipt["restored_inventory_sha256"]:
        raise ValueError("inventory hashes differ")
    if receipt["git_commit"] != expected_commit:
        raise ValueError("restore receipt is stale for the current frozen commit")
    return receipt


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
