"""Tests for the durable graph-sync operator CLI."""

from argparse import Namespace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

from src.graphiti.sync_models import RunRecord, RunState
from src.scripts import graph_sync


def _run_summary(run_id: UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "available",
        "run": {
            "id": run_id,
            "state": "running",
            "sync_profile_fingerprint": "sync:test",
        },
        "progress": {
            "synced_jobs": 8,
            "total_jobs": 10,
            "remaining_jobs": 2,
            "completion_percent": 80.0,
            "eligible_now": 2,
            "expired_leases": 0,
            "rolling_verified_per_minute": 1.0,
            "rolling_window_seconds": 300.0,
            "approximate_eta_seconds": 120,
            "eta_status": "available",
        },
        "attempts": {
            "attempts": 6,
            "completed_attempts": 6,
            "outcomes": {
                "primary_success": 5,
                "fallback_success": 0,
                "retry_wait": 1,
                "quarantined": 0,
                "paused_systemic": 0,
                "cancelled": 0,
                "shutdown": 0,
            },
            "failure_classes": {"malformed_json": 1, "authentication": 0},
        },
        "provider_calls": {
            "reserved": 7,
            "completed": 7,
            "failure_classes": {"malformed_json": 1, "authentication": 0},
        },
    }


def _quality_report(run_id: UUID) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "available",
        "run": {
            "id": run_id,
            "state": "stopped",
            "sync_profile_fingerprint": "sync:test",
        },
        "evidence": {
            "status": "complete",
            "successful_attempts": 2,
            "reported_attempts": 2,
            "missing_attempts": 0,
            "coverage_percent": 100.0,
        },
        "vocabulary": {
            "fingerprints": ["relationships:sha256:" + ("a" * 64)],
            "mixed": False,
        },
        "relationships": {
            "proposed": 5,
            "normalized": 1,
            "accepted": 3,
            "rejected": 2,
            "resolved": 3,
            "new": 2,
            "invalidated": 1,
        },
        "rates_percent": {
            "normalized_of_proposed": 20.0,
            "accepted_of_proposed": 60.0,
            "rejected_of_proposed": 40.0,
            "resolved_of_accepted": 100.0,
            "new_of_resolved": 66.667,
            "invalidated_of_resolved": 33.333,
        },
        "rejection_reasons": {
            "rejected_unknown_type": 1,
            "rejected_missing_endpoint": 1,
            "rejected_ambiguous_endpoint": 0,
            "rejected_self_edge": 0,
            "rejected_empty_fact": 0,
            "rejected_duplicate": 0,
        },
    }


def test_parser_requires_explicit_confirmation_for_quarantine_retry():
    episode_id = "11111111-1111-1111-1111-111111111111"
    args = graph_sync.build_parser().parse_args(["retry-quarantined", episode_id])

    assert args.confirm is False


async def test_execute_rejects_unconfirmed_quarantine_retry():
    episode_id = UUID("11111111-1111-1111-1111-111111111111")
    args = Namespace(
        command="retry-quarantined",
        episode_ids=[episode_id],
        confirm=False,
    )

    try:
        await graph_sync.execute_command(args, AsyncMock())
    except ValueError as error:
        assert "--confirm" in str(error)
    else:
        raise AssertionError("Unconfirmed quarantine retry was accepted")


def test_status_renderer_includes_zero_states_and_run_identity():
    run_id = UUID("22222222-2222-2222-2222-222222222222")
    snapshot = {
        "counts": {"pending": 3},
        "total": 3,
        "eligible": 3,
        "expired_leases": 0,
        "job_attempts": 0,
        "ledger": {
            "attempts": 0,
            "completed_attempts": 0,
            "provider_calls": 0,
            "completed_provider_calls": 0,
        },
        "active_run": {
            "id": run_id,
            "state": "running",
            "sync_profile_fingerprint": "sync:test",
            "heartbeat_at": datetime(2026, 8, 7, tzinfo=UTC),
        },
        "latest_run_summary": _run_summary(run_id),
    }

    rendered = graph_sync.render_status(snapshot)

    assert "pending: 3" in rendered
    assert "quarantined: 0" in rendered
    assert f"Active run: {run_id}" in rendered
    assert "Profile completion: 8/10 (80.000%)" in rendered
    assert "Rolling verified throughput: 1.000 episodes/min" in rendered
    assert "Run failure classes: malformed_json=1" in rendered


