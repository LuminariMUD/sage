#!/usr/bin/env python3
"""Inspect and explicitly activate PostgreSQL embedding-space metadata."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

sys.path.insert(0, "/app")

from src.db.embedding_profiles import (
    ACTIVATE_EMPTY_CONFIRMATION,
    ADOPT_EXISTING_CONFIRMATION,
    EMBEDDING_SPACE_SPECS,
    EPISODE_EMBEDDING_SPACE,
    EmbeddingSpaceError,
    activate_embedding_space,
    preflight_embedding_space,
)
from src.db.postgres import PostgresDB
from src.llm.config import get_embedding_profile


async def collect_preflight(
    postgres: Any,
    scope: str,
    *,
    profile_resolver=get_embedding_profile,
) -> dict[str, Any]:
    """Build a secret-free report for one or every PostgreSQL vector space."""
    scopes = tuple(EMBEDDING_SPACE_SPECS) if scope == "all" else (scope,)
    profile = profile_resolver() if "episodes" in scopes else None
    spaces: list[dict[str, Any]] = []
    for name in scopes:
        spec = EMBEDDING_SPACE_SPECS[name]
        report = await preflight_embedding_space(
            postgres,
            spec,
            configured_profile=profile if spec.application_supported else None,
            require_active=spec.application_supported,
        )
        spaces.append(report)

    blocked = [report for report in spaces if report["status"] == "blocked"]
    return {
        "schema_version": 1,
        "status": "blocked" if blocked else "ready",
        "scope": scope,
        "spaces": spaces,
    }


def render_human(report: dict[str, Any]) -> str:
    """Render a compact inventory without vector values or source content."""
    lines = [f"Embedding preflight: {report['status'].upper()}"]
    for space in report["spaces"]:
        physical = space["physical"]
        metadata = space["metadata"]
        lines.append(
            f"- {space['semantic_index']}: {space['status']} "
            f"({physical['formatted_type'] or 'missing'}, "
            f"rows={physical['total_rows']}, embedded={physical['embedded_rows']}, "
            f"index={physical['index']['method'] or 'missing'}, "
            f"metadata={metadata['state'] or 'missing'})"
        )
        for finding in space["findings"]:
            lines.append(f"  - {finding['severity']}: {finding['code']}")
    return "\n".join(lines)


async def run(
    args: argparse.Namespace,
    *,
    postgres_factory=PostgresDB,
    profile_resolver=get_embedding_profile,
) -> int:
    """Run a read-only inventory or a confirmed metadata-only activation."""
    postgres = None
    try:
        if args.command == "status":
            postgres = postgres_factory(read_only=True)
            await postgres.connect()
            report = await collect_preflight(
                postgres,
                args.scope,
                profile_resolver=profile_resolver,
            )
        else:
            expected_confirmation = (
                ADOPT_EXISTING_CONFIRMATION if args.adopt_existing else ACTIVATE_EMPTY_CONFIRMATION
            )
            if args.confirm != expected_confirmation:
                raise EmbeddingSpaceError("Embedding profile activation confirmation is invalid")
            postgres = postgres_factory(read_only=False)
            await postgres.connect()
            profile = profile_resolver()
            activated = await activate_embedding_space(
                postgres,
                profile,
                EPISODE_EMBEDDING_SPACE,
                adopt_existing=args.adopt_existing,
                confirmation=args.confirm or "",
            )
            report = {
                "schema_version": 1,
                "status": "ready" if activated["ready"] else "blocked",
                "scope": "episodes",
                "spaces": [activated],
            }
    except (EmbeddingSpaceError, OSError, ValueError) as error:
        incomplete = {
            "schema_version": 1,
            "status": "incomplete",
            "error_type": type(error).__name__,
            "message": "Embedding preflight could not complete",
        }
        if args.json:
            print(json.dumps(incomplete, indent=2, sort_keys=True))
        else:
            print(
                f"Embedding preflight: INCOMPLETE ({incomplete['error_type']})",
                file=sys.stderr,
            )
        return 2
    except Exception as error:
        incomplete = {
            "schema_version": 1,
            "status": "incomplete",
            "error_type": type(error).__name__,
            "message": "Embedding preflight could not complete",
        }
        if args.json:
            print(json.dumps(incomplete, indent=2, sort_keys=True))
        else:
            print(
                f"Embedding preflight: INCOMPLETE ({incomplete['error_type']})",
                file=sys.stderr,
            )
        return 2
    finally:
        if postgres is not None:
            try:
                await postgres.disconnect()
            except Exception as cleanup_error:
                print(
                    f"Embedding preflight cleanup warning ({type(cleanup_error).__name__})",
                    file=sys.stderr,
                )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(render_human(report))
    return 0 if report["status"] == "ready" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Embedding profile, dimension, index, and row-count preflight"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Run a strictly read-only preflight")
    status.add_argument(
        "--scope",
        choices=("all", *EMBEDDING_SPACE_SPECS),
        default="all",
        help="Physical vector space to inspect",
    )

    activate = subparsers.add_parser(
        "activate",
        help="Persist and activate the configured application profile (metadata only)",
    )
    activate.add_argument(
        "--adopt-existing",
        action="store_true",
        help="Attest that existing vectors were generated by the configured profile",
    )
    activate.add_argument(
        "--confirm",
        help=(
            f"Use {ACTIVATE_EMPTY_CONFIRMATION} for an empty space or "
            f"{ADOPT_EXISTING_CONFIRMATION} with --adopt-existing"
        ),
    )
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
