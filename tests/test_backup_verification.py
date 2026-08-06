"""Tests for the provider-upgrade backup verification gate."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.scripts import verify_provider_upgrade_backup as backup_verifier


def _write_private(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def _build_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    project_directory = tmp_path / "project"
    backup_directory = project_directory / "backups" / "fixture"
    backup_directory.mkdir(parents=True)
    backup_directory.chmod(0o700)
    monkeypatch.setattr(backup_verifier, "PROJECT_DIRECTORY", project_directory)
    monkeypatch.setattr(backup_verifier, "BACKUP_ROOT", project_directory / "backups")

    dumps = {
        "postgres": ("postgres.dump", b"postgres fixture"),
        "neo4j": ("neo4j.dump", b"neo4j fixture"),
        "system": ("system.dump", b"system fixture"),
    }
    hashes = {}
    for key, (name, content) in dumps.items():
        _write_private(backup_directory / name, content)
        hashes[key] = hashlib.sha256(content).hexdigest()

    _write_private(backup_directory / "postgres-restore-list.txt", b"TABLE episodes\n")
    _write_private(
        backup_directory / "postgres-restore-verification.txt",
        b"episodes_total=611\nepisodes_synced=305\npublic_tables=12\n",
    )
    _write_private(
        backup_directory / "neo4j-restore-info.txt",
        b"Database: neo4j\nFormat: Neo4j ZSTD Dump.\nFiles: 2\nBytes: 10\n",
    )
    _write_private(
        backup_directory / "system-restore-info.txt",
        b"Database: system\nFormat: Neo4j ZSTD Dump.\nFiles: 2\nBytes: 10\n",
    )
    for database in ("neo4j", "system"):
        _write_private(
            backup_directory / f"{database}-consistency-check.txt",
            b"Running consistency check\nConsistency check\n",
        )
    _write_private(
        backup_directory / "postgres-SHA256SUMS",
        f"{hashes['postgres']}  postgres.dump\n".encode(),
    )
    _write_private(
        backup_directory / "neo4j-SHA256SUMS",
        (f"{hashes['neo4j']}  neo4j.dump\n" f"{hashes['system']}  system.dump\n").encode(),
    )
    _write_private(
        backup_directory / "BACKUP_COMPLETE",
        (
            "format=sage-provider-upgrade-backup-v1\n"
            "backup_reference=backups/fixture\n"
            "created_at=2026-08-07T00:00:00Z\n"
            f"postgres_sha256={hashes['postgres']}\n"
            f"neo4j_sha256={hashes['neo4j']}\n"
            f"system_sha256={hashes['system']}\n"
        ).encode(),
    )
    return backup_directory, "backups/fixture"


def test_verify_backup_accepts_complete_restore_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reference = _build_backup(tmp_path, monkeypatch)

    result = backup_verifier.verify_backup(reference)

    assert result["status"] == "verified"
    assert result["backup_reference"] == reference
    assert result["postgres_restore"] == {
        "episodes_total": 611,
        "episodes_synced": 305,
        "public_tables": 12,
    }


def test_verify_backup_rejects_tampered_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_directory, reference = _build_backup(tmp_path, monkeypatch)
    _write_private(backup_directory / "neo4j.dump", b"tampered")

    with pytest.raises(backup_verifier.BackupVerificationError, match="checksum"):
        backup_verifier.verify_backup(reference)


def test_verify_backup_rejects_reference_outside_backup_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_directory = tmp_path / "project"
    project_directory.mkdir()
    monkeypatch.setattr(backup_verifier, "PROJECT_DIRECTORY", project_directory)
    monkeypatch.setattr(backup_verifier, "BACKUP_ROOT", project_directory / "backups")

    with pytest.raises(backup_verifier.BackupVerificationError, match="outside"):
        backup_verifier.resolve_backup_directory("../escape")


def test_verify_backup_rejects_broad_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_directory, reference = _build_backup(tmp_path, monkeypatch)
    (backup_directory / "postgres.dump").chmod(0o644)

    with pytest.raises(backup_verifier.BackupVerificationError, match="permissions"):
        backup_verifier.verify_backup(reference)


def test_verify_backup_rejects_forged_checksum_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_directory, reference = _build_backup(tmp_path, monkeypatch)
    _write_private(backup_directory / "neo4j-SHA256SUMS", b"forged\n")

    with pytest.raises(backup_verifier.BackupVerificationError, match="manifest"):
        backup_verifier.verify_backup(reference)
