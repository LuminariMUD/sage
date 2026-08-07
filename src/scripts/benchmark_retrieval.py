#!/usr/bin/env python3
"""Validate or explicitly run the versioned episode-retrieval benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from src.db.embedding_profiles import (
    EPISODE_EMBEDDING_SPACE,
    EmbeddingSpaceError,
    preflight_embedding_space,
    require_embedding_space,
)
from src.db.postgres import PostgresDB
from src.llm.config import get_embedding_profile, get_embedding_profile_for_provider
from src.llm.embeddings.factory import create_embedder
from src.llm.provider_config import EmbeddingProfile
from src.retrieval.benchmark import (
    ACTIVE_EPISODE_SEARCH_QUERY,
    SNAPSHOT_ROWS_QUERY,
    RetrievalBenchmarkError,
    RetrievalCorpus,
    benchmark_episode_space,
    load_retrieval_corpus,
    planned_provider_requests,
    reconcile_retrieval_corpus,
)
from src.retrieval.shadow_embeddings import (
    ShadowEmbeddingError,
    ShadowEmbeddingRepository,
    shadow_search_query,
)

BENCHMARK_CONFIRMATION = "RUN_RETRIEVAL_BENCHMARK"
DEFAULT_CORPUS = Path("/app/benchmarks/episode_retrieval_v1.json")


def _emit(report: Mapping[str, object], *, as_json: bool, error: bool = False) -> None:
    destination = sys.stderr if error else sys.stdout
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True), file=destination)
        return

    operation = report.get("operation")
    status = str(report.get("status", "incomplete")).upper()
    if operation == "retrieval_corpus_validation":
        print(f"Retrieval corpus validation: {status}", file=destination)
        print(
            f"Cases: {report['case_count']}; judgments: "
            f"{report['matched_judgments']}/{report['judgment_count']}; entities: "
            f"{report['grounded_entity_count']}/{report['expected_entity_count']}",
            file=destination,
        )
        actual = report["actual_source_snapshot"]
        assert isinstance(actual, Mapping)
        print(
            f"Snapshot: {actual['episode_count']} episodes, "
            f"{actual['document_count']} documents, {actual['fingerprint']}",
            file=destination,
        )
        for finding in report.get("findings", []):
            assert isinstance(finding, Mapping)
            print(f"- {finding['code']}", file=destination)
        return

    if operation == "episode_retrieval_benchmark" and status == "COMPLETED":
        metrics = report["metrics"]
        requests = report["provider_requests"]
        assert isinstance(metrics, Mapping)
        assert isinstance(requests, Mapping)
        print("Episode retrieval benchmark: COMPLETED (manual review required)", file=destination)
        print(
            f"Corpus: {report['corpus_id']} ({report['corpus_fingerprint']})",
            file=destination,
        )
        print(
            "Metrics: "
            f"Recall@5={float(metrics['recall_at_5']):.3f}, "
            f"Recall@10={float(metrics['recall_at_10']):.3f}, "
            f"MRR@10={float(metrics['mrr_at_10']):.3f}, "
            f"nDCG@10={float(metrics['ndcg_at_10']):.3f}",
            file=destination,
        )
        print(
            f"Provider requests: {requests['completed']}/{requests['maximum']}",
            file=destination,
        )
        print(
            "Query text, ranked episode identities, vectors, source text, and credentials "
            "were not emitted.",
            file=destination,
        )
        return

    print(f"Episode retrieval benchmark: {status}", file=destination)
    if report.get("message"):
        print(str(report["message"]), file=destination)
    if report.get("error_type"):
        print(f"Error type: {report['error_type']}", file=destination)


def _refused() -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": "episode_retrieval_benchmark",
        "status": "refused",
        "message": f"--confirm {BENCHMARK_CONFIRMATION} is required",
    }


async def run(
    args: argparse.Namespace,
    *,
    postgres_factory: Callable[..., Any] = PostgresDB,
    corpus_loader: Callable[[Path], RetrievalCorpus] = load_retrieval_corpus,
    profile_resolver: Callable[[], EmbeddingProfile] = get_embedding_profile,
    shadow_profile_resolver: Callable[[str], EmbeddingProfile] = get_embedding_profile_for_provider,
    embedder_factory: Callable[..., Any] = create_embedder,
    benchmark_runner: Callable[..., Any] = benchmark_episode_space,
    shadow_repository_factory: Callable[
        [Any], ShadowEmbeddingRepository
    ] = ShadowEmbeddingRepository,
) -> int:
    """Keep validation read-only and require exact consent before any inference."""
    if args.command == "run" and args.confirm != BENCHMARK_CONFIRMATION:
        _emit(_refused(), as_json=args.json, error=True)
        return 2
    if args.command == "run" and not 1 <= args.max_provider_requests <= 100:
        report = {
            "schema_version": 1,
            "operation": "episode_retrieval_benchmark",
            "status": "invalid",
            "message": "--max-provider-requests must be between 1 and 100",
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    postgres = None
    try:
        corpus = corpus_loader(args.corpus)
        postgres = postgres_factory(read_only=True)
        await postgres.connect()
        rows = await postgres.fetch(SNAPSHOT_ROWS_QUERY)
        reconciliation = reconcile_retrieval_corpus(corpus, rows)
        if args.command == "validate":
            _emit(
                reconciliation,
                as_json=args.json,
                error=reconciliation["status"] != "valid",
            )
            return 0 if reconciliation["status"] == "valid" else 1
        if reconciliation["status"] != "valid":
            _emit(reconciliation, as_json=args.json, error=True)
            return 1

        space_kind = getattr(args, "space", "active")
        if space_kind == "shadow":
            profile = shadow_profile_resolver(getattr(args, "provider", "openrouter"))
            shadow_repository = shadow_repository_factory(postgres)
            await shadow_repository.require_ready(profile)
            search_query = shadow_search_query(profile)
            evaluated_space = {
                "kind": "shadow",
                "profile_fingerprint": profile.fingerprint,
            }
        else:
            profile = profile_resolver()
            preflight = await preflight_embedding_space(
                postgres,
                EPISODE_EMBEDDING_SPACE,
                configured_profile=profile,
                require_active=True,
            )
            require_embedding_space(preflight)
            search_query = ACTIVE_EPISODE_SEARCH_QUERY
            evaluated_space = {
                "kind": "active",
                "physical_space": "episodes.embedding",
            }

        planned_requests = planned_provider_requests(corpus, profile)
        if planned_requests > args.max_provider_requests:
            raise RetrievalBenchmarkError(
                "Embedding batch plan exceeds the provider-request ceiling"
            )
        factory_options = (
            {}
            if profile.connection.provider == "sentence-transformers"
            else {"transport_max_retries": 0}
        )
        embedder = embedder_factory(profile, **factory_options)

        logging.getLogger("openai").setLevel(logging.CRITICAL)
        logging.getLogger("httpx").setLevel(logging.CRITICAL)
        logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
        report = await benchmark_runner(
            postgres,
            corpus,
            profile,
            embedder,
            maximum_provider_requests=args.max_provider_requests,
            search_query=search_query,
            evaluated_space=evaluated_space,
        )
        report["corpus_validation_status"] = "valid"
        _emit(report, as_json=args.json)
        return 0
    except (EmbeddingSpaceError, RetrievalBenchmarkError, ShadowEmbeddingError) as error:
        report = {
            "schema_version": 1,
            "operation": "episode_retrieval_benchmark",
            "status": "invalid",
            "message": str(error),
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    except ValueError as error:
        report = {
            "schema_version": 1,
            "operation": "episode_retrieval_benchmark",
            "status": "invalid",
            "error_type": type(error).__name__,
            "message": "Retrieval benchmark configuration or response is invalid",
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    except Exception as error:
        report = {
            "schema_version": 1,
            "operation": "episode_retrieval_benchmark",
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
                    "Retrieval benchmark cleanup warning " f"({type(cleanup_error).__name__})",
                    file=sys.stderr,
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or run the versioned episode-retrieval benchmark"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "validate",
        help="Reconcile corpus judgments with PostgreSQL without provider configuration",
    )
    execute = subparsers.add_parser(
        "run",
        help="Run query embeddings and active episode search after exact confirmation",
    )
    execute.add_argument("--max-provider-requests", type=int, default=1)
    execute.add_argument("--space", choices=("active", "shadow"), default="active")
    execute.add_argument("--provider", choices=("ollama", "openrouter"), default="openrouter")
    execute.add_argument("--confirm", default="")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
