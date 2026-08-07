#!/usr/bin/env python3
"""Plan, prepare, and finalize a controlled durable Graphiti rebuild."""

# ruff: noqa: E402 - direct script execution requires the repository root on sys.path.

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.db.neo4j_db import Neo4jDB
from src.db.postgres import PostgresDB
from src.graphiti.rebuild import (
    GraphRebuildError,
    GraphRebuildRepository,
    audit_fingerprint,
)
from src.graphiti.sync_models import GraphSyncStateError, sanitize_summary
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.scripts.graph_audit import collect_graph_audit
from src.scripts.verify_provider_upgrade_backup import (
    BackupVerificationError,
    verify_backup,
)

PREPARE_CONFIRMATION = "PREPARE_DURABLE_GRAPH_REBUILD"
FINALIZE_CONFIRMATION = "FINALIZE_DURABLE_GRAPH_REBUILD"
MAX_BACKUP_AGE = timedelta(hours=24)
GRAPH_CLEAR_LOCK_ID = 731047850175

GRAPH_COUNTS_QUERY = """
    CALL {
        MATCH (n)
        RETURN count(n) AS nodes
    }
    CALL {
        MATCH ()-[r]->()
        RETURN count(r) AS relationships
    }
    RETURN nodes, relationships
"""


def json_default(value: object) -> Any:
    """Serialize stable operator evidence without arbitrary representations."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


async def collect_graph_counts(neo4j: Neo4jDB) -> dict[str, int]:
    """Read whole-database node and relationship counts in one query."""
    rows = await neo4j.execute_query(GRAPH_COUNTS_QUERY)
    if len(rows) != 1:
        raise GraphRebuildError("Neo4j graph counts were incomplete")
    return {
        "nodes": int(rows[0]["nodes"]),
        "relationships": int(rows[0]["relationships"]),
    }


async def clear_entire_graph(neo4j: Neo4jDB) -> None:
    """Delete the graph only after the durable preparation record is committed."""
    await neo4j.execute_query("MATCH (n) DETACH DELETE n")


@asynccontextmanager
async def serialized_graph_clear(postgres: PostgresDB):
    """Hold one session lock across the complete cross-store clear phase."""
    async with postgres.acquire() as connection:
        acquired = await connection.fetchval("SELECT pg_try_advisory_lock($1)", GRAPH_CLEAR_LOCK_ID)
        if not acquired:
            raise GraphRebuildError("Another graph rebuild preparation is already active")
        try:
            yield
        finally:
            released = await connection.fetchval(
                "SELECT pg_advisory_unlock($1)", GRAPH_CLEAR_LOCK_ID
            )
            if not released:
                raise GraphRebuildError("Graph rebuild preparation lock was not released")


def _audit_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report["status"],
        "fingerprint": audit_fingerprint(report),
        "counts": report["counts"],
        "metadata_coverage": report["metadata_coverage"],
    }


def _parse_backup_created_at(evidence: dict[str, Any]) -> datetime:
    return datetime.strptime(evidence["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _require_recent_backup(created_at: datetime, *, now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    age = current - created_at
    if age < -timedelta(minutes=5):
        raise GraphRebuildError("Verified backup creation time is in the future")
    if age > MAX_BACKUP_AGE:
        raise GraphRebuildError("Verified backup is older than 24 hours")


def _require_profile_match(operation: dict[str, Any], profile: GraphSyncExecutionProfile) -> None:
    if operation["target_sync_profile_fingerprint"] != profile.sync_profile_fingerprint:
        raise GraphRebuildError("Active rebuild uses a different sync profile")
    if operation["target_embedding_profile_fingerprint"] != profile.embedding_profile_fingerprint:
        raise GraphRebuildError("Active rebuild uses a different embedding profile")


async def build_plan(
    *,
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    repository: GraphRebuildRepository,
    profile: GraphSyncExecutionProfile,
) -> dict[str, Any]:
    """Build a read-only readiness plan for the configured target profile."""
    operation = await repository.active_operation()
    audit = await collect_graph_audit(postgres, neo4j)
    graph_counts = await collect_graph_counts(neo4j)
    blockers: list[str] = []
    if operation is not None:
        blockers.append("active_rebuild")
    if audit["status"] != "clean":
        blockers.append("graph_audit_drift")
    active_run = await postgres.fetchval(
        "SELECT EXISTS (SELECT 1 FROM graph_sync_runs WHERE state <> 'stopped')"
    )
    leased_jobs = int(
        await postgres.fetchval("SELECT count(*) FROM graph_sync_jobs WHERE state = 'leased'")
    )
    if active_run:
        blockers.append("active_graph_sync_run")
    if leased_jobs:
        blockers.append("leased_graph_jobs")
    return {
        "schema_version": 1,
        "status": "ready" if not blockers else "blocked",
        "target_profile": profile.sanitized_summary(),
        "active_operation": operation,
        "audit": _audit_summary(audit),
        "graph_counts": graph_counts,
        "leased_jobs": leased_jobs,
        "blockers": blockers,
    }


async def prepare_rebuild(
    *,
    backup_reference: str,
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    repository: GraphRebuildRepository,
    profile: GraphSyncExecutionProfile,
    backup_verifier: Callable[[str], dict[str, Any]] = verify_backup,
) -> dict[str, Any]:
    """Requeue jobs, clear Neo4j, and prove the empty transition state."""
    async with serialized_graph_clear(postgres):
        return await _prepare_rebuild_locked(
            backup_reference=backup_reference,
            postgres=postgres,
            neo4j=neo4j,
            repository=repository,
            profile=profile,
            backup_verifier=backup_verifier,
        )


async def _prepare_rebuild_locked(
    *,
    backup_reference: str,
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    repository: GraphRebuildRepository,
    profile: GraphSyncExecutionProfile,
    backup_verifier: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Perform preparation while the cross-store clear lock is held."""
    backup = backup_verifier(backup_reference)
    canonical_reference = str(backup["backup_reference"])
    backup_created_at = _parse_backup_created_at(backup)
    operation = await repository.active_operation()
    resumed = operation is not None

    if operation is not None:
        _require_profile_match(operation, profile)
        if operation["backup_reference"] != canonical_reference:
            raise GraphRebuildError("Active rebuild uses a different verified backup")
        if operation["backup_created_at"] != backup_created_at:
            raise GraphRebuildError("Active rebuild backup timestamp does not match")
        if operation["state"] in {"ready", "awaiting_audit"}:
            graph_counts = await collect_graph_counts(neo4j)
            return {
                "schema_version": 1,
                "status": operation["state"],
                "resumed": True,
                "graph_clear_performed": False,
                "operation": operation,
                "target_profile": profile.sanitized_summary(),
                "graph_counts": graph_counts,
            }
        if operation["state"] != "jobs_requeued":
            raise GraphRebuildError("Active rebuild cannot be prepared in its current state")
    else:
        _require_recent_backup(backup_created_at)
        pre_audit = await collect_graph_audit(postgres, neo4j)
        if pre_audit["status"] != "clean":
            raise GraphRebuildError("A clean graph audit is required before rebuild preparation")
        restored_episode_count = int(backup["postgres_restore"]["episodes_total"])
        current_episode_count = int(pre_audit["counts"]["postgres_total"])
        if restored_episode_count != current_episode_count:
            raise GraphRebuildError(
                "Verified backup episode count does not match the current audit"
            )
        pre_graph_counts = await collect_graph_counts(neo4j)
        operation = await repository.prepare(
            target_sync_profile_fingerprint=profile.sync_profile_fingerprint,
            target_embedding_profile_fingerprint=profile.embedding_profile_fingerprint,
            backup_reference=canonical_reference,
            backup_created_at=backup_created_at,
            pre_audit_fingerprint=audit_fingerprint(pre_audit),
            pre_postgres_episode_count=current_episode_count,
            pre_neo4j_node_count=pre_graph_counts["nodes"],
            pre_neo4j_relationship_count=pre_graph_counts["relationships"],
        )

    before_clear = await collect_graph_counts(neo4j)
    await clear_entire_graph(neo4j)
    after_clear = await collect_graph_counts(neo4j)
    if after_clear != {"nodes": 0, "relationships": 0}:
        raise GraphRebuildError("Neo4j was not empty after the rebuild clear")
    post_clear_audit = await collect_graph_audit(
        postgres,
        neo4j,
        expected_sync_profile=profile.sync_profile_fingerprint,
        expected_embedding_profile=profile.embedding_profile_fingerprint,
    )
    if post_clear_audit["status"] != "clean":
        raise GraphRebuildError("Post-clear graph audit found data drift")
    operation = await repository.mark_graph_cleared(
        operation["id"],
        cleared_node_count=before_clear["nodes"],
        cleared_relationship_count=before_clear["relationships"],
        post_clear_audit_fingerprint=audit_fingerprint(post_clear_audit),
    )
    return {
        "schema_version": 1,
        "status": operation["state"],
        "resumed": resumed,
        "graph_clear_performed": True,
        "operation": operation,
        "target_profile": profile.sanitized_summary(),
        "graph_counts": after_clear,
        "post_clear_audit": _audit_summary(post_clear_audit),
    }


