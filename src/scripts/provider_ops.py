#!/usr/bin/env python3
"""Inspect provider configuration and run explicitly confirmed bounded probes."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from time import perf_counter
from typing import Any

sys.path.insert(0, "/app")

from src.llm.base import BaseLLMProvider
from src.llm.embeddings.base import BaseEmbedder
from src.llm.embeddings.factory import create_embedder
from src.llm.embeddings.validation import validate_embedding_batch
from src.llm.provider_config import (
    TEXT_TASKS,
    EmbeddingProfile,
    ProviderSettings,
    TextModelCandidate,
    TextTask,
    TransportRetryPolicy,
    resolve_provider_settings,
)
from src.llm.providers.factory import create_text_provider
from src.llm.retry import classify_provider_failure

PROBE_CONFIRMATION = "RUN_PROVIDER_PROBE"
TEXT_PROBE_INPUT = "Reply with one word: ready."
EMBEDDING_PROBE_INPUT = "provider readiness"
_SAFE_MODEL_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,254}$")
_SAFE_PROVIDER_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/+@()-]{0,127}$")
_SAFE_USAGE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

TextProviderFactory = Callable[[TextModelCandidate], BaseLLMProvider]
EmbedderFactory = Callable[[EmbeddingProfile], BaseEmbedder]


def configuration_report(settings: ProviderSettings) -> dict[str, object]:
    """Build a secret-free report for the complete selected profile."""
    report = settings.sanitized_summary()
    connections = []
    for route in (*settings.text_routes.values(), settings.graphiti_text_route):
        connections.extend(candidate.connection for candidate in route.candidates)
    connections.extend(
        (
            settings.embedding_profile.connection,
            settings.graphiti_embedding_profile.connection,
        )
    )
    credential_status: dict[str, bool] = {}
    for connection in connections:
        configured = connection.api_key is not None
        credential_status[connection.provider] = (
            credential_status.get(connection.provider, False) or configured
        )
    return {
        "schema_version": 1,
        "operation": "configuration_check",
        "status": "valid",
        "credential_status": credential_status,
        "profile": report,
    }


def _one_attempt_candidate(candidate: TextModelCandidate) -> TextModelCandidate:
    connection = replace(
        candidate.connection,
        transport_retry=TransportRetryPolicy(
            maximum_attempts=1,
            retry_on=frozenset(),
            base_delay_seconds=0,
            maximum_delay_seconds=0,
        ),
    )
    return replace(candidate, connection=connection, maximum_model_attempts=1)


def _safe_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, Mapping):
        return {}
    result: dict[str, object] = {}
    actual_model = metadata.get("actual_model")
    if isinstance(actual_model, str) and _SAFE_MODEL_LABEL.fullmatch(actual_model):
        result["actual_model"] = actual_model
    upstream_provider = metadata.get("upstream_provider")
    if isinstance(upstream_provider, str) and _SAFE_PROVIDER_LABEL.fullmatch(upstream_provider):
        result["upstream_provider"] = upstream_provider
    transport_attempts = metadata.get("transport_attempts")
    if isinstance(transport_attempts, int) and not isinstance(transport_attempts, bool):
        if 1 <= transport_attempts <= 10:
            result["transport_attempts"] = transport_attempts
    usage = metadata.get("usage")
    if isinstance(usage, Mapping):
        result["usage"] = {
            str(key): value
            for key, value in usage.items()
            if _SAFE_USAGE_KEY.fullmatch(str(key))
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
    return result


async def execute_text_probe(
    settings: ProviderSettings,
    task: TextTask,
    *,
    provider_factory: TextProviderFactory = create_text_provider,
) -> dict[str, object]:
    """Make one text request and return metadata without response content."""
    configured = settings.text_route(task).primary
    candidate = _one_attempt_candidate(configured)
    provider = provider_factory(candidate)
    started = perf_counter()
    response = await provider.generate(
        TEXT_PROBE_INPUT,
        model=candidate.model,
        temperature=0,
        max_tokens=8,
    )
    if not isinstance(response, str) or not response.strip():
        raise RuntimeError("Provider returned an empty text probe response")
    metadata = _safe_metadata(getattr(provider, "last_response_metadata", None))
    return {
        "schema_version": 1,
        "operation": "text_probe",
        "status": "passed",
        "task": task,
        "provider": configured.connection.provider,
        "requested_model": configured.model,
        "candidate_fingerprint": configured.fingerprint,
        "latency_ms": max(0, round((perf_counter() - started) * 1000)),
        **metadata,
    }


async def execute_embedding_probe(
    settings: ProviderSettings,
    scope: str,
    *,
    embedder_factory: EmbedderFactory | None = None,
) -> dict[str, object]:
    """Make one embedding request and validate its shape without emitting values."""
    profile = (
        settings.embedding_profile
        if scope == "application"
        else settings.graphiti_embedding_profile
    )

    if embedder_factory is None:
        retries = 0 if profile.connection.provider in {"openrouter", "openai"} else None
        embedder = create_embedder(profile, transport_max_retries=retries)
    else:
        embedder = embedder_factory(profile)
    started = perf_counter()
    vector = await embedder.embed_text(EMBEDDING_PROBE_INPUT)
    validate_embedding_batch([vector], expected_count=1, dimensions=profile.dimensions)
    metadata_method = getattr(embedder, "sanitized_metadata", None)
    metadata = _safe_metadata(metadata_method() if callable(metadata_method) else None)
    return {
        "schema_version": 1,
        "operation": "embedding_probe",
        "status": "passed",
        "scope": scope,
        "provider": profile.connection.provider,
        "requested_model": profile.model,
        "profile_fingerprint": profile.fingerprint,
        "dimensions": profile.dimensions,
        "latency_ms": max(0, round((perf_counter() - started) * 1000)),
        **metadata,
    }


def _human_report(report: Mapping[str, object]) -> str:
    operation = report["operation"]
    status = report["status"]
    if status not in {"valid", "passed"}:
        lines = [f"Provider operation: {str(status).upper()}"]
        if "message" in report:
            lines.append(str(report["message"]))
        if "failure_class" in report:
            lines.append(f"Failure class: {report['failure_class']}")
        if "failure_code" in report:
            lines.append(f"Failure code: {report['failure_code']}")
        if "error_type" in report:
            lines.append(f"Error type: {report['error_type']}")
        return "\n".join(lines)
    if operation == "configuration_check":
        profile = report["profile"]
        assert isinstance(profile, Mapping)
        credentials = report["credential_status"]
        assert isinstance(credentials, Mapping)
        return "\n".join(
            (
                "Provider configuration: VALID",
                f"Application text provider: {profile['text_provider']}",
                f"Application embedding provider: {profile['embedding_provider']}",
                f"Graphiti text provider: {profile['graphiti_text_provider']}",
                f"Graphiti embedding provider: {profile['graphiti_embedding_provider']}",
                "Selected credentials: "
                + ", ".join(
                    f"{provider}={'configured' if configured else 'not-required'}"
                    for provider, configured in sorted(credentials.items())
                ),
            )
        )
    label = "Text" if operation == "text_probe" else "Embedding"
    lines = [
        f"{label} provider probe: PASSED",
        f"Provider: {report['provider']}",
        f"Requested model: {report['requested_model']}",
        f"Latency: {report['latency_ms']} ms",
    ]
    if "actual_model" in report:
        lines.append(f"Actual model: {report['actual_model']}")
    if "upstream_provider" in report:
        lines.append(f"Upstream provider: {report['upstream_provider']}")
    lines.append("Response content and vector values were not emitted.")
    return "\n".join(lines)


def _emit(report: Mapping[str, object], *, as_json: bool, error: bool = False) -> None:
    destination = sys.stderr if error else sys.stdout
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True), file=destination)
    else:
        print(_human_report(report), file=destination)


async def run(
    args: argparse.Namespace,
    *,
    settings_resolver: Callable[[], ProviderSettings] = resolve_provider_settings,
    text_probe: Callable[[ProviderSettings, TextTask], Any] = execute_text_probe,
    embedding_probe: Callable[[ProviderSettings, str], Any] = execute_embedding_probe,
) -> int:
    """Guard provider calls, resolve configuration, and emit sanitized results."""
    if args.command != "check" and args.confirm != PROBE_CONFIRMATION:
        report = {
            "schema_version": 1,
            "operation": args.command.replace("-", "_"),
            "status": "refused",
            "message": f"--confirm {PROBE_CONFIRMATION} is required",
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    try:
        settings = settings_resolver()
    except ValueError as error:
        report = {
            "schema_version": 1,
            "operation": "configuration_check",
            "status": "invalid",
            "message": str(error),
        }
        _emit(report, as_json=args.json, error=True)
        return 1
    except Exception as error:
        report = {
            "schema_version": 1,
            "operation": "configuration_check",
            "status": "incomplete",
            "error_type": type(error).__name__,
        }
        _emit(report, as_json=args.json, error=True)
        return 2

    if args.command == "check":
        _emit(configuration_report(settings), as_json=args.json)
        return 0

    try:
        if args.command == "text-probe":
            report = await text_probe(settings, args.task)
        else:
            report = await embedding_probe(settings, args.scope)
    except Exception as error:
        failure = classify_provider_failure(error)
        report = {
            "schema_version": 1,
            "operation": args.command.replace("-", "_"),
            "status": "failed",
            "failure_class": failure.failure_class,
            "failure_code": failure.code,
        }
        _emit(report, as_json=args.json, error=True)
        return 1

    _emit(report, as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect provider configuration or run a bounded readiness probe"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Resolve and print sanitized configuration only")

    text_probe = commands.add_parser("text-probe", help="Make one confirmed text request")
    text_probe.add_argument("--task", choices=TEXT_TASKS, default="chat")
    text_probe.add_argument("--confirm", default="")

    embedding_probe = commands.add_parser(
        "embedding-probe", help="Make one confirmed embedding request"
    )
    embedding_probe.add_argument(
        "--scope", choices=("application", "graphiti"), default="application"
    )
    embedding_probe.add_argument("--confirm", default="")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
