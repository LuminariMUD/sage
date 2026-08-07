"""Versioned episode-retrieval corpus validation and deterministic scoring."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from src.db.embedding_profiles import embedding_profile_record
from src.llm.embeddings.validation import validate_embedding_batch
from src.llm.provider_config import EmbeddingProfile

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_ENTITY_ID = _CASE_ID
_DOCUMENT_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SOURCE_FINGERPRINT = re.compile(r"^sha256:v1:[0-9a-f]{64}$")
_SNAPSHOT_FINGERPRINT = re.compile(r"^source-snapshot:sha256:[0-9a-f]{64}$")
_MAX_CORPUS_BYTES = 1_048_576
_MAX_CASES = 100
_MAX_JUDGMENTS_PER_CASE = 100
_MAX_ENTITIES_PER_CASE = 50

SNAPSHOT_ROWS_QUERY = """
    SELECT
        document.stable_id AS document_stable_id,
        episode.episode_index,
        job.desired_source_fingerprint AS source_fingerprint,
        episode.text
    FROM episodes AS episode
    JOIN lore_documents AS document
      ON document.id = episode.document_id
    LEFT JOIN graph_sync_jobs AS job
      ON job.episode_id = episode.id
    ORDER BY document.stable_id, episode.episode_index
"""

ACTIVE_EPISODE_SEARCH_QUERY = """
    SELECT
        document.stable_id AS document_stable_id,
        episode.episode_index,
        1 - (episode.embedding <=> $1::vector) AS similarity
    FROM episodes AS episode
    JOIN lore_documents AS document
      ON document.id = episode.document_id
    WHERE episode.embedding IS NOT NULL
    ORDER BY episode.embedding <=> $1::vector,
             document.stable_id,
             episode.episode_index
    LIMIT $2
