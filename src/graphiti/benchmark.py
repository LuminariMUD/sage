"""Fixed-corpus Graphiti extraction benchmarking without database or graph writes."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.utils.maintenance.combined_extraction import extract_nodes_and_edges

from src.graphiti.edge_types import EDGE_TYPES
from src.graphiti.entity_types import ENTITY_TYPES
from src.graphiti.provider_config import create_graphiti_llm_client
from src.graphiti.provider_tracking import ProviderCallTracker, ProviderTrackingError
from src.llm.provider_config import TextModelCandidate
from src.llm.retry import classify_provider_failure

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/+@()-]{0,254}$")
_MAX_CORPUS_BYTES = 1_048_576


class BenchmarkConfigurationError(ValueError):
    """The benchmark corpus or call boundary is invalid."""


class BenchmarkCallBudgetExceeded(RuntimeError):
    """A case exhausted its provider-call budget before another request."""


@dataclass(frozen=True)
class ExpectedEntity:
    id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedRelationship:
    source: str
    target: str
    types: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    episode: str
    expected_entities: tuple[ExpectedEntity, ...]
    expected_relationships: tuple[ExpectedRelationship, ...]


@dataclass(frozen=True)
class BenchmarkCorpus:
    schema_version: int
    corpus_id: str
    fingerprint: str
    entity_recall_threshold: float
    relationship_recall_threshold: float
    cases: tuple[BenchmarkCase, ...]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BenchmarkConfigurationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise BenchmarkConfigurationError(f"{label} must be a list")
    return value


def _label(value: object, label: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BenchmarkConfigurationError(f"{label} is missing or invalid")
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        raise BenchmarkConfigurationError(f"{label} contains unsupported characters")
    return value.strip()


def _ratio(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkConfigurationError(f"{label} must be numeric")
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise BenchmarkConfigurationError(f"{label} must be between zero and one")
    return parsed


def _parse_entity(value: object) -> ExpectedEntity:
    payload = _mapping(value, "Expected entity")
    entity_id = _label(payload.get("id"), "Expected entity ID", maximum=64)
    if not _CASE_ID.fullmatch(entity_id):
        raise BenchmarkConfigurationError("Expected entity ID is invalid")
    aliases = tuple(
        _label(alias, "Expected entity alias")
        for alias in _sequence(payload.get("aliases"), "Expected entity aliases")
    )
    if not aliases or len(aliases) > 10 or len(set(aliases)) != len(aliases):
        raise BenchmarkConfigurationError("Expected entity aliases are invalid")
    return ExpectedEntity(id=entity_id, aliases=aliases)


def _parse_relationship(value: object, entity_ids: frozenset[str]) -> ExpectedRelationship:
    payload = _mapping(value, "Expected relationship")
    source = _label(payload.get("source"), "Expected relationship source", maximum=64)
    target = _label(payload.get("target"), "Expected relationship target", maximum=64)
    if source not in entity_ids or target not in entity_ids or source == target:
        raise BenchmarkConfigurationError("Expected relationship endpoints are invalid")
    types = tuple(
        _label(item, "Expected relationship type", maximum=64)
        for item in _sequence(payload.get("types"), "Expected relationship types")
    )
    if not types or len(types) > 10 or len(set(types)) != len(types):
        raise BenchmarkConfigurationError("Expected relationship types are invalid")
    return ExpectedRelationship(source=source, target=target, types=types)


def _parse_case(value: object) -> BenchmarkCase:
    payload = _mapping(value, "Benchmark case")
    case_id = _label(payload.get("id"), "Benchmark case ID", maximum=64)
    if not _CASE_ID.fullmatch(case_id):
        raise BenchmarkConfigurationError("Benchmark case ID is invalid")
    episode = _label(payload.get("episode"), "Benchmark episode", maximum=50_000)
    entities = tuple(
        _parse_entity(item)
        for item in _sequence(payload.get("expected_entities"), "Expected entities")
    )
    if not entities or len(entities) > 100:
        raise BenchmarkConfigurationError("Expected entities are invalid")
    entity_ids = frozenset(entity.id for entity in entities)
    if len(entity_ids) != len(entities):
        raise BenchmarkConfigurationError("Expected entity IDs must be unique")
    relationships = tuple(
        _parse_relationship(item, entity_ids)
        for item in _sequence(
            payload.get("expected_relationships"),
            "Expected relationships",
        )
    )
    if not relationships or len(relationships) > 200:
        raise BenchmarkConfigurationError("Expected relationships are invalid")
    return BenchmarkCase(
        id=case_id,
        episode=episode,
        expected_entities=entities,
        expected_relationships=relationships,
    )


def load_benchmark_corpus(path: Path) -> BenchmarkCorpus:
    """Load a bounded, versioned corpus and bind it to its exact bytes."""
    if path.is_symlink():
        raise BenchmarkConfigurationError("Benchmark corpus cannot be a symlink")
    try:
        metadata = path.stat()
        if not path.is_file() or not 0 < metadata.st_size <= _MAX_CORPUS_BYTES:
            raise BenchmarkConfigurationError("Benchmark corpus file is invalid")
        raw = path.read_bytes()
        payload = json.loads(raw)
    except BenchmarkConfigurationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkConfigurationError("Benchmark corpus is unreadable") from error
    root = _mapping(payload, "Benchmark corpus")
    if root.get("schema_version") != 1:
        raise BenchmarkConfigurationError("Benchmark corpus schema version is unsupported")
    corpus_id = _label(root.get("corpus_id"), "Benchmark corpus ID")
    thresholds = _mapping(root.get("thresholds"), "Benchmark thresholds")
    cases = tuple(_parse_case(item) for item in _sequence(root.get("cases"), "Benchmark cases"))
    if not cases or len(cases) > 100:
        raise BenchmarkConfigurationError("Benchmark cases are invalid")
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise BenchmarkConfigurationError("Benchmark case IDs must be unique")
    return BenchmarkCorpus(
        schema_version=1,
        corpus_id=corpus_id,
        fingerprint="corpus:sha256:" + hashlib.sha256(raw).hexdigest(),
        entity_recall_threshold=_ratio(thresholds.get("entity_recall"), "Entity recall"),
        relationship_recall_threshold=_ratio(
            thresholds.get("relationship_recall"),
            "Relationship recall",
        ),
        cases=cases,
    )


def _normalize(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _name_matches(name: object, aliases: tuple[str, ...]) -> bool:
    normalized_name = _normalize(name)
    return bool(normalized_name) and any(
        normalized_alias in normalized_name or normalized_name in normalized_alias
        for normalized_alias in map(_normalize, aliases)
    )


def score_benchmark_case(
    case: BenchmarkCase,
    nodes: Sequence[object],
    edges: Sequence[object],
) -> dict[str, int | float]:
    """Score only counts and recall; never return extracted names or facts."""
    matched_node_ids: dict[str, set[str]] = {}
    for expected in case.expected_entities:
        matched_node_ids[expected.id] = {
            str(getattr(node, "uuid", ""))
            for node in nodes
            if _name_matches(getattr(node, "name", ""), expected.aliases)
        }
    matched_entities = sum(bool(matches) for matches in matched_node_ids.values())
    matched_relationships = 0
    for expected in case.expected_relationships:
        allowed_types = {_normalize(value) for value in expected.types}
        if any(
            str(getattr(edge, "source_node_uuid", "")) in matched_node_ids[expected.source]
            and str(getattr(edge, "target_node_uuid", "")) in matched_node_ids[expected.target]
            and _normalize(getattr(edge, "name", "")) in allowed_types
            for edge in edges
        ):
            matched_relationships += 1
    expected_entity_count = len(case.expected_entities)
    expected_relationship_count = len(case.expected_relationships)
    return {
        "expected_entities": expected_entity_count,
        "matched_entities": matched_entities,
        "extracted_entities": len(nodes),
        "entity_recall": matched_entities / expected_entity_count,
        "expected_relationships": expected_relationship_count,
        "matched_relationships": matched_relationships,
        "extracted_relationships": len(edges),
        "relationship_recall": matched_relationships / expected_relationship_count,
    }


def _value(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


class BenchmarkProviderCallBudget:
    """Count and cap the exact OpenAI-compatible request boundary in memory."""

    def __init__(self, llm_client: object, candidate: TextModelCandidate, maximum_calls: int):
        if not 1 <= maximum_calls <= 100:
            raise BenchmarkConfigurationError("Provider-call budget must be between 1 and 100")
        self.llm_client = llm_client
        self.candidate = candidate
        self.maximum_calls = maximum_calls
        self.calls = 0
        self.rejected_calls = 0
        self.failed_calls = 0
        self.failures: dict[str, int] = {}
        self.usage: dict[str, int] = {}
        self.actual_models: set[str] = set()
        self.upstream_providers: set[str] = set()
        self._installed = False

    def verify_ready(self) -> None:
        try:
            ProviderCallTracker.verify_client(self.llm_client)
        except ProviderTrackingError as error:
            raise BenchmarkConfigurationError(str(error)) from error

    @asynccontextmanager
    async def installed(self) -> AsyncIterator[BenchmarkProviderCallBudget]:
        self.verify_ready()
        if self._installed:
            raise BenchmarkConfigurationError("Benchmark call accounting is already installed")
        resource = self.llm_client.client.chat.completions
        marker = object()
        prior_instance_value = vars(resource).get("create", marker)
        original_create = resource.create

        async def bounded_create(*args: Any, **kwargs: Any) -> Any:
            requested_model = kwargs.get("model")
            if requested_model != self.candidate.model:
                raise BenchmarkConfigurationError(
                    "Benchmark request model does not match the selected candidate"
                )
            if self.calls >= self.maximum_calls:
                self.rejected_calls += 1
                raise BenchmarkCallBudgetExceeded("Benchmark provider-call budget exhausted")
            self.calls += 1
            try:
                response = await original_create(*args, **kwargs)
            except Exception as error:
                failure = classify_provider_failure(error)
                key = f"{failure.failure_class}:{failure.code}"
                self.failed_calls += 1
                self.failures[key] = self.failures.get(key, 0) + 1
                raise
            self._capture_response(response)
            return response

        resource.create = bounded_create
        self._installed = True
        try:
            yield self
        finally:
            if prior_instance_value is marker:
                del resource.create
            else:
                resource.create = prior_instance_value
            self._installed = False

    def _capture_response(self, response: object) -> None:
        actual_model = _value(response, "model")
        if isinstance(actual_model, str) and _SAFE_LABEL.fullmatch(actual_model):
            self.actual_models.add(actual_model)
        upstream = _value(response, "provider")
        if upstream is None:
            extra = _value(response, "model_extra")
            if isinstance(extra, Mapping):
                upstream = extra.get("provider")
        if isinstance(upstream, str) and _SAFE_LABEL.fullmatch(upstream):
            self.upstream_providers.add(upstream)
        usage = _value(response, "usage")
        for name in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
        ):
            count = _value(usage, name) if usage is not None else None
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                self.usage[name] = self.usage.get(name, 0) + count

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "provider_calls": self.calls,
            "budget_rejections": self.rejected_calls,
            "failed_provider_calls": self.failed_calls,
            "provider_failures": dict(sorted(self.failures.items())),
            "usage": dict(sorted(self.usage.items())),
            "actual_models": sorted(self.actual_models),
            "upstream_providers": sorted(self.upstream_providers),
        }


async def _close_llm_client(llm_client: object) -> None:
    client = getattr(llm_client, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


Extractor = Callable[..., Awaitable[tuple[list[object], list[object], dict[str, list[int]]]]]
ClientFactory = Callable[[TextModelCandidate], object]


async def benchmark_candidate(
    corpus: BenchmarkCorpus,
    candidate: TextModelCandidate,
    *,
    route_fingerprint: str,
    sync_profile_fingerprint: str,
    prompt_version: str,
    schema_version: str,
    max_entities: int,
    max_relationships: int,
    maximum_provider_calls: int,
    concurrency: int,
    client_factory: ClientFactory = create_graphiti_llm_client,
    extractor: Extractor = extract_nodes_and_edges,
) -> dict[str, object]:
    """Benchmark one candidate against every case without persistence."""
    if not 1 <= concurrency <= 2:
        raise BenchmarkConfigurationError("Benchmark concurrency must be one or two")
    semaphore = asyncio.Semaphore(concurrency)

    async def run_case(case: BenchmarkCase) -> dict[str, object]:
        async with semaphore:
            started = perf_counter()
            llm_client: object | None = None
            budget: BenchmarkProviderCallBudget | None = None
            try:
                llm_client = client_factory(candidate)
                budget = BenchmarkProviderCallBudget(
                    llm_client,
                    candidate,
                    maximum_provider_calls,
                )
                episode = EpisodicNode(
                    uuid=f"benchmark-{case.id}",
                    name=f"benchmark-{case.id}",
                    group_id=corpus.corpus_id,
                    source=EpisodeType.text,
                    source_description=f"benchmark-{case.id}",
                    content=case.episode,
                    valid_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
                instructions = (
                    "Return only the most important facts from this episode. "
                    f"Extract at most {max_entities} entities and at most "
                    f"{max_relationships} relationships. "
                    "Do not repeat equivalent entities or relationships."
                )
                async with budget.installed():
                    nodes, edges, _ = await extractor(
                        SimpleNamespace(llm_client=llm_client),
                        episode,
                        [],
                        entity_types=ENTITY_TYPES,
                        edge_types=EDGE_TYPES,
                        edge_type_map={("Entity", "Entity"): list(EDGE_TYPES)},
                        custom_extraction_instructions=instructions,
                    )
                if budget.rejected_calls:
                    raise BenchmarkCallBudgetExceeded("Benchmark provider-call budget was exceeded")
                score = score_benchmark_case(case, nodes, edges)
                return {
                    "case_id": case.id,
                    "status": "completed" if budget.failed_calls == 0 else "degraded",
                    "latency_ms": max(0, round((perf_counter() - started) * 1000)),
                    **score,
                    **budget.sanitized_summary(),
                }
            except Exception as error:
                if isinstance(error, BenchmarkCallBudgetExceeded):
                    failure_class = "resource_exhaustion"
                    failure_code = "provider_call_budget_exhausted"
                else:
                    failure = classify_provider_failure(error)
                    failure_class = failure.failure_class
                    failure_code = failure.code
                return {
                    "case_id": case.id,
                    "status": "failed",
                    "latency_ms": max(0, round((perf_counter() - started) * 1000)),
                    "expected_entities": len(case.expected_entities),
                    "matched_entities": 0,
                    "extracted_entities": 0,
                    "entity_recall": 0.0,
                    "expected_relationships": len(case.expected_relationships),
                    "matched_relationships": 0,
                    "extracted_relationships": 0,
                    "relationship_recall": 0.0,
                    "failure_class": failure_class,
                    "failure_code": failure_code,
                    **(
                        budget.sanitized_summary()
                        if budget is not None
                        else {
                            "provider_calls": 0,
                            "budget_rejections": 0,
                            "failed_provider_calls": 0,
                            "provider_failures": {},
                            "usage": {},
                            "actual_models": [],
                            "upstream_providers": [],
                        }
                    ),
                }
            finally:
                if llm_client is not None:
                    try:
                        await _close_llm_client(llm_client)
                    except Exception:
                        pass

    case_results = list(await asyncio.gather(*(run_case(case) for case in corpus.cases)))
    expected_entities = sum(int(result["expected_entities"]) for result in case_results)
    matched_entities = sum(int(result["matched_entities"]) for result in case_results)
    expected_relationships = sum(int(result["expected_relationships"]) for result in case_results)
    matched_relationships = sum(int(result["matched_relationships"]) for result in case_results)
    entity_recall = matched_entities / expected_entities
    relationship_recall = matched_relationships / expected_relationships
    failed_cases = sum(result["status"] != "completed" for result in case_results)
    passed = (
        failed_cases == 0
        and entity_recall >= corpus.entity_recall_threshold
        and relationship_recall >= corpus.relationship_recall_threshold
    )
    contract = {
        "corpus_fingerprint": corpus.fingerprint,
        "route_fingerprint": route_fingerprint,
        "candidate_fingerprint": candidate.fingerprint,
        "sync_profile_fingerprint": sync_profile_fingerprint,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "maximum_provider_calls_per_case": maximum_provider_calls,
        "concurrency": concurrency,
    }
    benchmark_fingerprint = (
        "graphiti-benchmark:sha256:"
        + hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    )
    usage: dict[str, int] = {}
    for result in case_results:
        for name, count in dict(result["usage"]).items():
            usage[name] = usage.get(name, 0) + int(count)
    return {
        "status": "passed" if passed else "failed",
        "provider": candidate.connection.provider,
        "requested_model": candidate.model,
        "model_revision": candidate.revision,
        "candidate_fingerprint": candidate.fingerprint,
        "benchmark_fingerprint": benchmark_fingerprint,
        "cases": case_results,
        "case_count": len(case_results),
        "failed_cases": failed_cases,
        "entity_recall": entity_recall,
        "entity_recall_threshold": corpus.entity_recall_threshold,
        "relationship_recall": relationship_recall,
        "relationship_recall_threshold": corpus.relationship_recall_threshold,
        "provider_calls": sum(int(result["provider_calls"]) for result in case_results),
        "maximum_provider_calls_per_case": maximum_provider_calls,
        "usage": dict(sorted(usage.items())),
    }
