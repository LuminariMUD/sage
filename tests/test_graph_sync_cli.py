"""Tests for the durable graph-sync operator CLI."""

from argparse import Namespace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

from src.graphiti.sync_models import RunRecord, RunState
from src.scripts import graph_sync


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
    }

    rendered = graph_sync.render_status(snapshot)

    assert "pending: 3" in rendered
    assert "quarantined: 0" in rendered
    assert f"Active run: {run_id}" in rendered


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
    }

    with (
        patch.object(graph_sync, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_sync, "GraphSyncRepository", return_value=repository),
    ):
        assert await graph_sync.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
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