def test_run_summary_renderer_exposes_only_bounded_operational_aggregates():
    run_id = UUID("22222222-2222-2222-2222-222222222222")

    rendered = graph_sync.render_run_summary(_run_summary(run_id))

    assert f"Run: {run_id}" in rendered
    assert "Completion: 8/10 (80.000%)" in rendered
    assert "Approximate ETA: 120 seconds" in rendered
    assert "Attempt failure classes: malformed_json=1" in rendered
    assert "Provider calls: 7/7 completed" in rendered


async def test_run_summary_dispatches_window_and_optional_identity():
    run_id = UUID("22222222-2222-2222-2222-222222222222")
    args = graph_sync.build_parser().parse_args(
        ["run-summary", "--run-id", str(run_id), "--window-seconds", "900"]
    )
    repository = AsyncMock()
    repository.run_summary.return_value = _run_summary(run_id)

    result = await graph_sync.execute_command(args, repository)

    assert result["run"]["id"] == run_id
    repository.run_summary.assert_awaited_once_with(run_id, rolling_window_seconds=900)


def test_quality_report_renderer_is_explicitly_separate_from_completeness():
    run_id = UUID("22222222-2222-2222-2222-222222222222")

    rendered = graph_sync.render_quality_report(_quality_report(run_id))

    assert f"Run: {run_id}" in rendered
    assert "Evidence: 2/2 successful attempts (complete)" in rendered
    assert "accepted/proposed=60.000%" in rendered
    assert "rejected_unknown_type=1" in rendered
    assert "synchronization completeness is reported separately" in rendered


async def test_quality_report_dispatches_optional_run_identity():
    run_id = UUID("22222222-2222-2222-2222-222222222222")
    args = graph_sync.build_parser().parse_args(["quality-report", "--run-id", str(run_id)])
    repository = AsyncMock()
    repository.relationship_quality_report.return_value = _quality_report(run_id)

    result = await graph_sync.execute_command(args, repository)

    assert result["run"]["id"] == run_id
    repository.relationship_quality_report.assert_awaited_once_with(run_id)


async def test_run_uses_read_only_connection_for_inspection():
    args = graph_sync.build_parser().parse_args(["--json", "status"])
    postgres = AsyncMock()
    repository = AsyncMock()
    repository.status_snapshot.return_value = {
        "counts": {},
        "total": 0,
        "eligible": 0,
        "expired_leases": 0,
        "job_attempts": 0,
        "ledger": {
            "attempts": 0,
            "completed_attempts": 0,
            "provider_calls": 0,
            "completed_provider_calls": 0,
        },
        "active_run": None,
        "latest_run_summary": {"schema_version": 1, "status": "no_runs", "run": None},
    }

    with (
        patch.object(graph_sync, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_sync, "GraphSyncRepository", return_value=repository),
    ):
        assert await graph_sync.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
    postgres.disconnect.assert_awaited_once()


async def test_run_summary_uses_read_only_connection():
    args = graph_sync.build_parser().parse_args(["--json", "run-summary"])
    postgres = AsyncMock()
    repository = AsyncMock()
    repository.run_summary.return_value = {
        "schema_version": 1,
        "status": "no_runs",
        "run": None,
    }

    with (
        patch.object(graph_sync, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_sync, "GraphSyncRepository", return_value=repository),
    ):
        assert await graph_sync.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
    repository.run_summary.assert_awaited_once_with(None, rolling_window_seconds=300)
    postgres.disconnect.assert_awaited_once()


async def test_quality_report_uses_read_only_connection():
    args = graph_sync.build_parser().parse_args(["--json", "quality-report"])
    postgres = AsyncMock()
    repository = AsyncMock()
    repository.relationship_quality_report.return_value = {
        "schema_version": 1,
        "status": "no_runs",
        "run": None,
    }

    with (
        patch.object(graph_sync, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_sync, "GraphSyncRepository", return_value=repository),
    ):
        assert await graph_sync.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
    repository.relationship_quality_report.assert_awaited_once_with(None)
    postgres.disconnect.assert_awaited_once()


def test_json_default_rejects_arbitrary_object_representation():
    try:
        graph_sync.json_default(object())
    except TypeError as error:
        assert "object" in str(error)
    else:
        raise AssertionError("Arbitrary object repr was serialized")


def test_run_record_is_rendered_without_arbitrary_repr():
    now = datetime(2026, 8, 7, tzinfo=UTC)
    record = RunRecord(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        state=RunState.STOPPED,
        worker_id="worker-a",
        sync_profile_fingerprint="sync:test",
        started_at=now,
        heartbeat_at=now,
    )
    args = graph_sync.build_parser().parse_args(["--json", "run-stop", str(record.id)])

    rendered = graph_sync.render_result(args, record)

    assert '"state": "stopped"' in rendered
    assert '"worker_id": "worker-a"' in rendered
