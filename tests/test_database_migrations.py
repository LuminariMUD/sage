"""Tests for immutable, checksum-verified PostgreSQL migrations."""

from argparse import Namespace
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.scripts import migrate_database


def _write_migration(path: Path, name: str, sql: str = "SELECT 1;\n") -> Path:
    migration = path / name
    migration.write_text(sql, encoding="ascii")
    return migration


def test_discovery_orders_migrations_and_hashes_exact_bytes(tmp_path):
    _write_migration(tmp_path, "0002_second.sql", "SELECT 2;\n")
    first = _write_migration(tmp_path, "0001_first.sql", "SELECT 1;\n")

    migrations = migrate_database.discover_migrations(tmp_path)

    assert [migration.identifier for migration in migrations] == ["0001_first", "0002_second"]
    assert migrations[0].path == first
    assert len(migrations[0].checksum) == 64


@pytest.mark.parametrize(
    "filename",
    ["1_short.sql", "0001-uses-dash.sql", "0001_UPPER.sql", "notes.sql"],
)
def test_discovery_rejects_invalid_filenames(tmp_path, filename):
    _write_migration(tmp_path, filename)

    with pytest.raises(migrate_database.MigrationError, match="filename"):
        migrate_database.discover_migrations(tmp_path)


def test_discovery_rejects_non_ascii_sql(tmp_path):
    migration = tmp_path / "0001_unicode.sql"
    migration.write_text("SELECT 'not-ascii: \u2192';\n", encoding="utf-8")

    with pytest.raises(migrate_database.MigrationError, match="not ASCII"):
        migrate_database.discover_migrations(tmp_path)


def test_plan_detects_changed_and_missing_applied_migrations(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    migrations = migrate_database.discover_migrations(tmp_path)

    with pytest.raises(migrate_database.MigrationError, match="checksum"):
        migrate_database.build_migration_plan(
            migrations,
            [{"version": "0001", "name": "first", "checksum": "0" * 64}],
        )

    with pytest.raises(migrate_database.MigrationError, match="missing from disk"):
        migrate_database.build_migration_plan(
            migrations,
            [{"version": "0002", "name": "missing", "checksum": "0" * 64}],
        )


def test_plan_rejects_out_of_order_backfill(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    _write_migration(tmp_path, "0002_second.sql")
    migrations = migrate_database.discover_migrations(tmp_path)

    with pytest.raises(migrate_database.MigrationError, match="sorts before"):
        migrate_database.build_migration_plan(
            migrations,
            [
                {
                    "version": "0002",
                    "name": "second",
                    "checksum": migrations[1].checksum,
                }
            ],
        )


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class FakeConnection:
    def __init__(self):
        self.execute = AsyncMock()
        self.fetch = AsyncMock(return_value=[])

    def transaction(self):
        return FakeTransaction()


class FakePostgres:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def test_apply_uses_lock_transaction_checksum_and_backup_reference(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    migrations = migrate_database.discover_migrations(tmp_path)
    connection = FakeConnection()

    applied = await migrate_database.apply_migrations(
        FakePostgres(connection),
        migrations,
        backup_reference="backups/provider-upgrade/pg.dump",
        application_revision="abc1234",
    )

    assert applied == ["0001_first"]
    executed_sql = [call.args[0] for call in connection.execute.await_args_list]
    assert migrate_database.LEDGER_DDL in executed_sql
    assert migrations[0].sql in executed_sql
    assert "SELECT pg_advisory_lock($1)" in executed_sql
    assert "SELECT pg_advisory_unlock($1)" in executed_sql
    insert_call = next(
        call for call in connection.execute.await_args_list if "INSERT INTO" in call.args[0]
    )
    assert migrations[0].checksum in insert_call.args
    assert "backups/provider-upgrade/pg.dump" in insert_call.args
    assert "abc1234" in insert_call.args


@pytest.mark.parametrize(
    ("backup_reference", "application_revision"),
    [
        ("", "abc1234"),
        ("path with spaces", "abc1234"),
        ("backups/pg.dump", ""),
        ("backups/pg.dump", "revision with spaces"),
    ],
)
async def test_apply_rejects_missing_or_unsafe_evidence_identifiers(
    tmp_path, backup_reference, application_revision
):
    _write_migration(tmp_path, "0001_first.sql")
    migrations = migrate_database.discover_migrations(tmp_path)

    with pytest.raises(migrate_database.MigrationError):
        await migrate_database.apply_migrations(
            FakePostgres(FakeConnection()),
            migrations,
            backup_reference=backup_reference,
            application_revision=application_revision,
        )


async def test_check_mode_returns_one_for_pending_migrations(tmp_path):
    _write_migration(tmp_path, "0001_first.sql")
    args = Namespace(
        apply=False,
        check=True,
        json=True,
        directory=str(tmp_path),
        backup_reference=None,
        application_revision=None,
    )
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(migrate_database, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(
            migrate_database,
            "read_migration_plan",
            AsyncMock(
                return_value={
                    "status": "pending",
                    "applied": [],
                    "pending": ["0001_first"],
                    "pending_migrations": [],
                    "ledger_exists": False,
                }
            ),
        ),
    ):
        assert await migrate_database.run(args) == 1

    postgres_class.assert_called_once_with(read_only=True)


def test_repository_migration_contains_required_durable_contract():
    migrations = migrate_database.discover_migrations(migrate_database.DEFAULT_MIGRATION_DIRECTORY)
    sql = migrations[0].sql

    for required_fragment in (
        "CREATE TABLE graph_sync_runs",
        "CREATE TABLE graph_sync_jobs",
        "CREATE TABLE graph_sync_attempts",
        "CREATE TABLE graph_sync_attempt_results",
        "CREATE TABLE graph_sync_provider_calls",
        "episodes_refresh_graph_sync_job",
        "graph_sync_jobs_project_compatibility",
        "episodes_guard_graph_sync_projection",
        "graph_sync_reject_ledger_mutation",
        "graph_sync_source_fingerprint",
        "legacy:unversioned",
    ):
        assert required_fragment in sql

    runtime_sql = migrations[1].sql
    for required_fragment in (
        "attempt_budget_count",
        "retry_generation",
        "provider_call_limit",
        "retry_delay_seconds",
        "graph_sync_guard_provider_call_budget",
        "graph_sync_guard_attempt_result",
        "graph_sync_provider_calls_budget",
        "graph_sync_attempt_results_provider_count",
    ):
        assert required_fragment in runtime_sql
