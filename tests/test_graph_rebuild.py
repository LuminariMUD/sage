"""Tests for the controlled durable graph rebuild workflow."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch
from uuid import UUID

import pytest

from src.graphiti.rebuild import GraphRebuildError, audit_fingerprint
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.scripts import clear_graph as legacy_clear_graph
from src.scripts import graph_rebuild
from src.scripts import reset_processing as legacy_reset_processing
from src.scripts.verify_provider_upgrade_backup import BackupVerificationError

OPERATION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _profile() -> GraphSyncExecutionProfile:
    return GraphSyncExecutionProfile(
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        candidate_fingerprint="candidate:test",
        embedding_profile_fingerprint="embedding:test",
        provider="ollama",
        model="test-model",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        max_entities=10,
        max_relationships=10,
    )


def _postgres() -> SimpleNamespace:
    connection = AsyncMock()
    connection.fetchval.side_effect = [True, True]

    @asynccontextmanager
    async def acquire():
        yield connection

    return SimpleNamespace(acquire=acquire, lock_connection=connection)


def _audit(*, total: int = 2, synced: int = 2, status: str = "clean") -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-08-07T00:00:00+00:00",
        "status": status,
        "state_source": "graph_sync_jobs",
        "counts": {
            "postgres_total": total,
            "postgres_synced": synced,
            "postgres_non_synced": total - synced,
            "neo4j_total": synced,
            "neo4j_populated_stable_ids": synced,
            "neo4j_distinct_stable_ids": synced,
            "lifecycle": {
                "pending": total - synced,
                "leased": 0,
                "retry_wait": 0,
                "quarantined": 0,
                "synced": synced,
            },
            "drift_findings": 0 if status == "clean" else 1,
        },
        "metadata_coverage": {
            "source_fingerprint": synced,
            "sync_profile_fingerprint": synced,
            "embedding_profile_fingerprint": synced,
            "job_source_fingerprint": total,
            "job_verified_source_fingerprint": synced,
            "job_sync_profile_fingerprint": total,
        },
        "drift": {"missing_neo4j_ids": [] if status == "clean" else ["id"]},
    }


def _operation(state: str = "jobs_requeued") -> dict:
    return {
        "id": OPERATION_ID,
        "state": state,
        "target_sync_profile_fingerprint": "sync:test",
        "target_embedding_profile_fingerprint": "embedding:test",
        "backup_reference": "backups/current",
        "backup_created_at": datetime(2020, 1, 1, tzinfo=UTC),
    }


def _backup(*, episodes: int = 2, age: timedelta = timedelta(minutes=1)) -> dict:
    created_at = datetime.now(UTC) - age
    return {
        "status": "verified",
        "backup_reference": "backups/current",
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "postgres_restore": {"episodes_total": episodes},
    }


def _backup_for_operation(operation: dict, *, episodes: int = 2) -> dict:
    return {
        "status": "verified",
        "backup_reference": operation["backup_reference"],
        "created_at": operation["backup_created_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "postgres_restore": {"episodes_total": episodes},
    }


def test_audit_fingerprint_is_stable_across_generation_times():
    first = _audit()
    second = _audit()
    second["generated_at"] = "2026-08-08T00:00:00+00:00"

    assert audit_fingerprint(first) == audit_fingerprint(second)
    assert audit_fingerprint(first).startswith("graph-audit:sha256:")


async def test_prepare_requeues_before_clear_and_records_post_clear_audit():
    repository = AsyncMock()
    repository.active_operation.return_value = None
    repository.prepare.return_value = _operation()
    repository.mark_graph_cleared.return_value = _operation("ready")
    postgres = _postgres()
    neo4j = AsyncMock()
    clean_before = _audit(total=2, synced=2)
    clean_after = _audit(total=2, synced=0)

    with (
        patch.object(
            graph_rebuild,
            "collect_graph_audit",
            AsyncMock(side_effect=[clean_before, clean_after]),
        ),
        patch.object(
            graph_rebuild,
            "collect_graph_counts",
            AsyncMock(
                side_effect=[
                    {"nodes": 9, "relationships": 12},
                    {"nodes": 9, "relationships": 12},
                    {"nodes": 0, "relationships": 0},
                ]
            ),
        ),
        patch.object(graph_rebuild, "clear_entire_graph", AsyncMock()) as clear_graph,
    ):
        result = await graph_rebuild.prepare_rebuild(
            backup_reference="backups/current",
            postgres=postgres,
            neo4j=neo4j,
            repository=repository,
            profile=_profile(),
            backup_verifier=lambda _: _backup(),
        )

    assert result["status"] == "ready"
    assert postgres.lock_connection.fetchval.await_args_list == [
        call("SELECT pg_try_advisory_lock($1)", graph_rebuild.GRAPH_CLEAR_LOCK_ID),
        call("SELECT pg_advisory_unlock($1)", graph_rebuild.GRAPH_CLEAR_LOCK_ID),
    ]
    repository.prepare.assert_awaited_once()
    clear_graph.assert_awaited_once_with(neo4j)
    repository.mark_graph_cleared.assert_awaited_once_with(
        OPERATION_ID,
        cleared_node_count=9,
        cleared_relationship_count=12,
        post_clear_audit_fingerprint=audit_fingerprint(clean_after),
    )

    locked_postgres = _postgres()
    locked_postgres.lock_connection.fetchval.side_effect = [False]
    with pytest.raises(GraphRebuildError, match="already active"):
        await graph_rebuild.prepare_rebuild(
            backup_reference="backups/current",
            postgres=locked_postgres,
            neo4j=neo4j,
            repository=repository,
            profile=_profile(),
            backup_verifier=lambda _: pytest.fail("backup verifier must not run"),
        )
    locked_postgres.lock_connection.fetchval.assert_awaited_once_with(
        "SELECT pg_try_advisory_lock($1)", graph_rebuild.GRAPH_CLEAR_LOCK_ID
    )


async def test_prepare_rejects_backup_from_a_different_episode_snapshot():
    repository = AsyncMock()
    repository.active_operation.return_value = None

    with patch.object(
        graph_rebuild,
        "collect_graph_audit",
        AsyncMock(return_value=_audit(total=2, synced=2)),
    ):
        with pytest.raises(GraphRebuildError, match="episode count"):
            await graph_rebuild.prepare_rebuild(
                backup_reference="backups/current",
                postgres=_postgres(),
                neo4j=AsyncMock(),
                repository=repository,
                profile=_profile(),
                backup_verifier=lambda _: _backup(episodes=1),
            )

    repository.prepare.assert_not_awaited()


async def test_prepare_rejects_preexisting_audit_drift_before_graph_access():
    repository = AsyncMock()
    repository.active_operation.return_value = None

    with (
        patch.object(
            graph_rebuild,
            "collect_graph_audit",
            AsyncMock(return_value=_audit(status="drift")),
        ),
        patch.object(
            graph_rebuild,
            "collect_graph_counts",
            AsyncMock(),
        ) as collect_counts,
    ):
        with pytest.raises(GraphRebuildError, match="clean graph audit"):
            await graph_rebuild.prepare_rebuild(
                backup_reference="backups/current",
                postgres=_postgres(),
                neo4j=AsyncMock(),
                repository=repository,
                profile=_profile(),
                backup_verifier=lambda _: _backup(),
            )

    collect_counts.assert_not_awaited()
    repository.prepare.assert_not_awaited()


async def test_prepare_resume_repeats_only_the_cross_store_clear_stage():
    repository = AsyncMock()
    operation = _operation()
    repository.active_operation.return_value = operation
    repository.mark_graph_cleared.return_value = _operation("ready")
    post_clear = _audit(total=2, synced=0)

    with (
        patch.object(
            graph_rebuild,
            "collect_graph_audit",
            AsyncMock(return_value=post_clear),
        ) as collect_audit,
        patch.object(
            graph_rebuild,
            "collect_graph_counts",
            AsyncMock(
                side_effect=[
                    {"nodes": 3, "relationships": 4},
                    {"nodes": 0, "relationships": 0},
                ]
            ),
        ),
        patch.object(graph_rebuild, "clear_entire_graph", AsyncMock()),
    ):
        result = await graph_rebuild.prepare_rebuild(
            backup_reference="backups/current",
            postgres=_postgres(),
            neo4j=AsyncMock(),
            repository=repository,
            profile=_profile(),
            backup_verifier=lambda _: _backup_for_operation(operation),
        )

    assert result["resumed"] is True
    assert operation["backup_created_at"].year == 2020
    repository.prepare.assert_not_awaited()
    collect_audit.assert_awaited_once()


async def test_prepare_leaves_resumable_state_when_graph_is_not_empty():
    repository = AsyncMock()
    operation = _operation()
    repository.active_operation.return_value = operation

    with (
        patch.object(
            graph_rebuild,
            "collect_graph_counts",
            AsyncMock(
                side_effect=[
                    {"nodes": 3, "relationships": 4},
                    {"nodes": 1, "relationships": 0},
                ]
            ),
        ),
        patch.object(graph_rebuild, "clear_entire_graph", AsyncMock()),
    ):
        with pytest.raises(GraphRebuildError, match="not empty"):
            await graph_rebuild.prepare_rebuild(
                backup_reference="backups/current",
                postgres=_postgres(),
                neo4j=AsyncMock(),
                repository=repository,
                profile=_profile(),
                backup_verifier=lambda _: _backup_for_operation(operation),
            )

    repository.mark_graph_cleared.assert_not_awaited()


async def test_finalize_requires_clean_complete_exact_profile_audit():
    repository = AsyncMock()
    repository.active_operation.return_value = _operation("awaiting_audit")
    repository.finalize.return_value = _operation("completed")
    report = _audit(total=2, synced=2)

    with patch.object(
        graph_rebuild,
        "collect_graph_audit",
        AsyncMock(return_value=report),
    ):
        result = await graph_rebuild.finalize_rebuild(
            postgres=AsyncMock(),
            neo4j=AsyncMock(),
            repository=repository,
            profile=_profile(),
        )

    assert result["status"] == "completed"
    repository.finalize.assert_awaited_once_with(
        OPERATION_ID,
        final_audit_fingerprint=audit_fingerprint(report),
        audited_episode_count=2,
    )


async def test_finalize_rejects_incomplete_coverage_even_when_audit_has_no_drift():
    repository = AsyncMock()
    repository.active_operation.return_value = _operation("awaiting_audit")
    report = _audit(total=2, synced=1)

    with patch.object(
        graph_rebuild,
        "collect_graph_audit",
        AsyncMock(return_value=report),
    ):
        with pytest.raises(GraphRebuildError, match="incomplete"):
            await graph_rebuild.finalize_rebuild(
                postgres=_postgres(),
                neo4j=AsyncMock(),
                repository=repository,
                profile=_profile(),
            )

    repository.finalize.assert_not_awaited()


async def test_active_rebuild_rejects_changed_profile_before_graph_access():
    repository = AsyncMock()
    operation = _operation()
    operation["target_sync_profile_fingerprint"] = "sync:other"
    repository.active_operation.return_value = operation

    with patch.object(
        graph_rebuild,
        "collect_graph_counts",
        AsyncMock(),
    ) as collect_counts:
        with pytest.raises(GraphRebuildError, match="different sync profile"):
            await graph_rebuild.prepare_rebuild(
                backup_reference="backups/current",
                postgres=_postgres(),
                neo4j=AsyncMock(),
                repository=repository,
                profile=_profile(),
                backup_verifier=lambda _: _backup_for_operation(operation),
            )

    collect_counts.assert_not_awaited()


async def test_confirmation_is_checked_before_configuration_or_connections(capsys):
    args = graph_rebuild.build_parser().parse_args(
        [
            "prepare",
            "--backup-reference",
            "backups/current",
            "--confirm",
            "wrong",
        ]
    )

    with (
        patch.object(graph_rebuild, "PostgresDB") as postgres_class,
        patch.object(
            graph_rebuild.GraphSyncExecutionProfile,
            "from_environment",
        ) as profile_resolver,
    ):
        assert await graph_rebuild.run(args) == 1

    postgres_class.assert_not_called()
    profile_resolver.assert_not_called()
    assert graph_rebuild.PREPARE_CONFIRMATION in capsys.readouterr().err

    args = graph_rebuild.build_parser().parse_args(
        [
            "prepare",
            "--backup-reference",
            "backups/current",
            "--confirm",
            graph_rebuild.PREPARE_CONFIRMATION,
        ]
    )
    with (
        patch.object(
            graph_rebuild,
            "verify_backup",
            side_effect=BackupVerificationError("invalid backup"),
        ),
        patch.object(graph_rebuild, "PostgresDB") as postgres_class,
        patch.object(
            graph_rebuild.GraphSyncExecutionProfile,
            "from_environment",
        ) as profile_resolver,
    ):
        assert await graph_rebuild.run(args) == 1

    postgres_class.assert_not_called()
    profile_resolver.assert_not_called()


async def test_status_uses_read_only_postgres_and_no_profile_resolution(capsys):
    args = graph_rebuild.build_parser().parse_args(["--json", "status"])
    postgres = AsyncMock()
    repository = AsyncMock()
    repository.status_snapshot.return_value = {
        "schema_version": 1,
        "operation": None,
        "active_profile": None,
        "events": [],
    }

    with (
        patch.object(graph_rebuild, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_rebuild, "GraphRebuildRepository", return_value=repository),
        patch.object(
            graph_rebuild.GraphSyncExecutionProfile,
            "from_environment",
        ) as profile_resolver,
    ):
        assert await graph_rebuild.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    profile_resolver.assert_not_called()
    assert '"status": "no_rebuilds"' in capsys.readouterr().out


def test_backup_must_be_recent():
    created_at = datetime.now(UTC) - timedelta(hours=25)
    with pytest.raises(GraphRebuildError, match="older than 24 hours"):
        graph_rebuild._require_recent_backup(created_at, now=datetime.now(UTC))


async def test_collect_graph_counts_requires_one_result_row():
    neo4j = SimpleNamespace(execute_query=AsyncMock(return_value=[]))

    with pytest.raises(GraphRebuildError, match="counts were incomplete"):
        await graph_rebuild.collect_graph_counts(neo4j)


async def test_legacy_graph_clear_and_sync_reset_are_inert(capsys):
    with (
        patch.object(legacy_clear_graph, "get_neo4j_db") as neo4j_factory,
        patch.object(legacy_reset_processing, "get_postgres_db") as postgres_factory,
    ):
        assert await legacy_clear_graph.clear_graph(confirm=True) is False
        assert await legacy_reset_processing.reset_sync_flags() is False
        assert await legacy_reset_processing.reset_processing(["all"], confirm=True) is False

    neo4j_factory.assert_not_called()
    postgres_factory.assert_not_called()
    assert "retired" in capsys.readouterr().err


def test_makefile_routes_rebuild_through_all_durable_gates():
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")

    assert "rebuild: clear-graph-force reset-all pipeline-canon" not in makefile
    assert "graph-rebuild-prepare" in makefile
    assert "PREPARE_DURABLE_GRAPH_REBUILD" in makefile
    assert "RUN_DURABLE_GRAPH_SYNC" in makefile
    assert "FINALIZE_DURABLE_GRAPH_REBUILD" in makefile
    assert "$(CURDIR)/backups:/app/backups:ro" in makefile
