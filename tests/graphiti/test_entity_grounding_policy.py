"""Tests for versioned literal entity grounding."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from graphiti_core import Graphiti

from src.graphiti.entity_grounding_policy import (
    EntityGroundingPolicyError,
    filter_entity_extraction_response,
    resolve_entity_grounding_policy,
)
from src.graphiti.policy_graphiti import (
    _CURRENT_EPISODE_TEXT,
    EntityGroundingLLMProxy,
    PolicyGraphiti,
)


def test_literal_policy_filters_prompt_examples_and_preserves_grounded_entities():
    filtered, report = filter_entity_extraction_response(
        {
            "extracted_entities": [
                {"name": "Crystal   Dwarves", "entity_type_id": 1},
                {"name": "AAN conference", "entity_type_id": 2},
                {"name": "", "entity_type_id": 0},
            ]
        },
        "The CRYSTAL\nDWARVES of Nagburim shaped arcanite.",
    )

    assert filtered["extracted_entities"] == [{"name": "Crystal   Dwarves", "entity_type_id": 1}]
    assert report.as_dict() == {
        "proposed": 3,
        "accepted": 1,
        "rejected_not_literal": 1,
        "rejected_empty_name": 1,
        "rejected": 2,
    }


@pytest.mark.parametrize("value", ["unknown", "literal-v1", 123])
def test_policy_resolution_fails_closed_for_unknown_modes(value):
    with pytest.raises(EntityGroundingPolicyError, match="unsupported"):
        resolve_entity_grounding_policy(value)


def test_policy_resolution_defaults_to_off():
    assert resolve_entity_grounding_policy(None) == "off"
    assert resolve_entity_grounding_policy(" LITERAL_V1 ") == "literal_v1"


def test_malformed_entity_response_fails_closed():
    with pytest.raises(EntityGroundingPolicyError, match="entity list"):
        filter_entity_extraction_response({}, "Canon")


async def test_proxy_filters_only_node_extraction_with_bound_episode_context():
    delegate = SimpleNamespace(
        generate_response=AsyncMock(
            return_value={
                "extracted_entities": [
                    {"name": "Lumia", "entity_type_id": 1},
                    {"name": "Dr. Amara Osei", "entity_type_id": 2},
                ]
            }
        )
    )
    proxy = EntityGroundingLLMProxy(delegate)
    token = _CURRENT_EPISODE_TEXT.set("The world of Lumia")
    try:
        filtered = await proxy.generate_response(prompt_name="extract_nodes.extract_text")
    finally:
        _CURRENT_EPISODE_TEXT.reset(token)

    assert [entity["name"] for entity in filtered["extracted_entities"]] == ["Lumia"]
    assert proxy.report is not None
    assert proxy.report.rejected == 1


async def test_proxy_leaves_non_entity_responses_unchanged():
    response = {"extracted_edges": [{"relation_type": "Protects"}]}
    delegate = SimpleNamespace(generate_response=AsyncMock(return_value=response))
    proxy = EntityGroundingLLMProxy(delegate)

    assert await proxy.generate_response(prompt_name="extract_edges.edge") is response


async def test_enabled_policy_exposes_one_content_free_report_by_episode(monkeypatch):
    delegate = SimpleNamespace(
        generate_response=AsyncMock(
            return_value={
                "extracted_entities": [
                    {"name": "Lumia", "entity_type_id": 1},
                    {"name": "AAN conference", "entity_type_id": 2},
                ]
            }
        )
    )
    proxy = EntityGroundingLLMProxy(delegate)
    graphiti = object.__new__(PolicyGraphiti)
    graphiti.entity_grounding_policy = "literal_v1"
    graphiti._entity_grounding_proxy = proxy
    graphiti._entity_grounding_quality = {}

    async def fake_add_episode(self, **kwargs):
        response = await self._entity_grounding_proxy.generate_response(
            prompt_name="extract_nodes.extract_text"
        )
        assert [entity["name"] for entity in response["extracted_entities"]] == ["Lumia"]
        return SimpleNamespace(episode=SimpleNamespace(uuid="episode-native-id"))

    monkeypatch.setattr(Graphiti, "add_episode", fake_add_episode)

    await graphiti.add_episode(episode_body="The world of Lumia")
    report = graphiti.consume_entity_grounding_quality("episode-native-id")

    assert report is not None
    assert report.as_dict() == {
        "proposed": 2,
        "accepted": 1,
        "rejected_not_literal": 1,
        "rejected_empty_name": 0,
        "rejected": 1,
    }
    assert graphiti.consume_entity_grounding_quality("episode-native-id") is None
