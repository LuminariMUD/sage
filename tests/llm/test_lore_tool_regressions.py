"""Regression tests for legacy lore tool payload handling."""

from typing import Any

import pytest

from src.agents.langchain import focused_tools
from src.agents.lore_chat_agent_streaming import (
    AgentDependencies,
    SearchData,
    StreamingLoreChatAgent,
)


@pytest.mark.asyncio
async def test_search_lore_reports_found_when_ranked_context_exists(monkeypatch) -> None:
    """A non-empty ranked chunk list must not be reported as an empty search."""

    class FakeRetrievalChain:
        async def ainvoke(self, _request: dict[str, str]) -> dict[str, Any]:
            return {
                "raw": {
                    "chunks": [{"text": "Canonical arcanite lore", "similarity": 0.9}],
                    "entities": [],
                    "relationships": [],
                    "metadata": {},
                }
            }

    monkeypatch.setattr(focused_tools, "RetrievalChain", FakeRetrievalChain)
    coroutine = focused_tools.search_lore.coroutine
    assert coroutine is not None

    result = await coroutine("arcanite")

    assert result["found"] is True
    assert result["context_blocks"] == ["Canonical arcanite lore"]


def test_streaming_follow_ups_use_dictionary_search_payloads() -> None:
    """Entity, relationship, and subgraph hints use the API's dictionary shape."""
    agent = object.__new__(StreamingLoreChatAgent)
    agent.deps = AgentDependencies(
        api_base_url="http://test.invalid",
        backend_api_key="test-only-key",
        search_data=SearchData(
            chunks=[{"text": "Arcanite marks the Luminari heroes."}],
            entities=[{"name": "Tal"}, {"name": "Dain"}],
            relationships=[{"metadata": {"fact": "Tal protects Dain"}}],
        ),
        used_subgraphs=[{"subgraph": {}, "scores": {}}],
    )

    follow_ups = agent._generate_follow_ups()

    assert "How are Tal and Dain connected?" in follow_ups
    assert "What do the relationship facts tell us about this topic?" in follow_ups
    assert "Explain the connections in the knowledge graph" in follow_ups
