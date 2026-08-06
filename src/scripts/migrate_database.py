#!/usr/bin/env python3
"""Apply immutable PostgreSQL migrations with checksums and an advisory lock."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from src.db.postgres import PostgresDB

DEFAULT_MIGRATION_DIRECTORY = Path(__file__).resolve().parents[2] / "schemas" / "migrations"
MIGRATION_FILE_PATTERN = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
BACKUP_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._/:+-]{1,255}$")
APPLICATION_REVISION_PATTERN = re.compile(r"^[A-Za-z0-9._+-]{1,128}$")
MIGRATION_LOCK_ID = 731047850173

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    backup_reference TEXT NOT NULL,
    application_revision TEXT NOT NULL,
    execution_ms INTEGER NOT NULL CHECK (execution_ms >= 0),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
)
"""

APPLIED_MIGRATIONS_QUERY = """
SELECT version, name, checksum, backup_reference, application_revision,
       execution_ms, applied_at
FROM schema_migrations
ORDER BY version
"""


class MigrationError(RuntimeError):
    """Raised when migration discovery, history, or application is unsafe."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str
    sql: str

    @property
    def identifier(self) -> str:
        return f"{self.version}_{self.name}"


def discover_migrations(directory: Path) -> list[Migration]:
    """Load validated ASCII SQL migrations in deterministic version order."""
    if not directory.is_dir():
        raise MigrationError("Migration directory does not exist")

    migrations = []
    versions = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationError("Migration filename does not match the required pattern")

        version = match.group("version")
        if version in versions:
            raise MigrationError(f"Duplicate migration version: {version}")
        versions.add(version)

        raw = path.read_bytes()
        try:
            sql = raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise MigrationError(f"Migration {version} is not ASCII") from error
        if not sql.strip():
            raise MigrationError(f"Migration {version} is empty")

        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=sha256(raw).hexdigest(),
                sql=sql,
            )
        )

    if not migrations:
        raise MigrationError("No migration files were found")
    return migrations


def build_migration_plan(
    migrations: Sequence[Migration], applied_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Validate immutable history and return applied and pending identifiers."""
    available = {migration.version: migration for migration in migrations}
    applied_versions = set()
    applied_identifiers = []

    for row in applied_rows:
        version = str(row["version"])
        applied_versions.add(version)
        migration = available.get(version)
        if migration is None:
            raise MigrationError(f"Applied migration {version} is missing from disk")
        if str(row["name"]) != migration.name:
            raise MigrationError(f"Applied migration {version} has a different name")
        if str(row["checksum"]) != migration.checksum:
            raise MigrationError(f"Applied migration {version} checksum does not match")
        applied_identifiers.append(migration.identifier)

    pending = [migration for migration in migrations if migration.version not in applied_versions]
    if applied_versions and pending:
        highest_applied = max(applied_versions)
        if any(migration.version < highest_applied for migration in pending):
            raise MigrationError("An unapplied migration sorts before applied history")

    return {
        "status": "current" if not pending else "pending",
        "applied": applied_identifiers,
        "pending": [migration.identifier for migration in pending],
        "pending_migrations": pending,
    }


async def read_migration_plan(
    postgres: PostgresDB, migrations: Sequence[Migration]
) -> dict[str, Any]:
    """Read migration state without creating or modifying the ledger."""
    has_ledger = await postgres.fetchval(
        "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
    )
    applied_rows = await postgres.fetch(APPLIED_MIGRATIONS_QUERY) if has_ledger else []
    plan = build_migration_plan(migrations, applied_rows)
    plan["ledger_exists"] = bool(has_ledger)
    return plan


