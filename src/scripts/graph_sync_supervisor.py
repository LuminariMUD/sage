#!/usr/bin/env python3
"""Heartbeat-driven watchdog and optional finalizer for managed graph sync."""

# ruff: noqa: E402 - direct script execution requires the repository root on sys.path.

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.db.neo4j_db import Neo4jDB
from src.db.postgres import PostgresDB
from src.graphiti.heartbeat import heartbeat_path, touch_heartbeat
from src.graphiti.rebuild import GraphRebuildRepository
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_state import GraphSyncRepository
from src.scripts.graph_rebuild import FINALIZE_CONFIRMATION, finalize_rebuild
from src.security import install_sensitive_logging

logger = logging.getLogger(__name__)


def _poll_seconds() -> int:
    raw_value = os.getenv("GRAPH_SYNC_SUPERVISOR_POLL_SECONDS", "10")
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError("Graph supervisor poll interval must be an integer") from error
    if not 2 <= value <= 300:
        raise ValueError("Graph supervisor poll interval must be between 2 and 300 seconds")
    return value


async def _wait(stop_event: asyncio.Event, seconds: int) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)


async def run_watchdog(stop_event: asyncio.Event) -> int:
    """Recover expired leases and suspend cleanly for operator pauses."""
    postgres = PostgresDB()
    await postgres.connect()
    marker = heartbeat_path(os.environ)
    repository = GraphSyncRepository(postgres)
    try:
        while not stop_event.is_set():
            touch_heartbeat(marker)
            recovered = await repository.recover_expired_leases()
            if recovered:
                logger.warning("Recovered %d expired graph leases", len(recovered))
            snapshot = await repository.status_snapshot()
            active_run = snapshot.get("active_run")
            if isinstance(active_run, dict) and active_run.get("state") == "paused_operator":
                logger.info("Watchdog suspended for operator-paused graph run")
                await _wait(stop_event, _poll_seconds())
                continue
            await _wait(stop_event, _poll_seconds())
        return 0
    finally:
        await postgres.disconnect()


async def run_finalizer(stop_event: asyncio.Event) -> int:
    """Monitor rebuild completion and finalize only with an exact opt-in token."""
    auto_finalize = os.getenv("GRAPH_REBUILD_AUTO_FINALIZE", "") == FINALIZE_CONFIRMATION
    postgres = PostgresDB(read_only=not auto_finalize)
    await postgres.connect()
    marker = heartbeat_path(os.environ)
    rebuilds = GraphRebuildRepository(postgres)
    sync = GraphSyncRepository(postgres)
    try:
        while not stop_event.is_set():
            touch_heartbeat(marker)
            sync_snapshot = await sync.status_snapshot()
            active_run = sync_snapshot.get("active_run")
            if isinstance(active_run, dict) and active_run.get("state") == "paused_operator":
                logger.info("Finalizer suspended for operator-paused graph run")
                await _wait(stop_event, _poll_seconds())
                continue
            operation = await rebuilds.active_operation()
            if operation is None:
                logger.info("No incomplete graph rebuild remains")
                await _wait(stop_event, _poll_seconds())
                continue
            if operation["state"] == "awaiting_audit" and auto_finalize:
                neo4j = Neo4jDB(read_only=True)
                await neo4j.connect()
                try:
                    await finalize_rebuild(
                        postgres=postgres,
                        neo4j=neo4j,
                        repository=rebuilds,
                        profile=GraphSyncExecutionProfile.from_environment(),
                    )
                finally:
                    await neo4j.disconnect()
                logger.info("Graph rebuild finalized after exact-profile audit")
            await _wait(stop_event, _poll_seconds())
        return 0
    finally:
        await postgres.disconnect()


async def async_main(args: argparse.Namespace) -> int:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signal_name, stop_event.set)
    if args.mode == "watchdog":
        return await run_watchdog(stop_event)
    return await run_finalizer(stop_event)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one managed graph-sync support role")
    parser.add_argument("mode", choices=("watchdog", "finalizer"))
    return parser


def main() -> int:
    install_sensitive_logging()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    try:
        return asyncio.run(async_main(build_parser().parse_args()))
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        logger.error("Graph sync supervisor failed (%s)", type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
