"""Regression tests for the durable graph-sync entrypoint safety contract."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

from src.scripts import sync_episodes_to_graphiti as sync


async def test_worker_entrypoint_is_inert_without_explicit_confirmation(capsys):
    result = await sync.async_main([])

    assert result == 2
    assert "worker not started" in capsys.readouterr().err


async def test_legacy_bulk_modes_are_rejected_before_connecting(capsys):
    assert await sync.async_main(["--bulk"]) == 2
    assert await sync.async_main(["--force-bulk"]) == 2

    assert "bulk mode is disabled" in capsys.readouterr().err


async def test_worker_status_path_uses_a_read_only_database_connection(capsys):
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
        patch.object(sync, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(sync, "GraphSyncRepository", return_value=repository),
    ):
        assert await sync._status() == 0

    postgres_class.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
    postgres.disconnect.assert_awaited_once()
    assert '"total": 0' in capsys.readouterr().out


def test_entrypoint_contains_no_boolean_queue_or_projection_write():
    source = Path(sync.__file__).read_text(encoding="ascii")

    assert "WHERE graphiti_synced = FALSE" not in source
    assert "SET graphiti_synced" not in source
    assert "UPDATE episodes" not in source
    assert sync.RUN_CONFIRMATION == "RUN_DURABLE_GRAPH_SYNC"


def test_worker_summary_json_rejects_arbitrary_object_representations():
    assert sync.json_default(UUID("11111111-1111-1111-1111-111111111111")) == (
        "11111111-1111-1111-1111-111111111111"
    )
    try:
        sync.json_default(object())
    except TypeError as error:
        assert "object" in str(error)
    else:
        raise AssertionError("Arbitrary object repr was serialized")
