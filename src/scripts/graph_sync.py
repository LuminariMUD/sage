#!/usr/bin/env python3
"""Inspect and operate the durable Graphiti synchronization lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

sys.path.insert(0, "/app")

from src.db.postgres import PostgresDB
from src.graphiti.sync_models import GraphSyncStateError, JobState, sanitize_summary
from src.graphiti.sync_state import GraphSyncRepository

READ_ONLY_COMMANDS = {"status", "list", "attempts"}


def json_default(value: object) -> str:
    """Serialize stable lifecycle value types without arbitrary object reprs."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def render_status(snapshot: dict[str, Any]) -> str:
    """Render a compact operator status without source content."""
    counts = {state.value: 0 for state in JobState}
    counts.update(snapshot["counts"])
    lines = [
        "Graph sync status",
        f"Total jobs: {snapshot['total']}",
        f"Eligible now: {snapshot['eligible']}",
        f"Expired leases: {snapshot['expired_leases']}",
        f"Total job attempts: {snapshot['job_attempts']}",
    ]
    lines.extend(f"{state}: {counts[state]}" for state in counts)
    ledger = snapshot["ledger"]
    lines.append(
        "Ledger: "
        f"{ledger['completed_attempts']}/{ledger['attempts']} completed attempts, "
        f"{ledger['provider_calls']} provider calls"
    )
    active_run = snapshot["active_run"]
    if active_run is None:
        lines.append("Active run: none")
    else:
        lines.extend(
            [
                f"Active run: {active_run['id']}",
                f"Run state: {active_run['state']}",
                f"Run profile: {active_run['sync_profile_fingerprint']}",
                f"Run heartbeat: {active_run['heartbeat_at'].isoformat()}",
            ]
        )
    return "\n".join(lines)


def render_rows(rows: list[dict[str, Any]], *, empty_message: str) -> str:
    """Render bounded records one per line for terminal inspection."""
    if not rows:
        return empty_message
    return "\n".join(
        json.dumps(row, sort_keys=True, default=json_default, separators=(",", ":")) for row in rows
    )


async def execute_command(args: argparse.Namespace, repository: GraphSyncRepository) -> Any:
    """Dispatch one parsed command to the repository."""
    if args.command == "status":
        return await repository.status_snapshot()
    if args.command == "list":
        return await repository.list_jobs(states=args.state, limit=args.limit)
    if args.command == "attempts":
        return await repository.attempt_chain(args.episode_id, limit=args.limit)
    if args.command == "recover-expired":
        return await repository.recover_expired_leases(limit=args.limit)
    if args.command == "retry-waiting":
        return {"updated": await repository.retry_waiting(args.episode_ids)}
    if args.command == "retry-quarantined":
        if not args.confirm:
            raise ValueError("Quarantined retry requires --confirm")
        return {"updated": await repository.retry_quarantined(args.episode_ids)}
    if args.command == "run-drain":
        return await repository.drain_run(args.run_id)
    if args.command == "run-resume":
        return await repository.resume_run(args.run_id, readiness_verified=args.readiness_verified)
    if args.command == "run-stop":
        return await repository.stop_run(args.run_id)
    raise ValueError("Unsupported graph sync command")


def render_result(args: argparse.Namespace, result: Any) -> str:
    """Render stable JSON or command-specific human output."""
    if args.json:
        return json.dumps(result, indent=2, sort_keys=True, default=json_default)
    if args.command == "status":
        return render_status(result)
    if args.command == "list":
        return render_rows(result, empty_message="No matching graph sync jobs")
    if args.command == "attempts":
        return render_rows(result, empty_message="No attempts for this episode")
    if args.command == "recover-expired":
        return f"Recovered expired leases: {len(result)}"
    if args.command in {"retry-waiting", "retry-quarantined"}:
        return f"Updated graph sync jobs: {result['updated']}"
    return json.dumps(result, sort_keys=True, default=json_default)


async def run(args: argparse.Namespace) -> int:
    """Connect with the narrowest DB mode, execute, and sanitize failures."""
    postgres = None
    output = None
    error_output = None
    exit_code = 0
    cleanup_error_type = None
    try:
        postgres = PostgresDB(read_only=args.command in READ_ONLY_COMMANDS)
        await postgres.connect()
        result = await execute_command(args, GraphSyncRepository(postgres))
        output = render_result(args, result)
    except (GraphSyncStateError, ValueError) as error:
        error_output = f"Graph sync command rejected: {sanitize_summary(error)}"
        exit_code = 1
    except Exception as error:
        error_output = f"Graph sync command incomplete ({type(error).__name__})"
        exit_code = 2
    finally:
        if postgres is not None:
            try:
                await postgres.disconnect()
            except Exception as error:
                cleanup_error_type = type(error).__name__

    if cleanup_error_type is not None:
        print(
            f"Graph sync command cleanup incomplete ({cleanup_error_type})",
            file=sys.stderr,
        )
        return 2
    if error_output is not None:
        print(error_output, file=sys.stderr)
    elif output is not None:
        print(output)
    return exit_code


def add_limit(parser: argparse.ArgumentParser, *, default: int = 100) -> None:
    parser.add_argument("--limit", type=int, default=default, help="Bounded result limit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate durable Graphiti sync state")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="Show durable lifecycle and run counts")

    list_parser = commands.add_parser("list", help="List sanitized job state")
    list_parser.add_argument(
        "--state",
        action="append",
        choices=[state.value for state in JobState],
        default=[],
        help="Filter by state; repeat for multiple states",
    )
    add_limit(list_parser)

    attempts = commands.add_parser("attempts", help="Inspect one sanitized attempt chain")
    attempts.add_argument("episode_id", type=UUID)
    add_limit(attempts)

    recover = commands.add_parser("recover-expired", help="Requeue or quarantine expired leases")
    add_limit(recover)

    retry_waiting = commands.add_parser(
        "retry-waiting", help="Make selected retry-wait jobs immediately eligible"
    )
    retry_waiting.add_argument("episode_ids", type=UUID, nargs="+")

    retry_quarantined = commands.add_parser(
        "retry-quarantined", help="Open a new budget generation for quarantined jobs"
    )
    retry_quarantined.add_argument("episode_ids", type=UUID, nargs="+")
    retry_quarantined.add_argument(
        "--confirm",
        action="store_true",
        help="Acknowledge explicit quarantined-job retry",
    )

    run_drain = commands.add_parser("run-drain", help="Stop new claims for an active run")
    run_drain.add_argument("run_id", type=UUID)

    run_resume = commands.add_parser(
        "run-resume", help="Resume a paused run after readiness succeeds"
    )
    run_resume.add_argument("run_id", type=UUID)
    run_resume.add_argument(
        "--readiness-verified",
        action="store_true",
        help="Assert that the required provider/database readiness check passed",
    )

    run_stop = commands.add_parser("run-stop", help="Stop a run with no active leases")
    run_stop.add_argument("run_id", type=UUID)
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