async def finalize_rebuild(
    *,
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    repository: GraphRebuildRepository,
    profile: GraphSyncExecutionProfile,
) -> dict[str, Any]:
    """Complete a rebuild only after exact-profile cross-store reconciliation."""
    operation = await repository.active_operation()
    if operation is None:
        raise GraphRebuildError("No active graph rebuild is available to finalize")
    _require_profile_match(operation, profile)
    if operation["state"] != "awaiting_audit":
        raise GraphRebuildError("Graph rebuild is not awaiting its final audit")
    report = await collect_graph_audit(
        postgres,
        neo4j,
        expected_sync_profile=profile.sync_profile_fingerprint,
        expected_embedding_profile=profile.embedding_profile_fingerprint,
    )
    if report["status"] != "clean":
        raise GraphRebuildError("Final graph audit found data drift")
    counts = report["counts"]
    if counts["postgres_synced"] != counts["postgres_total"]:
        raise GraphRebuildError("Final graph audit is incomplete")
    operation = await repository.finalize(
        operation["id"],
        final_audit_fingerprint=audit_fingerprint(report),
        audited_episode_count=int(counts["postgres_total"]),
    )
    return {
        "schema_version": 1,
        "status": "completed",
        "operation": operation,
        "active_profile": {
            "sync_profile_fingerprint": profile.sync_profile_fingerprint,
            "embedding_profile_fingerprint": profile.embedding_profile_fingerprint,
        },
        "final_audit": _audit_summary(report),
    }


