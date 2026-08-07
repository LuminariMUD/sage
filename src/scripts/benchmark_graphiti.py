#!/usr/bin/env python3
"""Run a confirmed, fixed-corpus Graphiti extraction benchmark without persistence."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

sys.path.insert(0, "/app")

from src.graphiti.benchmark import (
    BENCHMARK_EXTRACTION_VERSION,
    BenchmarkCorpus,
    benchmark_candidate,
    load_benchmark_corpus,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.llm.provider_config import ProviderSettings, resolve_provider_settings

BENCHMARK_CONFIRMATION = "RUN_GRAPHITI_BENCHMARK"
DEFAULT_CORPUS = Path("/app/benchmarks/graphiti_extraction_v2.json")


def _emit(report: Mapping[str, object], *, as_json: bool, error: bool = False) -> None:
    destination = sys.stderr if error else sys.stdout
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True), file=destination)
        return
    status = str(report["status"]).upper()
    if status in {"REFUSED", "INVALID", "INCOMPLETE"}:
        print(f"Graphiti benchmark: {status}", file=destination)
        if "message" in report:
            print(report["message"], file=destination)
        if "error_type" in report:
            print(f"Error type: {report['error_type']}", file=destination)
        return
    print(f"Graphiti extraction benchmark: {status}", file=destination)
    print(f"Corpus: {report['corpus_id']} ({report['corpus_fingerprint']})", file=destination)
    print(f"Extraction boundary: {report['benchmark_extraction_version']}", file=destination)
    print(f"Sync profile: {report['sync_profile_fingerprint']}", file=destination)
    results = report["candidates"]
    assert isinstance(results, list)
    for result in results:
        assert isinstance(result, Mapping)
        relationship_quality = result["relationship_quality"]
        assert isinstance(relationship_quality, Mapping)
        accepted_rate = relationship_quality["accepted_of_proposed"]
        accepted_rate_text = (
            "unavailable" if accepted_rate is None else f"{float(accepted_rate):.3f}"
        )
        print(
            "Candidate: "
            f"{result['provider']}:{result['requested_model']} "
            f"status={result['status']} cases={result['case_count']} "
            f"structured={result['schema_success_cases']}/{result['case_count']} "
            f"entity_recall={float(result['entity_recall']):.3f} "
            f"relationship_recall={float(result['relationship_recall']):.3f} "
            f"relationship_acceptance={accepted_rate_text} "
            f"provider_calls={result['provider_calls']}",
            file=destination,
        )
    print(
        "Episode, prompt, response, fact, and credential content were not emitted.",
        file=destination,
    )


BenchmarkRunner = Callable[..., Awaitable[dict[str, object]]]


async def run(
    args: argparse.Namespace,
    *,
    settings_resolver: Callable[[], ProviderSettings] = resolve_provider_settings,
    profile_resolver: Callable[[], GraphSyncExecutionProfile] = (
        GraphSyncExecutionProfile.from_environment
    ),
    corpus_loader: Callable[[Path], BenchmarkCorpus] = load_benchmark_corpus,
    benchmark_runner: BenchmarkRunner = benchmark_candidate,
) -> int:
    """Refuse by default, then run only the in-memory extraction boundary."""
    if args.confirm != BENCHMARK_CONFIRMATION:
        report = {
            "schema_version": 1,
            "operation": "graphiti_extraction_benchmark",
            "status": "refused",
            "message": f"--confirm {BENCHMARK_CONFIRMATION} is required",
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    if not 1 <= args.concurrency <= 2:
        report = {
            "schema_version": 1,
            "operation": "graphiti_extraction_benchmark",
            "status": "invalid",
            "message": "--concurrency must be one or two",
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    try:
        corpus = corpus_loader(args.corpus)
        settings = settings_resolver()
        profile = profile_resolver()
        route = settings.graphiti_text_route
        if args.candidate == "primary":
            candidates = (route.primary,)
        elif args.candidate == "fallback":
            if len(route.candidates) < 2:
                raise ValueError("The selected Graphiti route has no fallback candidate")
            candidates = (route.candidates[1],)
        else:
            candidates = route.candidates
        maximum_provider_calls = (
            route.maximum_provider_calls
            if args.max_provider_calls is None
            else args.max_provider_calls
        )
        if not 1 <= maximum_provider_calls <= route.maximum_provider_calls:
            raise ValueError(
                "--max-provider-calls must be positive and cannot exceed the route limit"
            )
    except ValueError as error:
        report = {
            "schema_version": 1,
            "operation": "graphiti_extraction_benchmark",
            "status": "invalid",
            "message": str(error),
        }
        _emit(report, as_json=args.json, error=True)
        return 2
    except Exception as error:
        report = {
            "schema_version": 1,
            "operation": "graphiti_extraction_benchmark",
            "status": "incomplete",
            "error_type": type(error).__name__,
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    logging.getLogger("graphiti_core").setLevel(logging.CRITICAL)
    logging.getLogger("openai").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    try:
        results = []
        for candidate in candidates:
            results.append(
                await benchmark_runner(
                    corpus,
                    candidate,
                    route_fingerprint=route.fingerprint,
                    sync_profile_fingerprint=profile.sync_profile_fingerprint,
                    prompt_version=profile.prompt_version,
                    schema_version=profile.schema_version,
                    relationship_vocabulary_fingerprint=(
                        profile.relationship_vocabulary_fingerprint
                    ),
                    max_entities=profile.max_entities,
                    max_relationships=profile.max_relationships,
                    maximum_provider_calls=maximum_provider_calls,
                    concurrency=args.concurrency,
                )
            )
    except Exception as error:
        report = {
            "schema_version": 1,
            "operation": "graphiti_extraction_benchmark",
            "status": "incomplete",
            "error_type": type(error).__name__,
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    passed = all(result["status"] == "passed" for result in results)
    report = {
        "schema_version": 1,
        "operation": "graphiti_extraction_benchmark",
        "status": "passed" if passed else "failed",
        "corpus_id": corpus.corpus_id,
        "corpus_fingerprint": corpus.fingerprint,
        "benchmark_extraction_version": BENCHMARK_EXTRACTION_VERSION,
        "sync_profile_fingerprint": profile.sync_profile_fingerprint,
        "route_fingerprint": route.fingerprint,
        "prompt_version": profile.prompt_version,
        "schema_version_id": profile.schema_version,
        "relationship_vocabulary_fingerprint": (profile.relationship_vocabulary_fingerprint),
        "candidate_selection": args.candidate,
        "concurrency": args.concurrency,
        "maximum_provider_calls_per_case": maximum_provider_calls,
        "candidates": results,
    }
    _emit(report, as_json=args.json)
    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark Graphiti extraction against a versioned in-memory corpus"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--candidate",
        choices=("primary", "fallback", "all"),
        default="primary",
    )
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-provider-calls", type=int)
    parser.add_argument("--confirm", default="")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
