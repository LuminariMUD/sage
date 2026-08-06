#!/usr/bin/env python3
"""Explicitly authorized durable PostgreSQL-to-Graphiti worker entrypoint."""

# ruff: noqa: E402 - direct script execution requires the repository root on sys.path.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import sys
from contextlib import suppress
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.db import close_postgres_db, get_postgres_db
from src.graphiti import initialize_graphiti
from src.graphiti.sync_graph import GraphitiEpisodeProcessor
from src.graphiti.sync_models import GraphSyncPolicy, sanitize_summary
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_state import GraphSyncRepository
from src.graphiti.sync_worker import GraphSyncWorker
from src.security import install_sensitive_logging

RUN_CONFIRMATION = "RUN_DURABLE_GRAPH_SYNC"


def _environment_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the durable leased Graphiti worker. The command is inert unless "
            "--run and the exact confirmation token are both supplied."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="Start the durable worker")
    mode.add_argument("--status", action="store_true", help="Print durable state without mutation")
    parser.add_argument("--confirm", help=f"Required with --run: {RUN_CONFIRMATION}")
    parser.add_argument("--max-episodes", type=int, help="Stop after this many claimed episodes")
    parser.add_argument(
        "--worker-id",
        default=f"{socket.gethostname()}:{os.getpid()}",
        help="Bounded operator-visible lease owner",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--bulk", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force-bulk", action="store_true", help=argparse.SUPPRESS)
    return parser


def policy_from_environment() -> GraphSyncPolicy:
    return GraphSyncPolicy(
        lease_seconds=_environment_int("GRAPH_SYNC_LEASE_SECONDS", 900),
        max_job_attempts=_environment_int("GRAPH_SYNC_MAX_JOB_ATTEMPTS", 3),
        retry_base_seconds=_environment_int("GRAPH_SYNC_RETRY_BASE_SECONDS", 60),
        retry_max_seconds=_environment_int("GRAPH_SYNC_RETRY_MAX_SECONDS", 3600),
        max_provider_calls=_environment_int("GRAPH_SYNC_MAX_PROVIDER_CALLS", 3),
    )


async def _status() -> int:
    postgres = await get_postgres_db()
    try:
        snapshot = await GraphSyncRepository(postgres).status_snapshot()
        print(json.dumps(snapshot, default=str, sort_keys=True))
        return 0
    finally:
        await close_postgres_db()


async def _run_worker(args: argparse.Namespace) -> int:
    profile = GraphSyncExecutionProfile.from_environment()
    policy = policy_from_environment()
    postgres = await get_postgres_db()
    graphiti = None
    try:
        graphiti = await initialize_graphiti(verbose=args.verbose)
        repository = GraphSyncRepository(postgres)
        processor = GraphitiEpisodeProcessor(graphiti, profile)
        worker = GraphSyncWorker(
            repository=repository,
            graph_processor=processor,
            llm_client=graphiti.graphiti.llm_client,
            profile=profile,
            policy=policy,
            worker_id=args.worker_id,
        )
        loop = asyncio.get_running_loop()
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(signal_name, worker.request_shutdown)
        summary = await worker.run(max_episodes=args.max_episodes)
        print(
            json.dumps(
                {
                    "profile": profile.sanitized_summary(),
                    "summary": summary.as_dict(),
                },
                sort_keys=True,
            )
        )
        return 1 if summary.paused_systemic or summary.quarantined else 0
    finally:
        if graphiti is not None:
            await graphiti.close()
        await close_postgres_db()


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.bulk or args.force_bulk:
        print("error: bulk mode is disabled by the durable lifecycle", file=sys.stderr)
        return 2
    if args.status:
        return await _status()
    if not args.run or args.confirm != RUN_CONFIRMATION:
        print(
            "worker not started: use --run --confirm " + RUN_CONFIRMATION,
            file=sys.stderr,
        )
        return 2
    if args.max_episodes is not None and args.max_episodes <= 0:
        print("error: --max-episodes must be positive", file=sys.stderr)
        return 2
    return await _run_worker(args)


def main(argv: list[str] | None = None) -> int:
    install_sensitive_logging()
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"error: {sanitize_summary(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
