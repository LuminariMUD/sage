"""Regression tests for the durable graph-sync entrypoint safety contract."""

from pathlib import Path

from src.scripts import sync_episodes_to_graphiti as sync


async def test_worker_entrypoint_is_inert_without_explicit_confirmation(capsys):
    result = await sync.async_main([])

    assert result == 2
    assert "worker not started" in capsys.readouterr().err


async def test_legacy_bulk_modes_are_rejected_before_connecting(capsys):
    assert await sync.async_main(["--bulk"]) == 2
    assert await sync.async_main(["--force-bulk"]) == 2

    assert "bulk mode is disabled" in capsys.readouterr().err


def test_entrypoint_contains_no_boolean_queue_or_projection_write():
    source = Path(sync.__file__).read_text(encoding="ascii")

    assert "WHERE graphiti_synced = FALSE" not in source
    assert "SET graphiti_synced" not in source
    assert "UPDATE episodes" not in source
    assert sync.RUN_CONFIRMATION == "RUN_DURABLE_GRAPH_SYNC"
