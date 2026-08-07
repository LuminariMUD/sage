"""Offline coverage for the versioned episode-retrieval quality boundary."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.llm.provider_config import resolve_provider_settings
from src.retrieval.benchmark import (
    EpisodeJudgment,
    ExpectedEntity,
    RankedEpisode,
    RetrievalBenchmarkError,
    RetrievalCase,
    RetrievalCorpus,
    benchmark_active_episode_space,
    load_retrieval_corpus,
    reconcile_retrieval_corpus,
    score_retrieval_case,
    score_retrieval_corpus,
    summarize_source_snapshot,
)
from src.scripts import benchmark_retrieval

CORPUS_PATH = Path(__file__).resolve().parents[2] / "benchmarks" / "episode_retrieval_v1.json"
SOURCE_A = "sha256:v1:" + "a" * 64
SOURCE_B = "sha256:v1:" + "b" * 64


def _profile(*, dimensions: int = 3, batch_size: int = 32):
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": str(dimensions),
            "OLLAMA_EMBEDDING_BATCH_SIZE": str(batch_size),
        }
    ).embedding_profile


def _rows():
    return [
        {
            "document_stable_id": "doc_alpha",
            "episode_index": 0,
            "source_fingerprint": SOURCE_A,
            "text": "Alpha Entity guards the archive.",
        },
        {
            "document_stable_id": "doc_beta",
            "episode_index": 1,
            "source_fingerprint": SOURCE_B,
            "text": "Beta Entity records the route.",
        },
    ]


def _corpus(rows=None):
    selected_rows = rows or _rows()
    snapshot, _ = summarize_source_snapshot(selected_rows)
    return RetrievalCorpus(
        schema_version=1,
        corpus_id="test-retrieval:v1",
        description="Test corpus",
        fingerprint="corpus:sha256:" + "c" * 64,
        source_snapshot=snapshot,
        cutoffs=(5, 10),
        cases=(
            RetrievalCase(
                id="alpha_lookup",
                query="Who guards the archive?",
                expected_entities=(ExpectedEntity(id="alpha", aliases=("Alpha Entity",)),),
                judgments=(
                    EpisodeJudgment(
                        document_stable_id="doc_alpha",
                        episode_index=0,
                        source_fingerprint=SOURCE_A,
                        relevance=3,
                    ),
                    EpisodeJudgment(
                        document_stable_id="doc_beta",
                        episode_index=1,
                        source_fingerprint=SOURCE_B,
                        relevance=1,
                    ),
                ),
            ),
        ),
    )


def test_checked_in_corpus_is_versioned_and_has_graded_portable_judgments():
    corpus = load_retrieval_corpus(CORPUS_PATH)

    assert corpus.schema_version == 1
    assert corpus.corpus_id == "luminari-episode-retrieval:v1"
    assert corpus.cutoffs == (5, 10)
    assert len(corpus.cases) == 12
    assert corpus.judgment_count == 33
    assert corpus.expected_entity_count == 39
    assert corpus.source_snapshot.episode_count == 611
    assert corpus.source_snapshot.document_count == 14
    assert corpus.fingerprint.startswith("corpus:sha256:")
    assert all(case.expected_entities and case.judgments for case in corpus.cases)


def test_corpus_loader_rejects_duplicate_judgments(tmp_path):
    rows = _rows()
    snapshot, _ = summarize_source_snapshot(rows)
    judgment = {
        "document_stable_id": "doc_alpha",
        "episode_index": 0,
        "source_fingerprint": SOURCE_A,
        "relevance": 3,
    }
    payload = {
        "schema_version": 1,
        "corpus_id": "test:v1",
        "description": "test",
        "source_snapshot": {
            "episode_count": snapshot.episode_count,
            "document_count": snapshot.document_count,
            "fingerprint": snapshot.fingerprint,
        },
        "metrics": {"cutoffs": [5, 10]},
        "cases": [
            {
                "id": "duplicate",
                "query": "Where is Alpha?",
                "expected_entities": [{"id": "alpha", "aliases": ["Alpha"]}],
                "judgments": [judgment, judgment],
            }
        ],
    }
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RetrievalBenchmarkError, match="unique episode selectors"):
        load_retrieval_corpus(path)


def test_snapshot_identity_is_order_independent_and_content_free():
    forward, _ = summarize_source_snapshot(_rows())
    reverse, _ = summarize_source_snapshot(list(reversed(_rows())))

    assert forward == reverse
    assert forward.episode_count == 2
    assert forward.document_count == 2
    assert forward.fingerprint.startswith("source-snapshot:sha256:")
    assert "Alpha Entity" not in forward.fingerprint


def test_snapshot_reconciliation_validates_judgments_and_entity_grounding():
    report = reconcile_retrieval_corpus(_corpus(), _rows())

    assert report["status"] == "valid"
    assert report["matched_judgments"] == 2
    assert report["grounded_entity_count"] == 1
    serialized = json.dumps(report)
    assert "guards the archive" not in serialized
    assert "doc_alpha" not in serialized


def test_snapshot_reconciliation_reports_source_and_grounding_drift():
    rows = _rows()
    rows[0] = {
        **rows[0],
        "source_fingerprint": "sha256:v1:" + "d" * 64,
        "text": "No expected name remains.",
    }

    report = reconcile_retrieval_corpus(_corpus(), rows)

    codes = {finding["code"] for finding in report["findings"]}
    assert report["status"] == "drift"
    assert "snapshot_fingerprint_mismatch" in codes
    assert "judgments_not_reconciled" in codes
    assert "entities_not_grounded" in codes
    assert report["case_findings"] == [
        {
            "case_id": "alpha_lookup",
            "codes": [
                "expected_entity_not_grounded",
                "judgment_source_fingerprint_mismatch",
            ],
            "ungrounded_entity_ids": ["alpha"],
        }
    ]


def test_case_scoring_produces_recall_reciprocal_rank_and_ndcg():
    case = _corpus().cases[0]
    ranked = [
        RankedEpisode("irrelevant", 9),
        RankedEpisode("doc_alpha", 0),
        RankedEpisode("doc_beta", 1),
    ]

    score = score_retrieval_case(case, ranked)

    assert score["recall_at_5"] == 1.0
    assert score["recall_at_10"] == 1.0
    assert score["reciprocal_rank_at_10"] == 0.5
    assert score["first_relevant_rank"] == 2
    assert 0 < score["ndcg_at_10"] < 1


def test_corpus_scoring_requires_exact_case_coverage_and_hides_queries():
    corpus = _corpus()
    perfect = [
        RankedEpisode("doc_alpha", 0),
        RankedEpisode("doc_beta", 1),
    ]

    report = score_retrieval_corpus(corpus, {"alpha_lookup": perfect})

    assert report["metrics"] == {
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
    }
    assert report["acceptance_thresholds"] == "not_configured"
    assert corpus.cases[0].query not in json.dumps(report)

    with pytest.raises(RetrievalBenchmarkError, match="every corpus case"):
        score_retrieval_corpus(corpus, {})


def test_case_scoring_rejects_duplicate_ranked_episodes():
    duplicate = RankedEpisode("doc_alpha", 0)

    with pytest.raises(RetrievalBenchmarkError, match="duplicate episode"):
        score_retrieval_case(_corpus().cases[0], [duplicate, duplicate])


async def test_active_benchmark_enforces_batch_budget_and_emits_sanitized_metrics():
    corpus = _corpus()
    profile = _profile()

    class FakeEmbedder:
        async def embed_batch(self, texts):
            assert texts == ["Who guards the archive?"]
            return [[1.0, 0.0, 0.0]]

        def sanitized_metadata(self):
            return {
                "actual_model": "local/embed",
                "usage": {"input_tokens": 4, "total_tokens": 4},
            }

    class FakePostgres:
        async def fetch(self, query, *args):
            assert "$1::vector" in query
            assert args[1] == 10
            return [
                {
                    "document_stable_id": "doc_alpha",
                    "episode_index": 0,
                    "similarity": 0.9,
                },
                {
                    "document_stable_id": "doc_beta",
                    "episode_index": 1,
                    "similarity": 0.8,
                },
            ]

    report = await benchmark_active_episode_space(
        FakePostgres(),
        corpus,
        profile,
        FakeEmbedder(),
        maximum_provider_requests=1,
    )

    assert report["status"] == "completed"
    assert report["provider_requests"] == {"maximum": 1, "planned": 1, "completed": 1}
    assert report["evaluated_space"] == {
        "kind": "active",
        "physical_space": "episodes.embedding",
    }
    assert report["usage"] == {"input_tokens": 4, "total_tokens": 4}
    assert report["estimated_cost_usd"] is None
    serialized = json.dumps(report)
    assert "Who guards the archive?" not in serialized
    assert "doc_alpha" not in serialized
    assert "[1.0, 0.0, 0.0]" not in serialized


async def test_cli_refuses_run_before_corpus_configuration_or_database(capsys):
    corpus_loader = Mock(side_effect=AssertionError("must not load corpus"))
    postgres_factory = Mock(side_effect=AssertionError("must not connect"))
    profile_resolver = Mock(side_effect=AssertionError("must not resolve profile"))

    result = await benchmark_retrieval.run(
        Namespace(
            command="run",
            confirm="",
            max_provider_requests=1,
            corpus=CORPUS_PATH,
            json=False,
        ),
        postgres_factory=postgres_factory,
        corpus_loader=corpus_loader,
        profile_resolver=profile_resolver,
    )

    assert result == 2
    corpus_loader.assert_not_called()
    postgres_factory.assert_not_called()
    profile_resolver.assert_not_called()
    assert "REFUSED" in capsys.readouterr().err


async def test_cli_validation_uses_read_only_database_without_provider_resolution(capsys):
    read_only_values = []
    profile_resolver = Mock(side_effect=AssertionError("validation has no provider"))

    class FakePostgres:
        async def connect(self):
            return None

        async def fetch(self, query):
            assert "graph_sync_jobs" in query
            return _rows()

        async def disconnect(self):
            return None

    def postgres_factory(*, read_only):
        read_only_values.append(read_only)
        return FakePostgres()

    result = await benchmark_retrieval.run(
        Namespace(command="validate", corpus=CORPUS_PATH, json=False),
        postgres_factory=postgres_factory,
        corpus_loader=lambda path: _corpus(),
        profile_resolver=profile_resolver,
    )

    assert result == 0
    assert read_only_values == [True]
    profile_resolver.assert_not_called()
    assert "VALID" in capsys.readouterr().out


async def test_cli_drift_blocks_profile_resolution_and_embedder_construction(capsys):
    drifted_rows = _rows()
    drifted_rows[0] = {**drifted_rows[0], "text": "Grounding removed."}
    profile_resolver = Mock(side_effect=AssertionError("drift must block profile"))
    embedder_factory = Mock(side_effect=AssertionError("drift must block adapter"))

    class FakePostgres:
        async def connect(self):
            return None

        async def fetch(self, query):
            return drifted_rows

        async def disconnect(self):
            return None

    result = await benchmark_retrieval.run(
        Namespace(
            command="run",
            confirm=benchmark_retrieval.BENCHMARK_CONFIRMATION,
            max_provider_requests=1,
            corpus=CORPUS_PATH,
            json=False,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        corpus_loader=lambda path: _corpus(),
        profile_resolver=profile_resolver,
        embedder_factory=embedder_factory,
    )

    assert result == 1
    profile_resolver.assert_not_called()
    embedder_factory.assert_not_called()
    assert "DRIFT" in capsys.readouterr().err


async def test_cli_redacts_arbitrary_configuration_value_errors(capsys):
    secret_marker = "provider-secret-marker"

    class FakePostgres:
        async def connect(self):
            return None

        async def fetch(self, query):
            return _rows()

        async def disconnect(self):
            return None

    result = await benchmark_retrieval.run(
        Namespace(
            command="run",
            confirm=benchmark_retrieval.BENCHMARK_CONFIRMATION,
            max_provider_requests=1,
            corpus=CORPUS_PATH,
            json=False,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        corpus_loader=lambda path: _corpus(),
        profile_resolver=Mock(side_effect=ValueError(secret_marker)),
    )

    error_output = capsys.readouterr().err
    assert result == 2
    assert secret_marker not in error_output
    assert "configuration or response is invalid" in error_output
    assert "ValueError" in error_output


async def test_cli_storage_preflight_blocks_embedder_construction(monkeypatch, capsys):
    embedder_factory = Mock(side_effect=AssertionError("preflight must block adapter"))
    benchmark_runner = AsyncMock(side_effect=AssertionError("preflight must block benchmark"))

    class FakePostgres:
        async def connect(self):
            return None

        async def fetch(self, query):
            return _rows()

        async def disconnect(self):
            return None

    monkeypatch.setattr(
        benchmark_retrieval,
        "preflight_embedding_space",
        AsyncMock(
            return_value={
                "ready": False,
                "findings": [{"code": "active_space_missing", "severity": "error"}],
            }
        ),
    )

    result = await benchmark_retrieval.run(
        Namespace(
            command="run",
            confirm=benchmark_retrieval.BENCHMARK_CONFIRMATION,
            max_provider_requests=1,
            corpus=CORPUS_PATH,
            json=False,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        corpus_loader=lambda path: _corpus(),
        profile_resolver=_profile,
        embedder_factory=embedder_factory,
        benchmark_runner=benchmark_runner,
    )

    assert result == 2
    embedder_factory.assert_not_called()
    benchmark_runner.assert_not_awaited()
    assert "active_space_missing" in capsys.readouterr().err


async def test_cli_shadow_preflight_selects_attested_shadow_query_before_adapter(capsys):
    profile = _profile()
    profile_resolver = Mock(side_effect=AssertionError("active profile must not resolve"))
    shadow_profile_resolver = Mock(return_value=profile)
    embedder = object()
    embedder_factory = Mock(return_value=embedder)
    benchmark_runner = AsyncMock(
        return_value={
            "schema_version": 1,
            "operation": "episode_retrieval_benchmark",
            "status": "completed",
        }
    )

    class FakePostgres:
        async def connect(self):
            return None

        async def fetch(self, query, *args):
            return _rows()

        async def disconnect(self):
            return None

    class FakeShadowRepository:
        def __init__(self):
            self.required = []

        async def require_ready(self, selected_profile):
            self.required.append(selected_profile)
            return {"ready": True}

    shadow_repository = FakeShadowRepository()
    result = await benchmark_retrieval.run(
        Namespace(
            command="run",
            confirm=benchmark_retrieval.BENCHMARK_CONFIRMATION,
            max_provider_requests=1,
            corpus=CORPUS_PATH,
            space="shadow",
            provider="ollama",
            json=True,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        corpus_loader=lambda path: _corpus(),
        profile_resolver=profile_resolver,
        shadow_profile_resolver=shadow_profile_resolver,
        embedder_factory=embedder_factory,
        benchmark_runner=benchmark_runner,
        shadow_repository_factory=lambda postgres: shadow_repository,
    )

    assert result == 0
    profile_resolver.assert_not_called()
    shadow_profile_resolver.assert_called_once_with("ollama")
    assert shadow_repository.required == [profile]
    embedder_factory.assert_called_once_with(profile, transport_max_retries=0)
    benchmark_runner.assert_awaited_once()
    arguments = benchmark_runner.await_args
    assert arguments.args[3] is embedder
    assert profile.fingerprint in arguments.kwargs["search_query"]
    assert arguments.kwargs["evaluated_space"] == {
        "kind": "shadow",
        "profile_fingerprint": profile.fingerprint,
    }
    assert _corpus().cases[0].query not in capsys.readouterr().out
