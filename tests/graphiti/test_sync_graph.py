"""Fault-injection tests for idempotent Neo4j episode convergence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.graphiti.relationship_policy import (
    RELATIONSHIP_VOCABULARY_FINGERPRINT,
    RelationshipQualityReport,
)
from src.graphiti.sync_graph import (
    GraphIdentityConflictError,
    GraphitiEpisodeProcessor,
)
from src.graphiti.sync_models import JobLease
from src.graphiti.sync_profile import GraphSyncExecutionProfile


class InjectedCrash(RuntimeError):
    pass


class FakeDriver:
    def __init__(self):
        self.nodes: list[dict] = []
        self.crash_after_stamp = False

    async def verify_connectivity(self):
        return None

    async def execute_query(self, query, params=None):
        params = params or {}
        if "graph_sync:readiness" in query:
            ids = [node.get("stable_id") for node in self.nodes if node.get("stable_id")]
            duplicates = len(ids) - len(set(ids))
            return SimpleNamespace(records=[{"duplicate_stable_ids": duplicates}])
        candidates = self._candidates(params)
        if "graph_sync:inspect_episode" in query:
            stable_id = params["stable_id"]
            source_description = params["source_description"]
            source_fingerprint = params["source_fingerprint"]
            sync_profile = params["sync_profile_fingerprint"]
            embedding_profile = params["embedding_profile_fingerprint"]
            exact = [
                node
                for node in candidates
                if node.get("stable_id") == stable_id
                and node.get("source_description") == source_description
                and node.get("source_fingerprint") == source_fingerprint
                and node.get("sync_profile_fingerprint") == sync_profile
                and node.get("embedding_profile_fingerprint") == embedding_profile
            ]
            row = {
                "candidate_count": len(candidates),
                "native_uuid_count": sum(node.get("uuid") == stable_id for node in candidates),
                "stable_id_count": sum(node.get("stable_id") == stable_id for node in candidates),
                "source_description_count": sum(
                    node.get("source_description") == source_description for node in candidates
                ),
                "source_fingerprint_count": sum(
                    node.get("source_fingerprint") == source_fingerprint for node in candidates
                ),
                "sync_profile_fingerprint_count": sum(
                    node.get("sync_profile_fingerprint") == sync_profile for node in candidates
                ),
                "embedding_profile_fingerprint_count": sum(
                    node.get("embedding_profile_fingerprint") == embedding_profile
                    for node in candidates
                ),
                "exact_count": len(exact),
                "stable_id_conflict_count": sum(
                    node.get("stable_id") not in (None, stable_id) for node in candidates
                ),
                "candidate_content": candidates[0].get("content") if candidates else None,
            }
            return SimpleNamespace(records=[row])
        if "graph_sync:stamp_episode" in query:
            updated = 0
            if len(candidates) == 1:
                node = candidates[0]
                identity_is_safe = node.get("stable_id") in (None, params["stable_id"])
                metadata_is_safe = all(
                    node.get(key) in (None, params[key])
                    for key in (
                        "source_fingerprint",
                        "sync_profile_fingerprint",
                        "embedding_profile_fingerprint",
                    )
                )
                uuid_is_free = not any(
                    other is not node and other.get("uuid") == params["stable_id"]
                    for other in self.nodes
                )
                if (
                    identity_is_safe
                    and metadata_is_safe
                    and uuid_is_free
                    and node.get("content") == params["content"]
                ):
                    node.update(params)
                    node["uuid"] = params["stable_id"]
                    updated = 1
            if self.crash_after_stamp:
                self.crash_after_stamp = False
                raise InjectedCrash("after write, before verification")
            return SimpleNamespace(records=[{"updated_count": updated}])
        raise AssertionError("unexpected query")

    def _candidates(self, params):
        stable_id = params.get("stable_id")
        source_description = params.get("source_description")
        return [
            node
            for node in self.nodes
            if node.get("uuid") == stable_id
            or node.get("stable_id") == stable_id
            or node.get("source_description") == source_description
        ]


class FakeGraphitiCore:
    def __init__(self, driver):
        self.driver = driver
        self.add_calls = 0
        self.crash_before_write = False
        self.crash_after_write = False
        self.quality_report = None
        self.quality_report_key = None
        self.last_add_kwargs = None

    def consume_relationship_quality(self, episode_uuid):
        if self.quality_report_key is not None and episode_uuid != self.quality_report_key:
            return None
        report = self.quality_report
        self.quality_report = None
        self.quality_report_key = None
        return report

    async def add_episode(self, **kwargs):
        self.add_calls += 1
        self.last_add_kwargs = kwargs
        if self.crash_before_write:
            self.crash_before_write = False
            raise InjectedCrash("before graph write")
        created_uuid = kwargs.get("uuid") or str(uuid4())
        self.driver.nodes.append(
            {
                "uuid": created_uuid,
                "stable_id": None,
                "source_description": kwargs["source_description"],
                "content": kwargs["episode_body"],
                "source_fingerprint": None,
                "sync_profile_fingerprint": None,
                "embedding_profile_fingerprint": None,
            }
        )
        if self.crash_after_write:
            self.crash_after_write = False
            raise InjectedCrash("after graph write")
        if self.quality_report is not None:
            self.quality_report_key = created_uuid
        return SimpleNamespace(
            episode=SimpleNamespace(uuid=created_uuid),
            nodes=[object(), object()],
            edges=[object()],
        )


def _profile():
    return GraphSyncExecutionProfile(
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        candidate_fingerprint="candidate:test",
        embedding_profile_fingerprint="embedding:test",
        provider="ollama",
        model="qwen2.5:3b",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        max_entities=25,
        max_relationships=25,
    )


def _lease():
    episode_id = uuid4()
    now = datetime.now(UTC)
    return JobLease(
        episode_id=episode_id,
        attempt_id=uuid4(),
        run_id=uuid4(),
        lease_token=uuid4(),
        lease_owner="worker-a",
        attempt_number=1,
        budget_attempt_number=1,
        retry_generation=0,
        job_attempt_limit=3,
        provider_call_limit=10,
        retry_delay_seconds=60,
        captured_source_fingerprint="sha256:v1:test",
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        lease_expires_at=now + timedelta(minutes=15),
        text="A bounded piece of lore.",
        document_id=uuid4(),
        episode_index=3,
        created_at=now,
    )


def _processor():
    driver = FakeDriver()
    core = FakeGraphitiCore(driver)
    wrapper = SimpleNamespace(driver=driver, graphiti=core)
    return GraphitiEpisodeProcessor(wrapper, _profile()), driver, core


async def test_crash_before_write_retries_without_false_node_or_duplicate():
    processor, driver, core = _processor()
    lease = _lease()
    core.crash_before_write = True

    with pytest.raises(InjectedCrash):
        await processor.process(lease)
    assert driver.nodes == []

    result = await processor.process(lease)
    assert result.verification.is_exact
    assert len(driver.nodes) == 1
    assert core.add_calls == 2
    assert "uuid" not in core.last_add_kwargs


async def test_crash_after_write_recovers_by_native_uuid_without_second_provider_path():
    processor, driver, core = _processor()
    lease = _lease()
    core.crash_after_write = True

    with pytest.raises(InjectedCrash):
        await processor.process(lease)
    assert len(driver.nodes) == 1

    result = await processor.process(lease)
    assert result.reused_existing
    assert result.verification.native_uuid_count == 1
    assert len(driver.nodes) == 1
    assert core.add_calls == 1


async def test_crash_before_verification_recovers_exact_stamped_node():
    processor, driver, core = _processor()
    lease = _lease()
    driver.crash_after_stamp = True

    with pytest.raises(InjectedCrash):
        await processor.process(lease)
    assert len(driver.nodes) == 1

    result = await processor.process(lease)
    assert result.reused_existing
    assert result.verification.is_exact
    assert core.add_calls == 1


async def test_crash_after_verification_before_postgres_success_reuses_exact_node():
    processor, driver, core = _processor()
    lease = _lease()

    first = await processor.process(lease)
    assert first.verification.is_exact
    second = await processor.process(lease)

    assert second.reused_existing
    assert second.verification.is_exact
    assert len(driver.nodes) == 1
    assert core.add_calls == 1


async def test_legacy_node_is_adopted_only_when_content_and_identity_are_safe():
    processor, driver, core = _processor()
    lease = _lease()
    driver.nodes.append(
        {
            "uuid": str(uuid4()),
            "stable_id": str(lease.episode_id),
            "source_description": f"episode_{lease.episode_id}",
            "content": lease.text,
        }
    )

    result = await processor.process(lease)

    assert result.reused_existing
    assert result.verification.native_uuid_count == 1
    assert driver.nodes[0]["uuid"] == str(lease.episode_id)
    assert core.add_calls == 0


async def test_conflicting_content_is_never_relabelled_as_current():
    processor, driver, core = _processor()
    lease = _lease()
    driver.nodes.append(
        {
            "uuid": str(lease.episode_id),
            "stable_id": str(lease.episode_id),
            "source_description": f"episode_{lease.episode_id}",
            "content": "Different content",
        }
    )

    with pytest.raises(GraphIdentityConflictError, match="content conflicts"):
        await processor.process(lease)
    assert core.add_calls == 0


async def test_verified_success_uses_premaintenance_relationship_quality_counts():
    processor, _, core = _processor()
    lease = _lease()
    core.quality_report = RelationshipQualityReport(
        vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        proposed_edges=4,
        normalized_edges=1,
        accepted_edges=2,
        rejected_edges=2,
        rejected_unknown_type=1,
        rejected_missing_endpoint=1,
    ).with_maintenance(resolved_edges=2, new_edges=1, invalidated_edges=0)

    result = await processor.process(lease)

    assert result.graph_counts.proposed_edges == 4
    assert result.graph_counts.accepted_edges == 2
    assert result.graph_counts.rejected_edges == 2
    assert result.relationship_quality is not None
    assert result.relationship_quality.normalized_edges == 1
    assert core.quality_report is None
