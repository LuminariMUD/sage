#!/usr/bin/env python3
"""Inspect or explicitly operate non-destructive shadow embedding spaces."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

sys.path.insert(0, "/app")

from src.db.postgres import PostgresDB
from src.llm.config import get_embedding_profile_for_provider
from src.llm.embeddings.factory import create_embedder
from src.llm.provider_config import EmbeddingProfile
from src.retrieval.shadow_embeddings import (
    BUILD_SHADOW_INDEX_CONFIRMATION,
    RECOVER_SHADOW_RUN_CONFIRMATION,
    REGISTER_SHADOW_CONFIRMATION,
    RUN_SHADOW_CONFIRMATION,
    ShadowEmbeddingError,
    ShadowEmbeddingRepository,
    execute_shadow_backfill,
)


def _emit(report: Mapping[str, object], *, as_json: bool, error: bool = False) -> None:
    destination = sys.stderr if error else sys.stdout
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True), file=destination)
        return

    operation = report.get("operation")
    status = str(report.get("status", "incomplete")).upper()
    if operation == "embedding_shadow_status":
        print(f"Embedding shadow status: {status}", file=destination)
        source = report.get("source_snapshot")
        if isinstance(source, Mapping):
            print(
                f"Source: {source['episode_count']} episodes, "
                f"{source['document_count']} documents, {source['fingerprint']}",
                file=destination,
            )
        spaces = report.get("spaces", [])
        if isinstance(spaces, list):
            print(f"Spaces: {len(spaces)}", file=destination)
            for space in spaces:
                if not isinstance(space, Mapping):
                    continue
                profile = space.get("profile")
                coverage = space.get("coverage")
                if not isinstance(profile, Mapping) or not isinstance(coverage, Mapping):
                    continue
                print(
                    f"- {profile['provider']} {profile['model']} "
                    f"({profile['dimensions']}d): {str(space['state']).upper()}, "
                    f"coverage {coverage['current_rows']}/{coverage['source_rows']}, "
                    f"index {'ready' if space['index']['ready'] else 'not-ready'}",
                    file=destination,
                )
                latest_run = space.get("latest_run")
                if isinstance(latest_run, Mapping):
                    requests = latest_run.get("provider_requests")
                    request_summary = ""
                    if isinstance(requests, Mapping):
                        request_summary = f", requests {requests['reserved']}/{requests['maximum']}"
                    print(
                        f"  latest run {latest_run['run_id']}: "
                        f"{str(latest_run['status']).upper()}{request_summary}",
                        file=destination,
                    )
        for finding in report.get("findings", []):
            if isinstance(finding, Mapping):
                print(f"- {finding['code']}", file=destination)
        if report.get("message"):
            print(str(report["message"]), file=destination)
        if report.get("error_type"):
            print(f"Error type: {report['error_type']}", file=destination)
        return

    if operation == "embedding_shadow_backfill":
        requests = report.get("provider_requests")
        print(f"Embedding shadow backfill: {status}", file=destination)
        print(
            f"Coverage: {report.get('stored_episode_count', 0)}/"
            f"{report.get('target_episode_count', 0)}",
            file=destination,
        )
        if isinstance(requests, Mapping):
            print(
                f"Provider requests: {requests['reserved']}/{requests['maximum']} reserved, "
                f"{requests['succeeded']} succeeded",
                file=destination,
            )
        if report.get("failure_code"):
            print(f"Outcome code: {report['failure_code']}", file=destination)
        if report.get("message"):
            print(str(report["message"]), file=destination)
        if report.get("error_type"):
            print(f"Error type: {report['error_type']}", file=destination)
        return

    print(f"Embedding shadow operation: {status}", file=destination)
    if report.get("message"):
        print(str(report["message"]), file=destination)
    if report.get("error_type"):
        print(f"Error type: {report['error_type']}", file=destination)


def _refusal(operation: str, required: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": operation,
        "status": "refused",
        "message": f"--confirm {required} is required",
    }


def _operation(command: str) -> str:
    return (
        "embedding_shadow_backfill"
        if command in {"backfill", "recover-run"}
        else "embedding_shadow_status"
    )


async def run(
    args: argparse.Namespace,
    *,
    postgres_factory: Callable[..., Any] = PostgresDB,
    profile_resolver: Callable[[str], EmbeddingProfile] = get_embedding_profile_for_provider,
    embedder_factory: Callable[..., Any] = create_embedder,
    repository_factory: Callable[[Any], ShadowEmbeddingRepository] = ShadowEmbeddingRepository,
) -> int:
    confirmation = {
        "register": REGISTER_SHADOW_CONFIRMATION,
        "backfill": RUN_SHADOW_CONFIRMATION,
        "build-index": BUILD_SHADOW_INDEX_CONFIRMATION,
        "recover-run": RECOVER_SHADOW_RUN_CONFIRMATION,
    }.get(args.command)
    if confirmation is not None and args.confirm != confirmation:
        _emit(_refusal(_operation(args.command), confirmation), as_json=args.json, error=True)
        return 2
    if args.command == "backfill" and not 1 <= args.max_provider_requests <= 100:
        _emit(
            {
                "schema_version": 1,
                "operation": "embedding_shadow_backfill",
                "status": "invalid",
                "message": "--max-provider-requests must be between 1 and 100",
            },
            as_json=args.json,
            error=True,
        )
        return 2

    postgres = None
    try:
        postgres = postgres_factory(read_only=args.command == "status")
        await postgres.connect()
        repository = repository_factory(postgres)
        if args.command == "status":
            report = await repository.inventory(profile_fingerprint=args.profile_fingerprint)
            _emit(report, as_json=args.json, error=report["status"] == "unavailable")
            return 2 if report["status"] == "unavailable" else 0
        if args.command == "recover-run":
            report = await repository.recover_run(args.run_id)
            _emit(report, as_json=args.json)
            return 0

        profile = profile_resolver(args.provider)
        if args.command == "register":
            report = await repository.register(profile)
            _emit(report, as_json=args.json)
            return 0
        if args.command == "build-index":
            report = await repository.build_index(profile)
            _emit(report, as_json=args.json)
            return 0

        # Registration/profile identity is proven before an adapter can access
        # source text or construct a provider transport.
        await repository.require_registered(profile)
        factory_options = (
            {}
            if profile.connection.provider == "sentence-transformers"
            else {"transport_max_retries": 0}
        )
        embedder = embedder_factory(profile, **factory_options)
        logging.getLogger("openai").setLevel(logging.CRITICAL)
        logging.getLogger("httpx").setLevel(logging.CRITICAL)
        logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
        report = await execute_shadow_backfill(
            repository,
            profile,
            embedder,
            maximum_provider_requests=args.max_provider_requests,
        )
        _emit(report, as_json=args.json)
        return 0
    except ShadowEmbeddingError as error:
        report = {
            "schema_version": 1,
            "operation": _operation(args.command),
            "status": "invalid",
            "message": str(error),
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    except ValueError as error:
        report = {
            "schema_version": 1,
            "operation": _operation(args.command),
            "status": "invalid",
            "error_type": type(error).__name__,
            "message": "Shadow embedding configuration or response is invalid",
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    except Exception as error:
        report = {
            "schema_version": 1,
            "operation": _operation(args.command),
            "status": "incomplete",
            "error_type": type(error).__name__,
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    finally:
        if postgres is not None:
            try:
                await postgres.disconnect()
            except Exception as cleanup_error:
                print(
                    f"Embedding shadow cleanup warning ({type(cleanup_error).__name__})",
                    file=sys.stderr,
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or operate isolated episode embedding candidates"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Inspect all shadow spaces read-only")
    status.add_argument("--profile-fingerprint")

    register = commands.add_parser("register", help="Register profile metadata only")
    register.add_argument("--provider", choices=("ollama", "openrouter"), required=True)
    register.add_argument("--confirm", default="")

    backfill = commands.add_parser("backfill", help="Run bounded resumable embedding batches")
    backfill.add_argument("--provider", choices=("ollama", "openrouter"), required=True)
    backfill.add_argument("--max-provider-requests", type=int, default=1)
    backfill.add_argument("--confirm", default="")

    build_index = commands.add_parser(
        "build-index", help="Build and attest a profile-specific HNSW index"
    )
    build_index.add_argument("--provider", choices=("ollama", "openrouter"), required=True)
    build_index.add_argument("--confirm", default="")

    recover = commands.add_parser(
        "recover-run",
        help="Finalize an explicitly abandoned running invocation without inference",
    )
    recover.add_argument("run_id", type=UUID)
    recover.add_argument("--confirm", default="")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
