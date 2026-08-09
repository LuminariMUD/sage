"""Shared lifecycle fixtures for live Graphiti integration tests."""

import os
from collections.abc import AsyncIterator

import pytest
from graphiti_core import Graphiti

from src.graphiti.ollama_config import (
    get_graphiti_embedding_client,
    get_graphiti_llm_client,
)


@pytest.fixture
async def graphiti_client() -> AsyncIterator[Graphiti]:
    """Create a Graphiti client and close both graph and LLM transports."""
    llm_client = get_graphiti_llm_client()
    graphiti = Graphiti(
        uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        llm_client=llm_client,
        embedder=get_graphiti_embedding_client(),
    )
    try:
        yield graphiti
    finally:
        await graphiti.close()
        await llm_client.client.close()
