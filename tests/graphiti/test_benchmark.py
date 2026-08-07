"""Offline contracts for the fixed-corpus, non-persistent Graphiti benchmark."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.graphiti import benchmark as benchmark_module
from src.graphiti.benchmark import (
    BenchmarkCallBudgetExceeded,
    BenchmarkConfigurationError,
    BenchmarkExtractionResult,
    BenchmarkProviderCallBudget,
    benchmark_candidate,
    extract_staged_policy_graph,
    load_benchmark_corpus,
    score_benchmark_case,
)
from src.graphiti.provider_config import create_graphiti_llm_client
from src.graphiti.provider_tracking import ProviderCallTracker
from src.graphiti.relationship_policy import (
    RELATIONSHIP_VOCABULARY_FINGERPRINT,
    RelationshipQualityReport,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.llm.provider_config import resolve_provider_settings
from src.llm.retry import ModelSchemaValidationError
from src.scripts import benchmark_graphiti

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = PROJECT_ROOT / "benchmarks" / "graphiti_extraction_v2.json"


def _candidate():
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_REASONING_MODEL": "local/reasoning",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
        }
    ).graphiti_text_route.primary


def _fake_client(candidate, events=None):
    events = [] if events is None else events

    async def create(*args, **kwargs):
        events.append("network")
        return SimpleNamespace(
            model=candidate.model,
            provider="offline-test",
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )

    async def close():
        events.append("close")

    completions = SimpleNamespace(create=create)
    transport = SimpleNamespace(
        max_retries=0,
        chat=SimpleNamespace(completions=completions),
        close=close,
    )
    return SimpleNamespace(client=transport), completions, create


def _extraction(
    nodes,
    edges,
    *,
    proposed_edges=None,
    normalized_edges=0,
):
    accepted_edges = len(edges)
    proposed_edges = accepted_edges if proposed_edges is None else proposed_edges
    rejected_edges = proposed_edges - accepted_edges
    return BenchmarkExtractionResult(
        nodes=nodes,
        edges=edges,
        node_episode_index_map={},
        relationship_quality=RelationshipQualityReport(
            vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
            proposed_edges=proposed_edges,
            normalized_edges=normalized_edges,
            accepted_edges=accepted_edges,
            rejected_edges=rejected_edges,
            rejected_unknown_type=rejected_edges,
        ),
    )


def test_checked_in_corpus_is_versioned_bounded_and_referentially_valid():
    corpus = load_benchmark_corpus(CORPUS_PATH)

    assert corpus.schema_version == 2
    assert corpus.corpus_id == "luminari-graphiti-extraction:v2"
    assert corpus.fingerprint.startswith("corpus:sha256:")
    assert len(corpus.cases) == 3
    assert all(case.expect_parse_success for case in corpus.cases)
    assert all(case.expect_schema_success for case in corpus.cases)
    assert all(case.expected_entities for case in corpus.cases)
    assert all(case.expected_relationships for case in corpus.cases)


def test_corpus_rejects_relationships_that_reference_unknown_entities(tmp_path):
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_relationships"][0]["target"] = "missing"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkConfigurationError, match="endpoints"):
        load_benchmark_corpus(path)


def test_corpus_requires_explicit_outcomes_and_canonical_relationship_types(tmp_path):
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    del payload["cases"][0]["expect_schema_success"]
    path = tmp_path / "missing-outcome.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkConfigurationError, match="Boolean"):
        load_benchmark_corpus(path)

    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_relationships"][0]["types"] = ["RELATES_TO"]
    path = tmp_path / "unknown-relationship.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkConfigurationError, match="canonical vocabulary"):
        load_benchmark_corpus(path)

    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expect_parse_success"] = False
    path = tmp_path / "unexpected-failure.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkConfigurationError, match="must require"):
        load_benchmark_corpus(path)


def test_case_scoring_reports_counts_without_extracted_content():
    case = load_benchmark_corpus(CORPUS_PATH).cases[0]
    nodes = [
        SimpleNamespace(uuid="loom", name="The Order of the Crimson Loom"),
        SimpleNamespace(uuid="spindle", name="Crimson Spindle"),
    ]
    edges = [
        SimpleNamespace(
            source_node_uuid="loom",
            target_node_uuid="spindle",
            name="PROTECTS",
            fact="sensitive extracted fact",
        )
    ]

    score = score_benchmark_case(case, nodes, edges)

    assert score["entity_recall"] == 1
    assert score["relationship_recall"] == 1
    assert "sensitive extracted fact" not in str(score)
    assert "Crimson Spindle" not in str(score)


async def test_staged_benchmark_extraction_applies_policy_before_edges(monkeypatch):
    nodes = [
        SimpleNamespace(uuid="alpha", name="Alpha"),
        SimpleNamespace(uuid="beta", name="Beta"),
    ]

    class Delegate:
        async def generate_response(self, *args, **kwargs):
            return {
                "edges": [
                    {
                        "source_entity_name": "Alpha",
                        "target_entity_name": "Beta",
                        "relation_type": "OPPOSED_TO",
                        "fact": "A valid fact",
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Alpha",
                        "target_entity_name": "Beta",
                        "relation_type": "RELATES_TO",
                        "fact": "An unknown predicate",
                        "episode_indices": [0],
                    },
                ]
            }

    async def fake_extract_nodes(*args):
        return nodes, {"alpha": [0], "beta": [0]}

    async def fake_extract_edges(clients, *args):
        response = await clients.llm_client.generate_response([], prompt_name="extract_edges.edge")
        assert [edge["relation_type"] for edge in response["edges"]] == ["OpposedTo"]
        return [
            SimpleNamespace(
                source_node_uuid="alpha",
                target_node_uuid="beta",
                name="OpposedTo",
            )
        ]

    monkeypatch.setattr(benchmark_module, "extract_nodes", fake_extract_nodes)
    monkeypatch.setattr(benchmark_module, "extract_edges", fake_extract_edges)
    episode = SimpleNamespace(group_id="benchmark", uuid="episode")

    result = await extract_staged_policy_graph(
        SimpleNamespace(llm_client=Delegate()),
        episode,
        [],
        entity_types={},
        edge_types={},
        edge_type_map={},
        custom_extraction_instructions="bounded",
    )

    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    assert result.relationship_quality.proposed_edges == 2
    assert result.relationship_quality.accepted_edges == 1
    assert result.relationship_quality.normalized_edges == 1
    assert result.relationship_quality.rejected_unknown_type == 1


@pytest.mark.asyncio
async def test_provider_call_budget_counts_usage_and_rejects_before_second_network_call():
    candidate = _candidate()
    events = []
    llm_client, completions, original = _fake_client(candidate, events)
    budget = BenchmarkProviderCallBudget(llm_client, candidate, maximum_calls=1)

    async with budget.installed():
        await completions.create(model=candidate.model, messages=[])
        with pytest.raises(BenchmarkCallBudgetExceeded):
            await completions.create(model=candidate.model, messages=[])

    assert events == ["network"]
    assert completions.create is original
    assert budget.sanitized_summary() == {
        "provider_calls": 1,
        "budget_rejections": 1,
        "failed_provider_calls": 0,
        "provider_failures": {},
        "usage": {"completion_tokens": 2, "prompt_tokens": 3, "total_tokens": 5},
        "actual_models": [candidate.model],
        "upstream_providers": ["offline-test"],
    }


@pytest.mark.asyncio
async def test_candidate_benchmark_scores_fixed_cases_without_persistence_or_content():
    corpus = load_benchmark_corpus(CORPUS_PATH)
    candidate = _candidate()
    cases = {case.id: case for case in corpus.cases}

    async def extractor(clients, episode, previous, **kwargs):
        await clients.llm_client.client.chat.completions.create(
            model=candidate.model,
            messages=[],
        )
        case = cases[episode.name.removeprefix("benchmark-")]
        nodes = [
            SimpleNamespace(uuid=entity.id, name=entity.aliases[0])
            for entity in case.expected_entities
        ]
        edges = [
            SimpleNamespace(
                source_node_uuid=relationship.source,
                target_node_uuid=relationship.target,
                name=relationship.types[0],
                fact="sensitive extracted fact",
            )
            for relationship in case.expected_relationships
        ]
        return _extraction(
            nodes,
            edges,
            proposed_edges=len(edges) + int(case.id == "crimson_guard"),
            normalized_edges=int(case.id == "crimson_guard"),
        )

    report = await benchmark_candidate(
        corpus,
        candidate,
        route_fingerprint="route:test",
        sync_profile_fingerprint="sync:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        relationship_vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        max_entities=25,
        max_relationships=25,
        maximum_provider_calls=2,
        concurrency=2,
        client_factory=lambda selected: _fake_client(selected)[0],
        extractor=extractor,
    )

    assert report["status"] == "passed"
    assert report["entity_recall"] == 1
    assert report["relationship_recall"] == 1
    assert report["provider_calls"] == len(corpus.cases)
    assert report["parse_success_cases"] == len(corpus.cases)
    assert report["schema_success_cases"] == len(corpus.cases)
    assert report["structured_expectation_matches"] == len(corpus.cases)
    assert report["relationship_quality"]["evidence_cases"] == len(corpus.cases)
    assert report["relationship_quality"]["proposed_edges"] == 4
    assert report["relationship_quality"]["accepted_edges"] == 3
    assert report["relationship_quality"]["rejection_reasons"]["rejected_unknown_type"] == 1
    assert "sensitive extracted fact" not in str(report)
    assert all(case.episode not in str(report) for case in corpus.cases)


async def test_candidate_benchmark_rejects_relationship_policy_drift_before_client():
    touched = False

    def forbidden(*args):
        nonlocal touched
        touched = True
        raise AssertionError("client construction must remain unused")

    with pytest.raises(BenchmarkConfigurationError, match="vocabulary is not current"):
        await benchmark_candidate(
            load_benchmark_corpus(CORPUS_PATH),
            _candidate(),
            route_fingerprint="route:test",
            sync_profile_fingerprint="sync:test",
            prompt_version="prompt:v1",
            schema_version="schema:v1",
            relationship_vocabulary_fingerprint="relationships:sha256:" + ("0" * 64),
            max_entities=25,
            max_relationships=25,
            maximum_provider_calls=2,
            concurrency=1,
            client_factory=forbidden,
        )

    assert touched is False


@pytest.mark.asyncio
async def test_recovered_provider_failure_is_reported_as_degraded_without_detail():
    corpus = load_benchmark_corpus(CORPUS_PATH)
    candidate = _candidate()
    cases = {case.id: case for case in corpus.cases}

    def client_factory(selected):
        calls = 0

        async def create(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("sensitive provider detail")
            return SimpleNamespace(model=selected.model)

        async def close():
            return None

        return SimpleNamespace(
            client=SimpleNamespace(
                max_retries=0,
                chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                close=close,
            )
        )

    async def extractor(clients, episode, previous, **kwargs):
        try:
            await clients.llm_client.client.chat.completions.create(
                model=candidate.model,
                messages=[],
            )
        except TimeoutError:
            pass
        await clients.llm_client.client.chat.completions.create(
            model=candidate.model,
            messages=[],
        )
        case = cases[episode.name.removeprefix("benchmark-")]
        nodes = [
            SimpleNamespace(uuid=entity.id, name=entity.aliases[0])
            for entity in case.expected_entities
        ]
        edges = [
            SimpleNamespace(
                source_node_uuid=relationship.source,
                target_node_uuid=relationship.target,
                name=relationship.types[0],
            )
            for relationship in case.expected_relationships
        ]
        return _extraction(nodes, edges)

    report = await benchmark_candidate(
        corpus,
        candidate,
        route_fingerprint="route:test",
        sync_profile_fingerprint="sync:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        relationship_vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        max_entities=25,
        max_relationships=25,
        maximum_provider_calls=2,
        concurrency=1,
        client_factory=client_factory,
        extractor=extractor,
    )

    assert report["status"] == "failed"
    assert all(result["status"] == "degraded" for result in report["cases"])
    assert all(result["failed_provider_calls"] == 1 for result in report["cases"])
    assert "sensitive provider detail" not in str(report)


@pytest.mark.asyncio
async def test_candidate_benchmark_records_budget_exhaustion_without_exception_detail():
    corpus = load_benchmark_corpus(CORPUS_PATH)
    candidate = _candidate()

    async def extractor(clients, episode, previous, **kwargs):
        for _ in range(2):
            await clients.llm_client.client.chat.completions.create(
                model=candidate.model,
                messages=[],
            )
        raise AssertionError("unreachable sensitive detail")

    report = await benchmark_candidate(
        corpus,
        candidate,
        route_fingerprint="route:test",
        sync_profile_fingerprint="sync:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        relationship_vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        max_entities=25,
        max_relationships=25,
        maximum_provider_calls=1,
        concurrency=1,
        client_factory=lambda selected: _fake_client(selected)[0],
        extractor=extractor,
    )

    assert report["status"] == "failed"
    assert report["failed_cases"] == len(corpus.cases)
    assert all(
        result["failure_code"] == "provider_call_budget_exhausted" for result in report["cases"]
    )
    assert "unreachable sensitive detail" not in str(report)


async def test_candidate_benchmark_reports_parse_and_schema_outcomes_separately():
    corpus = load_benchmark_corpus(CORPUS_PATH)
    candidate = _candidate()

    async def extractor(*args, **kwargs):
        raise ModelSchemaValidationError("sensitive invalid response")

    report = await benchmark_candidate(
        corpus,
        candidate,
        route_fingerprint="route:test",
        sync_profile_fingerprint="sync:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        relationship_vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        max_entities=25,
        max_relationships=25,
        maximum_provider_calls=1,
        concurrency=1,
        client_factory=lambda selected: _fake_client(selected)[0],
        extractor=extractor,
    )

    assert report["status"] == "failed"
    assert report["parse_success_cases"] == len(corpus.cases)
    assert report["schema_success_cases"] == 0
    assert report["structured_expectation_matches"] == 0
    assert report["relationship_quality"]["evidence_cases"] == 0
    assert all(result["parse_success"] is True for result in report["cases"])
    assert all(result["schema_success"] is False for result in report["cases"])
    assert "sensitive invalid response" not in str(report)


@pytest.mark.asyncio
async def test_cli_refuses_before_loading_corpus_or_resolving_credentials(capsys):
    touched = False

    def forbidden(*args):
        nonlocal touched
        touched = True
        raise AssertionError("must remain unused")

    args = Namespace(
        json=False,
        corpus=CORPUS_PATH,
        candidate="primary",
        concurrency=1,
        max_provider_calls=None,
        confirm="wrong",
    )

    result = await benchmark_graphiti.run(
        args,
        settings_resolver=forbidden,
        profile_resolver=forbidden,
        corpus_loader=forbidden,
    )

    assert result == 2
    assert touched is False
    assert benchmark_graphiti.BENCHMARK_CONFIRMATION in capsys.readouterr().err


@pytest.mark.asyncio
async def test_cli_can_compare_declared_candidates_without_exposing_secret(capsys):
    secret = "offline-openrouter-secret"
    settings = resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_REASONING_MODEL": "local/reasoning",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OPENROUTER_API_KEY": secret,
            "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "openrouter",
            "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "example/fallback",
        }
    )
    profile = GraphSyncExecutionProfile(
        sync_profile_fingerprint="sync:test",
        route_fingerprint=settings.graphiti_text_route.fingerprint,
        candidate_fingerprint=settings.graphiti_text_route.primary.fingerprint,
        embedding_profile_fingerprint=settings.graphiti_embedding_profile.fingerprint,
        provider="ollama",
        model="local/reasoning",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        max_entities=25,
        max_relationships=25,
    )
    seen = []

    async def runner(corpus, candidate, **kwargs):
        seen.append(candidate.connection.provider)
        return {
            "status": "passed",
            "provider": candidate.connection.provider,
            "requested_model": candidate.model,
            "case_count": len(corpus.cases),
            "schema_success_cases": len(corpus.cases),
            "entity_recall": 1.0,
            "relationship_recall": 1.0,
            "relationship_quality": {
                "accepted_of_proposed": 1.0,
            },
            "provider_calls": len(corpus.cases),
        }

    args = Namespace(
        json=False,
        corpus=CORPUS_PATH,
        candidate="all",
        concurrency=1,
        max_provider_calls=3,
        confirm=benchmark_graphiti.BENCHMARK_CONFIRMATION,
    )

    result = await benchmark_graphiti.run(
        args,
        settings_resolver=lambda: settings,
        profile_resolver=lambda: profile,
        benchmark_runner=runner,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert seen == ["ollama", "openrouter"]
    assert secret not in output


@pytest.mark.asyncio
async def test_arbitrary_route_candidate_builds_a_trackable_graphiti_client():
    candidate = _candidate()
    client = create_graphiti_llm_client(candidate)
    try:
        ProviderCallTracker.verify_client(client)
        assert client.model == candidate.model
    finally:
        await client.client.close()


def test_legacy_benchmark_is_inert_and_corpus_is_mounted_read_only():
    legacy = (PROJECT_ROOT / "scripts" / "benchmark_graphiti.sh").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "legacy state-mutating benchmark is disabled" in legacy
    assert "UPDATE episodes" not in legacy
    assert "docker exec" not in legacy
    assert "./benchmarks:/app/benchmarks:ro" in compose
    assert benchmark_graphiti.DEFAULT_CORPUS.name == "graphiti_extraction_v2.json"
