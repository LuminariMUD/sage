#!/usr/bin/env python3
"""Verify a provider-upgrade backup set without mutating either database."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
BACKUP_ROOT = PROJECT_DIRECTORY / "backups"
BACKUP_FORMAT = "sage-provider-upgrade-backup-v1"
REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._/:+-]{1,255}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_MANIFEST_KEYS = {
    "format",
    "backup_reference",
    "created_at",
    "postgres_sha256",
    "neo4j_sha256",
    "system_sha256",
}
REQUIRED_EVIDENCE_FILES = (
    "postgres-restore-list.txt",
    "postgres-restore-verification.txt",
    "neo4j-restore-info.txt",
    "system-restore-info.txt",
    "neo4j-consistency-check.txt",
    "system-consistency-check.txt",
    "postgres-SHA256SUMS",
    "neo4j-SHA256SUMS",
)


class BackupVerificationError(RuntimeError):
    """Raised when a backup set cannot prove the required safety properties."""


def resolve_backup_directory(reference: str) -> tuple[Path, str]:
    """Resolve a reference below the project backup root and return its canonical form."""
    if not REFERENCE_PATTERN.fullmatch(reference):
        raise BackupVerificationError("Backup reference is missing or invalid")

    requested = Path(reference)
    candidate = requested if requested.is_absolute() else PROJECT_DIRECTORY / requested
    backup_root = BACKUP_ROOT.resolve()
    backup_directory = candidate.resolve()
    try:
        relative = backup_directory.relative_to(backup_root)
    except ValueError as error:
        raise BackupVerificationError("Backup reference is outside the backup root") from error
    if not relative.parts:
        raise BackupVerificationError("Backup reference must identify a backup set")
    if not backup_directory.is_dir():
        raise BackupVerificationError("Backup directory does not exist")
    return backup_directory, (Path("backups") / relative).as_posix()


def read_regular_file(path: Path, *, maximum_bytes: int = 1_000_000) -> bytes:
    """Read a bounded, private, non-symlink regular file."""
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise BackupVerificationError(
            f"Required backup artifact is missing: {path.name}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise BackupVerificationError(f"Backup artifact is not a regular file: {path.name}")
    if metadata.st_size <= 0:
        raise BackupVerificationError(f"Backup artifact is empty: {path.name}")
    if metadata.st_size > maximum_bytes:
        raise BackupVerificationError(
            f"Backup evidence artifact is unexpectedly large: {path.name}"
        )
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise BackupVerificationError(f"Backup artifact permissions are too broad: {path.name}")
    return path.read_bytes()


def parse_manifest(path: Path) -> dict[str, str]:
    """Parse the strict key-value completion marker."""
    raw = read_regular_file(path, maximum_bytes=16_384)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise BackupVerificationError("Backup completion marker is not ASCII") from error

    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            raise BackupVerificationError("Backup completion marker is malformed")
        key, value = line.split("=", 1)
        if key in values:
            raise BackupVerificationError("Backup completion marker contains duplicate keys")
        values[key] = value
    if set(values) != REQUIRED_MANIFEST_KEYS:
        raise BackupVerificationError("Backup completion marker fields do not match the format")
    return values


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a potentially large artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_dump(path: Path, expected_hash: str) -> int:
    """Verify a private, non-empty dump and return its byte count."""
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise BackupVerificationError(f"Required database dump is missing: {path.name}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise BackupVerificationError(f"Database dump is not a regular file: {path.name}")
    if metadata.st_size <= 0:
        raise BackupVerificationError(f"Database dump is empty: {path.name}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise BackupVerificationError(f"Database dump permissions are too broad: {path.name}")
    if not HASH_PATTERN.fullmatch(expected_hash) or sha256_file(path) != expected_hash:
        raise BackupVerificationError(f"Database dump checksum does not match: {path.name}")
    return metadata.st_size


def parse_postgres_verification(raw: bytes) -> dict[str, int]:
    """Validate the row-count evidence produced by the scratch restore."""
    try:
        text = raw.decode("ascii")
        values = dict(line.split("=", 1) for line in text.splitlines())
        counts = {key: int(value) for key, value in values.items()}
    except (UnicodeDecodeError, ValueError) as error:
        raise BackupVerificationError("PostgreSQL restore verification is malformed") from error
    if set(counts) != {"episodes_total", "episodes_synced", "public_tables"}:
        raise BackupVerificationError("PostgreSQL restore verification fields are incomplete")
    if counts["episodes_total"] < 0:
        raise BackupVerificationError("PostgreSQL restored episode count is invalid")
    if not 0 <= counts["episodes_synced"] <= counts["episodes_total"]:
        raise BackupVerificationError("PostgreSQL restored sync count is invalid")
    if counts["public_tables"] <= 0:
        raise BackupVerificationError("PostgreSQL scratch restore contains no public tables")
    return counts


def require_text_evidence(raw: bytes, required_fragments: tuple[str, ...], label: str) -> None:
    """Require stable success evidence from a completed Neo4j admin command."""
    text = raw.decode("utf-8", errors="replace")
    if "Command Failed" in text or any(fragment not in text for fragment in required_fragments):
        raise BackupVerificationError(f"{label} evidence is incomplete")


def verify_backup(reference: str) -> dict[str, Any]:
    """Verify hashes, restore evidence, archive metadata, and permissions."""
    backup_directory, canonical_reference = resolve_backup_directory(reference)
    directory_mode = stat.S_IMODE(backup_directory.stat().st_mode)
    if directory_mode & 0o077:
        raise BackupVerificationError("Backup directory permissions are too broad")

    manifest = parse_manifest(backup_directory / "BACKUP_COMPLETE")
    if manifest["format"] != BACKUP_FORMAT:
        raise BackupVerificationError("Backup completion marker has an unsupported format")
    if manifest["backup_reference"] != canonical_reference:
        raise BackupVerificationError("Backup completion marker reference does not match")
    try:
        datetime.strptime(manifest["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise BackupVerificationError("Backup completion time is invalid") from error

    dump_sizes = {
        "postgres": verify_dump(backup_directory / "postgres.dump", manifest["postgres_sha256"]),
        "neo4j": verify_dump(backup_directory / "neo4j.dump", manifest["neo4j_sha256"]),
        "system": verify_dump(backup_directory / "system.dump", manifest["system_sha256"]),
    }

    evidence = {
        name: read_regular_file(backup_directory / name) for name in REQUIRED_EVIDENCE_FILES
    }
    expected_postgres_sums = f"{manifest['postgres_sha256']}  postgres.dump\n".encode()
    expected_neo4j_sums = (
        f"{manifest['neo4j_sha256']}  neo4j.dump\n" f"{manifest['system_sha256']}  system.dump\n"
    ).encode()
    if evidence["postgres-SHA256SUMS"] != expected_postgres_sums:
        raise BackupVerificationError("PostgreSQL checksum manifest does not match")
    if evidence["neo4j-SHA256SUMS"] != expected_neo4j_sums:
        raise BackupVerificationError("Neo4j checksum manifest does not match")

    postgres_counts = parse_postgres_verification(evidence["postgres-restore-verification.txt"])
    require_text_evidence(
        evidence["neo4j-restore-info.txt"],
        ("Database: neo4j", "Format:", "Files:", "Bytes:"),
        "Neo4j archive inspection",
    )
    require_text_evidence(
        evidence["system-restore-info.txt"],
        ("Database: system", "Format:", "Files:", "Bytes:"),
        "Neo4j system archive inspection",
    )
    for database in ("neo4j", "system"):
        require_text_evidence(
            evidence[f"{database}-consistency-check.txt"],
            ("Running consistency check", "Consistency check"),
            f"Neo4j {database} consistency check",
        )

    return {
        "status": "verified",
        "backup_reference": canonical_reference,
        "created_at": manifest["created_at"],
        "dump_bytes": dump_sizes,
        "postgres_restore": postgres_counts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a provider-upgrade backup set")
    parser.add_argument("backup_reference", help="Backup set below the project backups directory")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = verify_backup(args.backup_reference)
    except BackupVerificationError as error:
        if args.json:
            print(json.dumps({"status": "invalid", "message": str(error)}, sort_keys=True))
        else:
            print(f"Backup verification failed: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Backup verified: {result['backup_reference']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