def render_human(result: dict[str, Any]) -> str:
    """Render a compact content-free rebuild summary."""
    lines = [f"Graph rebuild: {str(result['status']).upper()}"]
    operation = result.get("operation") or result.get("active_operation")
    if operation is not None:
        lines.extend(
            [
                f"Operation: {operation['id']}",
                f"State: {operation['state']}",
                f"Sync profile: {operation['target_sync_profile_fingerprint']}",
                "Embedding profile: " f"{operation['target_embedding_profile_fingerprint']}",
                f"Verified backup: {operation['backup_reference']}",
            ]
        )
    target = result.get("target_profile")
    if operation is None and target is not None:
        lines.extend(
            [
                f"Target sync profile: {target['sync_profile_fingerprint']}",
                "Target embedding profile: " f"{target['embedding_profile_fingerprint']}",
            ]
        )
    if "graph_counts" in result:
        lines.append(
            "Neo4j: "
            f"nodes={result['graph_counts']['nodes']}, "
            f"relationships={result['graph_counts']['relationships']}"
        )
    blockers = result.get("blockers")
    if blockers:
        lines.append("Blockers: " + ", ".join(blockers))
    if result["status"] == "ready":
        lines.append("Next: run the explicitly confirmed durable graph sync, then finalize.")
    elif result["status"] == "awaiting_audit":
        lines.append("Next: finalize with the exact confirmation token.")
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    """Use the narrowest database modes and keep failure output sanitized."""
    if args.command == "prepare" and args.confirm != PREPARE_CONFIRMATION:
        print(
            f"Graph rebuild command rejected: --confirm {PREPARE_CONFIRMATION} is required",
            file=sys.stderr,
        )
        return 1
    if args.command == "finalize" and args.confirm != FINALIZE_CONFIRMATION:
        print(
            f"Graph rebuild command rejected: --confirm {FINALIZE_CONFIRMATION} is required",
            file=sys.stderr,
        )
        return 1

    postgres = None
    neo4j = None
    output = None
    error_output = None
    verified_backup = None
    exit_code = 0
    cleanup_errors: list[str] = []
    try:
        if args.command == "prepare":
            verified_backup = verify_backup(args.backup_reference)
        read_only_postgres = args.command in {"status", "plan"}
        postgres = PostgresDB(read_only=read_only_postgres)
        await postgres.connect()
        repository = GraphRebuildRepository(postgres)
        if args.command == "status":
            result = await repository.status_snapshot(args.operation_id)
            result["status"] = (
                result["operation"]["state"] if result["operation"] is not None else "no_rebuilds"
            )
        else:
            profile = GraphSyncExecutionProfile.from_environment()
            neo4j = Neo4jDB(read_only=args.command in {"plan", "finalize"})
            await neo4j.connect()
            if args.command == "plan":
                result = await build_plan(
                    postgres=postgres,
                    neo4j=neo4j,
                    repository=repository,
                    profile=profile,
                )
            elif args.command == "prepare":
                if verified_backup is None:
                    raise GraphRebuildError("Verified backup evidence is unavailable")
                result = await prepare_rebuild(
                    backup_reference=args.backup_reference,
                    postgres=postgres,
                    neo4j=neo4j,
                    repository=repository,
                    profile=profile,
                    backup_verifier=lambda _: verified_backup,
                )
            elif args.command == "finalize":
                result = await finalize_rebuild(
                    postgres=postgres,
                    neo4j=neo4j,
                    repository=repository,
                    profile=profile,
                )
            else:
                raise ValueError("Unsupported graph rebuild command")
        output = (
            json.dumps(result, indent=2, sort_keys=True, default=json_default)
            if args.json
            else render_human(result)
        )
    except (BackupVerificationError, GraphSyncStateError, ValueError) as error:
        error_output = f"Graph rebuild command rejected: {sanitize_summary(error)}"
        exit_code = 1
    except Exception as error:
        error_output = f"Graph rebuild command incomplete ({type(error).__name__})"
        exit_code = 2
    finally:
        for client in (neo4j, postgres):
            if client is not None:
                try:
                    await client.disconnect()
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)

    if cleanup_errors:
        print(
            "Graph rebuild cleanup incomplete (" + ",".join(cleanup_errors) + ")",
            file=sys.stderr,
        )
        return 2
    if error_output is not None:
        print(error_output, file=sys.stderr)
    elif output is not None:
        print(output)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate the backup-gated durable Graphiti rebuild lifecycle"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Inspect the latest rebuild read-only")
    status.add_argument("--operation-id", type=UUID)

    commands.add_parser("plan", help="Evaluate rebuild readiness without mutation")

    prepare = commands.add_parser(
        "prepare", help="Requeue durable jobs and clear Neo4j after all safety gates"
    )
    prepare.add_argument("--backup-reference", required=True)
    prepare.add_argument("--confirm", required=True)

    finalize = commands.add_parser(
        "finalize", help="Activate rebuilt profiles after a clean final audit"
    )
    finalize.add_argument("--confirm", required=True)
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