"""


class RetrievalBenchmarkError(ValueError):
    """Raised when corpus, snapshot, ranking, or call-budget input is invalid."""


@dataclass(frozen=True)
class SourceSnapshot:
    episode_count: int
    document_count: int
    fingerprint: str


@dataclass(frozen=True)
class ExpectedEntity:
    id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class EpisodeJudgment:
    document_stable_id: str
    episode_index: int
    source_fingerprint: str
    relevance: int

    @property
    def selector(self) -> tuple[str, int]:
        return (self.document_stable_id, self.episode_index)


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    query: str
    expected_entities: tuple[ExpectedEntity, ...]
    judgments: tuple[EpisodeJudgment, ...]


@dataclass(frozen=True)
class RetrievalCorpus:
    schema_version: int
    corpus_id: str
    description: str
    fingerprint: str
    source_snapshot: SourceSnapshot
    cutoffs: tuple[int, ...]
    cases: tuple[RetrievalCase, ...]

    @property
    def judgment_count(self) -> int:
        return sum(len(case.judgments) for case in self.cases)

    @property
    def expected_entity_count(self) -> int:
        return sum(len(case.expected_entities) for case in self.cases)


@dataclass(frozen=True)
class RankedEpisode:
    document_stable_id: str
    episode_index: int
    similarity: float | None = None

    @property
    def selector(self) -> tuple[str, int]:
        return (self.document_stable_id, self.episode_index)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RetrievalBenchmarkError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RetrievalBenchmarkError(f"{label} must be a list")
    return value


def _text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise RetrievalBenchmarkError(f"{label} must be text")
    parsed = value.strip()
    if not parsed or len(parsed) > maximum or any(ord(character) < 32 for character in parsed):
        raise RetrievalBenchmarkError(f"{label} is missing or invalid")
    return parsed


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RetrievalBenchmarkError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise RetrievalBenchmarkError(f"{label} is outside the supported range")
    return value


def _document_stable_id(value: object) -> str:
    parsed = _text(value, "Document stable ID", maximum=128)
    if not _DOCUMENT_STABLE_ID.fullmatch(parsed):
        raise RetrievalBenchmarkError("Document stable ID is invalid")
    return parsed


def _source_fingerprint(value: object) -> str:
    parsed = _text(value, "Source fingerprint", maximum=80)
    if not _SOURCE_FINGERPRINT.fullmatch(parsed):
        raise RetrievalBenchmarkError("Source fingerprint is invalid")
    return parsed


def _normalize(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _parse_expected_entity(value: object) -> ExpectedEntity:
    payload = _mapping(value, "Expected entity")
    entity_id = _text(payload.get("id"), "Expected entity ID", maximum=64)
    if not _ENTITY_ID.fullmatch(entity_id):
        raise RetrievalBenchmarkError("Expected entity ID is invalid")
    aliases = tuple(
        _text(alias, "Expected entity alias", maximum=255)
        for alias in _sequence(payload.get("aliases"), "Expected entity aliases")
    )
    normalized_aliases = tuple(_normalize(alias) for alias in aliases)
    if (
        not aliases
        or len(aliases) > 10
        or any(not alias for alias in normalized_aliases)
        or len(set(normalized_aliases)) != len(normalized_aliases)
    ):
        raise RetrievalBenchmarkError("Expected entity aliases are invalid")
    return ExpectedEntity(id=entity_id, aliases=aliases)


def _parse_judgment(value: object) -> EpisodeJudgment:
    payload = _mapping(value, "Retrieval judgment")
    return EpisodeJudgment(
        document_stable_id=_document_stable_id(payload.get("document_stable_id")),
        episode_index=_integer(
            payload.get("episode_index"),
            "Episode index",
            minimum=0,
            maximum=1_000_000,
        ),
        source_fingerprint=_source_fingerprint(payload.get("source_fingerprint")),
        relevance=_integer(
            payload.get("relevance"),
            "Relevance grade",
            minimum=1,
            maximum=3,
        ),
    )


def _parse_case(value: object) -> RetrievalCase:
    payload = _mapping(value, "Retrieval case")
    case_id = _text(payload.get("id"), "Retrieval case ID", maximum=64)
    if not _CASE_ID.fullmatch(case_id):
        raise RetrievalBenchmarkError("Retrieval case ID is invalid")
    query = _text(payload.get("query"), "Retrieval query", maximum=2_000)
    entities = tuple(
        _parse_expected_entity(entity)
        for entity in _sequence(payload.get("expected_entities"), "Expected entities")
    )
    if not entities or len(entities) > _MAX_ENTITIES_PER_CASE:
        raise RetrievalBenchmarkError("Expected entity set is invalid")
    entity_ids = [entity.id for entity in entities]
    if len(entity_ids) != len(set(entity_ids)):
        raise RetrievalBenchmarkError("Expected entity IDs must be unique per case")

    judgments = tuple(
        _parse_judgment(judgment)
        for judgment in _sequence(payload.get("judgments"), "Retrieval judgments")
    )
    if not judgments or len(judgments) > _MAX_JUDGMENTS_PER_CASE:
        raise RetrievalBenchmarkError("Retrieval judgment set is invalid")
    selectors = [judgment.selector for judgment in judgments]
    if len(selectors) != len(set(selectors)):
        raise RetrievalBenchmarkError("Retrieval judgments must have unique episode selectors")
    return RetrievalCase(
        id=case_id,
        query=query,
        expected_entities=entities,
        judgments=judgments,
    )


def load_retrieval_corpus(path: Path) -> RetrievalCorpus:
    """Load a bounded versioned corpus and fingerprint its exact bytes."""
    if path.is_symlink():
        raise RetrievalBenchmarkError("Retrieval corpus cannot be a symlink")
    try:
        metadata = path.stat()
        if not path.is_file() or not 0 < metadata.st_size <= _MAX_CORPUS_BYTES:
            raise RetrievalBenchmarkError("Retrieval corpus file is invalid")
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except RetrievalBenchmarkError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RetrievalBenchmarkError("Retrieval corpus is unreadable") from error

    root = _mapping(payload, "Retrieval corpus")
    if root.get("schema_version") != 1:
        raise RetrievalBenchmarkError("Retrieval corpus schema version is unsupported")
    corpus_id = _text(root.get("corpus_id"), "Retrieval corpus ID", maximum=255)
    description = _text(root.get("description"), "Retrieval corpus description", maximum=2_000)

    source = _mapping(root.get("source_snapshot"), "Source snapshot")
    snapshot_fingerprint = _text(
        source.get("fingerprint"),
        "Source snapshot fingerprint",
        maximum=96,
    )
    if not _SNAPSHOT_FINGERPRINT.fullmatch(snapshot_fingerprint):
        raise RetrievalBenchmarkError("Source snapshot fingerprint is invalid")
    source_snapshot = SourceSnapshot(
        episode_count=_integer(
            source.get("episode_count"),
            "Source snapshot episode count",
            minimum=1,
            maximum=10_000_000,
        ),
        document_count=_integer(
            source.get("document_count"),
            "Source snapshot document count",
            minimum=1,
            maximum=1_000_000,
        ),
        fingerprint=snapshot_fingerprint,
    )

    metrics = _mapping(root.get("metrics"), "Retrieval metrics")
    cutoffs = tuple(
        _integer(cutoff, "Retrieval cutoff", minimum=1, maximum=100)
        for cutoff in _sequence(metrics.get("cutoffs"), "Retrieval cutoffs")
    )
    if cutoffs != (5, 10):
        raise RetrievalBenchmarkError("Retrieval corpus must declare cutoffs 5 and 10")

    cases = tuple(_parse_case(case) for case in _sequence(root.get("cases"), "Retrieval cases"))
    if not cases or len(cases) > _MAX_CASES:
        raise RetrievalBenchmarkError("Retrieval case set is invalid")
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise RetrievalBenchmarkError("Retrieval case IDs must be unique")
    return RetrievalCorpus(
        schema_version=1,
        corpus_id=corpus_id,
        description=description,
        fingerprint="corpus:sha256:" + hashlib.sha256(raw).hexdigest(),
        source_snapshot=source_snapshot,
        cutoffs=cutoffs,
        cases=cases,
    )


def _row_value(row: object, field: str) -> object:
    if isinstance(row, Mapping):
        return row.get(field)
    try:
        return row[field]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return getattr(row, field, None)


def summarize_source_snapshot(
    rows: Sequence[object],
) -> tuple[SourceSnapshot, dict[tuple[str, int], object]]:
    """Build the canonical content-free snapshot identity used by the corpus."""
    parsed: list[tuple[str, int, str, object]] = []
    selectors: set[tuple[str, int]] = set()
    for row in rows:
        stable_id = _document_stable_id(_row_value(row, "document_stable_id"))
        episode_index = _integer(
            _row_value(row, "episode_index"),
            "Episode index",
            minimum=0,
            maximum=1_000_000,
        )
        source_fingerprint = _source_fingerprint(_row_value(row, "source_fingerprint"))
        selector = (stable_id, episode_index)
        if selector in selectors:
            raise RetrievalBenchmarkError("Database snapshot contains duplicate episode selectors")
        selectors.add(selector)
        parsed.append((stable_id, episode_index, source_fingerprint, row))

    parsed.sort(key=lambda item: (item[0], item[1]))
    canonical = "".join(
        f"{stable_id}|{episode_index}|{source_fingerprint}\n"
        for stable_id, episode_index, source_fingerprint, _ in parsed
    ).encode("utf-8")
    snapshot = SourceSnapshot(
        episode_count=len(parsed),
        document_count=len({stable_id for stable_id, _, _, _ in parsed}),
        fingerprint="source-snapshot:sha256:" + hashlib.sha256(canonical).hexdigest(),
    )
    return snapshot, {(stable_id, index): row for stable_id, index, _, row in parsed}


def reconcile_retrieval_corpus(
    corpus: RetrievalCorpus,
    rows: Sequence[object],
) -> dict[str, object]:
    """Validate snapshot identity, judgments, and entity grounding without emitting content."""
    actual_snapshot, by_selector = summarize_source_snapshot(rows)
    findings: list[dict[str, str]] = []
    case_findings: list[dict[str, object]] = []

    def add(code: str, message: str) -> None:
        if not any(finding["code"] == code for finding in findings):
            findings.append({"code": code, "severity": "error", "message": message})

    if actual_snapshot.episode_count != corpus.source_snapshot.episode_count:
        add("snapshot_episode_count_mismatch", "Source snapshot episode count differs")
    if actual_snapshot.document_count != corpus.source_snapshot.document_count:
        add("snapshot_document_count_mismatch", "Source snapshot document count differs")
    if actual_snapshot.fingerprint != corpus.source_snapshot.fingerprint:
        add("snapshot_fingerprint_mismatch", "Source snapshot fingerprint differs")

    matched_judgments = 0
    grounded_entities = 0
    for case in corpus.cases:
        codes: set[str] = set()
        ungrounded_entity_ids: list[str] = []
        judged_text = ""
        for judgment in case.judgments:
            row = by_selector.get(judgment.selector)
            if row is None:
                codes.add("judgment_episode_missing")
                continue
            actual_fingerprint = _row_value(row, "source_fingerprint")
            if actual_fingerprint != judgment.source_fingerprint:
                codes.add("judgment_source_fingerprint_mismatch")
                continue
            matched_judgments += 1
            text = _row_value(row, "text")
            if isinstance(text, str):
                judged_text += "\n" + text

        normalized_text = _normalize(judged_text)
        for entity in case.expected_entities:
            if any(_normalize(alias) in normalized_text for alias in entity.aliases):
                grounded_entities += 1
            else:
                codes.add("expected_entity_not_grounded")
                ungrounded_entity_ids.append(entity.id)
        if codes:
            case_findings.append(
                {
                    "case_id": case.id,
                    "codes": sorted(codes),
                    "ungrounded_entity_ids": sorted(ungrounded_entity_ids),
                }
            )

    if matched_judgments != corpus.judgment_count:
        add("judgments_not_reconciled", "Not every graded judgment matches the snapshot")
    if grounded_entities != corpus.expected_entity_count:
        add("entities_not_grounded", "Not every expected entity is grounded in judged episodes")

    return {
        "schema_version": 1,
        "operation": "retrieval_corpus_validation",
        "status": "valid" if not findings and not case_findings else "drift",
        "corpus_id": corpus.corpus_id,
        "corpus_fingerprint": corpus.fingerprint,
        "case_count": len(corpus.cases),
        "judgment_count": corpus.judgment_count,
        "matched_judgments": matched_judgments,
        "expected_entity_count": corpus.expected_entity_count,
        "grounded_entity_count": grounded_entities,
        "expected_source_snapshot": {
            "episode_count": corpus.source_snapshot.episode_count,
            "document_count": corpus.source_snapshot.document_count,
            "fingerprint": corpus.source_snapshot.fingerprint,
        },
        "actual_source_snapshot": {
            "episode_count": actual_snapshot.episode_count,
            "document_count": actual_snapshot.document_count,
            "fingerprint": actual_snapshot.fingerprint,
        },
        "findings": sorted(findings, key=lambda finding: finding["code"]),
        "case_findings": case_findings,
    }


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def score_retrieval_case(
    case: RetrievalCase,
    ranked: Sequence[RankedEpisode],
    *,
    cutoffs: tuple[int, ...] = (5, 10),
) -> dict[str, object]:
    """Score one ordered result set without returning queries or episode selectors."""
    selectors = [result.selector for result in ranked]
    if len(selectors) != len(set(selectors)):
        raise RetrievalBenchmarkError("Ranked results contain duplicate episode selectors")

    relevance = {judgment.selector: judgment.relevance for judgment in case.judgments}
    grades = [relevance.get(selector, 0) for selector in selectors]
    result: dict[str, object] = {
        "case_id": case.id,
        "relevant_episode_count": len(relevance),
        "returned_episode_count": len(ranked),
    }
    for cutoff in cutoffs:
        retrieved = sum(grade > 0 for grade in grades[:cutoff])
        result[f"recall_at_{cutoff}"] = retrieved / len(relevance)

    maximum_cutoff = max(cutoffs)
    first_relevant_rank = next(
        (rank for rank, grade in enumerate(grades[:maximum_cutoff], start=1) if grade > 0),
        None,
    )
    ideal_grades = sorted(relevance.values(), reverse=True)[:maximum_cutoff]
    actual_dcg = _dcg(grades[:maximum_cutoff])
    ideal_dcg = _dcg(ideal_grades)
    result[f"reciprocal_rank_at_{maximum_cutoff}"] = (
        1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
    )
    result[f"ndcg_at_{maximum_cutoff}"] = actual_dcg / ideal_dcg if ideal_dcg else 0.0
    result["first_relevant_rank"] = first_relevant_rank
    return result


def score_retrieval_corpus(
    corpus: RetrievalCorpus,
    rankings: Mapping[str, Sequence[RankedEpisode]],
) -> dict[str, object]:
    """Compute macro Recall@5/10, MRR@10, and nDCG@10 for every corpus case."""
    expected_ids = {case.id for case in corpus.cases}
    if set(rankings) != expected_ids:
        raise RetrievalBenchmarkError("Rankings must cover every corpus case exactly once")
    case_results = [
        score_retrieval_case(case, rankings[case.id], cutoffs=corpus.cutoffs)
        for case in corpus.cases
    ]
    case_count = len(case_results)
    maximum_cutoff = max(corpus.cutoffs)
    metrics = {
        f"recall_at_{cutoff}": sum(float(result[f"recall_at_{cutoff}"]) for result in case_results)
        / case_count
        for cutoff in corpus.cutoffs
    }
    metrics[f"mrr_at_{maximum_cutoff}"] = (
        sum(float(result[f"reciprocal_rank_at_{maximum_cutoff}"]) for result in case_results)
        / case_count
    )
    metrics[f"ndcg_at_{maximum_cutoff}"] = (
        sum(float(result[f"ndcg_at_{maximum_cutoff}"]) for result in case_results) / case_count
    )
    return {
        "schema_version": 1,
        "operation": "episode_retrieval_benchmark",
        "status": "completed",
        "corpus_id": corpus.corpus_id,
        "corpus_fingerprint": corpus.fingerprint,
        "source_snapshot_fingerprint": corpus.source_snapshot.fingerprint,
        "case_count": case_count,
        "judgment_count": corpus.judgment_count,
        "metrics": metrics,
        "cases": case_results,
        "acceptance_thresholds": "not_configured",
        "manual_review_required": True,
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def planned_provider_requests(corpus: RetrievalCorpus, profile: EmbeddingProfile) -> int:
    """Return the exact no-retry request count implied by profile batch size."""
    return math.ceil(len(corpus.cases) / profile.batch_size)


async def benchmark_episode_space(
    postgres: Any,
    corpus: RetrievalCorpus,
    profile: EmbeddingProfile,
    embedder: Any,
    *,
    maximum_provider_requests: int,
    search_query: str,
    evaluated_space: Mapping[str, object],
) -> dict[str, object]:
    """Embed fixed queries and score one attested episode vector space read-only."""
    if not 1 <= maximum_provider_requests <= 100:
        raise RetrievalBenchmarkError("Maximum provider requests must be between 1 and 100")
    batch_size = profile.batch_size
    planned_requests = planned_provider_requests(corpus, profile)
    if planned_requests > maximum_provider_requests:
        raise RetrievalBenchmarkError("Embedding batch plan exceeds the provider-request ceiling")

    vectors: list[list[float]] = []
    usage: dict[str, int] = {}
    actual_models: set[str] = set()
    embedding_started = perf_counter()
    completed_requests = 0
    for start in range(0, len(corpus.cases), batch_size):
        case_batch = corpus.cases[start : start + batch_size]
        batch_vectors = await embedder.embed_batch([case.query for case in case_batch])
        vectors.extend(
            validate_embedding_batch(
                batch_vectors,
                expected_count=len(case_batch),
                dimensions=profile.dimensions,
            )
        )
        completed_requests += 1
        metadata_reader = getattr(embedder, "sanitized_metadata", None)
        metadata = metadata_reader() if callable(metadata_reader) else {}
        if isinstance(metadata, Mapping):
            actual_model = metadata.get("actual_model")
            if isinstance(actual_model, str) and actual_model:
                actual_models.add(actual_model)
            response_usage = metadata.get("usage")
            if isinstance(response_usage, Mapping):
                for name, count in response_usage.items():
                    if (
                        isinstance(name, str)
                        and isinstance(count, int)
                        and not isinstance(count, bool)
                        and count >= 0
                    ):
                        usage[name] = usage.get(name, 0) + count
    embedding_ms = (perf_counter() - embedding_started) * 1_000

    rankings: dict[str, list[RankedEpisode]] = {}
    search_latencies: list[float] = []
    result_limit = max(corpus.cutoffs)
    for case, vector in zip(corpus.cases, vectors, strict=True):
        vector_text = "[" + ",".join(map(str, vector)) + "]"
        search_started = perf_counter()
        rows = await postgres.fetch(search_query, vector_text, result_limit)
        search_latencies.append((perf_counter() - search_started) * 1_000)
        rankings[case.id] = [
            RankedEpisode(
                document_stable_id=_document_stable_id(_row_value(row, "document_stable_id")),
                episode_index=_integer(
                    _row_value(row, "episode_index"),
                    "Episode index",
                    minimum=0,
                    maximum=1_000_000,
                ),
                similarity=(
                    float(_row_value(row, "similarity"))
                    if _row_value(row, "similarity") is not None
                    else None
                ),
            )
            for row in rows
        ]

    report = score_retrieval_corpus(corpus, rankings)
    report.update(
        {
            "embedding_profile": embedding_profile_record(profile),
            "evaluated_space": dict(evaluated_space),
            "provider_requests": {
                "maximum": maximum_provider_requests,
                "planned": planned_requests,
                "completed": completed_requests,
            },
            "actual_models": sorted(actual_models),
            "usage": dict(sorted(usage.items())),
            "estimated_cost_usd": None,
            "cost_estimation_status": "not_configured",
            "timing_ms": {
                "query_embedding_total": embedding_ms,
                "search_total": sum(search_latencies),
                "search_p50": _percentile(search_latencies, 0.50),
                "search_p95": _percentile(search_latencies, 0.95),
            },
        }
    )
    return report


async def benchmark_active_episode_space(
    postgres: Any,
    corpus: RetrievalCorpus,
    profile: EmbeddingProfile,
    embedder: Any,
    *,
    maximum_provider_requests: int,
) -> dict[str, object]:
    """Compatibility wrapper for the active episode vector space."""
    return await benchmark_episode_space(
        postgres,
        corpus,
        profile,
        embedder,
        maximum_provider_requests=maximum_provider_requests,
        search_query=ACTIVE_EPISODE_SEARCH_QUERY,
        evaluated_space={"kind": "active", "physical_space": "episodes.embedding"},
    )
