"""Tests for managed graph-sync watchdog and finalizer lifecycles."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.scripts import graph_sync_supervisor


def _heartbeat_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SAGE_HEARTBEAT_FILE", str(tmp_path / "service.heartbeat"))
    monkeypatch.setenv("GRAPH_SYNC_SUPERVISOR_POLL_SECONDS", "2")


async def test_watchdog_idles_while_operator_paused_and_handles_stop(
    monkeypatch,
    tmp_path: Path,
):
    _heartbeat_environment(monkeypatch, tmp_path)
    stop_event = asyncio.Event()
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    repository = SimpleNamespace(
        recover_expired_leases=AsyncMock(return_value=[]),
        status_snapshot=AsyncMock(
            return_value={"active_run": {"state": "paused_operator"}}
        ),
    )

    async def stop_after_wait(event, seconds):
        assert event is stop_event
        assert seconds == 2
        event.set()

    with (
        patch.object(graph_sync_supervisor, "PostgresDB", return_value=postgres),
        patch.object(
            graph_sync_supervisor,
            "GraphSyncRepository",
            return_value=repository,
        ),
        patch.object(graph_sync_supervisor, "_wait", side_effect=stop_after_wait) as wait,
    ):
        assert await graph_sync_supervisor.run_watchdog(stop_event) == 0

    wait.assert_awaited_once()
    repository.recover_expired_leases.assert_awaited_once()
    postgres.disconnect.assert_awaited_once()
    assert (tmp_path / "service.heartbeat").exists()


async def test_finalizer_stays_managed_when_no_rebuild_exists(
    monkeypatch,
    tmp_path: Path,
):
    _heartbeat_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("GRAPH_REBUILD_AUTO_FINALIZE", raising=False)
    stop_event = asyncio.Event()
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    rebuilds = SimpleNamespace(active_operation=AsyncMock(return_value=None))
    sync = SimpleNamespace(status_snapshot=AsyncMock(return_value={"active_run": None}))

    async def stop_after_wait(event, seconds):
        assert event is stop_event
        assert seconds == 2
        event.set()

    with (
        patch.object(
            graph_sync_supervisor,
            "PostgresDB",
            return_value=postgres,
        ) as postgres_class,
        patch.object(
            graph_sync_supervisor,
            "GraphRebuildRepository",
            return_value=rebuilds,
        ),
        patch.object(
            graph_sync_supervisor,
            "GraphSyncRepository",
            return_value=sync,
        ),
        patch.object(graph_sync_supervisor, "Neo4jDB", MagicMock()) as neo4j_class,
        patch.object(graph_sync_supervisor, "_wait", side_effect=stop_after_wait) as wait,
    ):
        assert await graph_sync_supervisor.run_finalizer(stop_event) == 0

    postgres_class.assert_called_once_with(read_only=True)
    wait.assert_awaited_once()
    rebuilds.active_operation.assert_awaited_once()
    neo4j_class.assert_not_called()
    postgres.disconnect.assert_awaited_once()