async def apply_migrations(
    postgres: PostgresDB,
    migrations: Sequence[Migration],
    *,
    backup_reference: str,
    application_revision: str,
) -> list[str]:
    """Apply pending migrations transactionally under a session advisory lock."""
    if not BACKUP_REFERENCE_PATTERN.fullmatch(backup_reference):
        raise MigrationError("Backup reference is missing or invalid")
    if not APPLICATION_REVISION_PATTERN.fullmatch(application_revision):
        raise MigrationError("Application revision is missing or invalid")

    applied_now = []
    async with postgres.acquire() as connection:
        await connection.execute(LEDGER_DDL)
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        try:
            applied_rows = await connection.fetch(APPLIED_MIGRATIONS_QUERY)
            plan = build_migration_plan(migrations, applied_rows)
            pending_versions = set(plan["pending"])

            for migration in migrations:
                if migration.identifier not in pending_versions:
                    continue

                started = time.monotonic()
                async with connection.transaction():
                    await connection.execute(migration.sql)
                    elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
                    await connection.execute(
                        """
                        INSERT INTO schema_migrations (
                            version,
                            name,
                            checksum,
                            backup_reference,
                            application_revision,
                            execution_ms
                        )
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        migration.version,
                        migration.name,
                        migration.checksum,
                        backup_reference,
                        application_revision,
                        elapsed_ms,
                    )
                applied_now.append(migration.identifier)
        finally:
            await connection.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)

    return applied_now


def public_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Remove internal Migration objects before rendering a plan."""
    return {key: value for key, value in plan.items() if key != "pending_migrations"}


def render_human(plan: Mapping[str, Any]) -> str:
    lines = [
        "Database migrations: " + str(plan["status"]).upper(),
        f"Ledger exists: {'yes' if plan.get('ledger_exists') else 'no'}",
        f"Applied: {len(plan['applied'])}",
        f"Pending: {len(plan['pending'])}",
    ]
    lines.extend(f"- pending: {identifier}" for identifier in plan["pending"])
    lines.extend(f"- applied now: {identifier}" for identifier in plan.get("applied_now", []))
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    postgres = None
    try:
        migrations = discover_migrations(Path(args.directory).resolve())
        if args.apply:
            postgres = PostgresDB()
            await postgres.connect()
            applied_now = await apply_migrations(
                postgres,
                migrations,
                backup_reference=args.backup_reference or "",
                application_revision=args.application_revision or "",
            )
            await postgres.disconnect()
            postgres = PostgresDB(read_only=True)
            await postgres.connect()
            plan = await read_migration_plan(postgres, migrations)
            plan["applied_now"] = applied_now
        else:
            postgres = PostgresDB(read_only=True)
            await postgres.connect()
            plan = await read_migration_plan(postgres, migrations)
    except Exception as error:
        incomplete = {
            "status": "incomplete",
            "error_type": type(error).__name__,
            "message": "Database migration command could not complete",
        }
        if args.json:
            print(json.dumps(incomplete, indent=2, sort_keys=True))
        else:
            print(
                f"Database migrations: INCOMPLETE ({incomplete['error_type']})",
                file=sys.stderr,
            )
        return 2
    finally:
        if postgres is not None:
            try:
                await postgres.disconnect()
            except Exception as cleanup_error:
                print(
                    f"Database migration cleanup warning ({type(cleanup_error).__name__})",
                    file=sys.stderr,
                )

    visible_plan = public_plan(plan)
    if args.json:
        print(json.dumps(visible_plan, indent=2, sort_keys=True))
    else:
        print(render_human(visible_plan))

    if args.check and plan["pending"]:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Checksum-verified PostgreSQL migrations")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--apply", action="store_true", help="Apply pending migrations")
    operation.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when migrations are pending; never mutate the database",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    parser.add_argument(
        "--directory",
        default=str(DEFAULT_MIGRATION_DIRECTORY),
        help="Migration directory",
    )
    parser.add_argument(
        "--backup-reference",
        help="Required pre-migration backup reference for --apply",
    )
    parser.add_argument(
        "--application-revision",
        help="Required immutable application revision for --apply",
    )
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
