"""Test Graphiti entity extraction with Ollama."""

import os

import pytest
from graphiti_core import Graphiti

from src.graphiti.ollama_config import (
    get_graphiti_config_summary,
    get_graphiti_embedding_client,
    get_graphiti_llm_client,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_entity_extraction():
    """Test extracting entities from a test episode using Ollama."""
    # Get configured clients
    llm_client = get_graphiti_llm_client(verbose=True)
    embedding_client = get_graphiti_embedding_client(verbose=True)

    # Show configuration
    config = get_graphiti_config_summary()
    print("\n🔧 Graphiti Configuration:")
    print(f"  Provider: {config['provider']}")
    print(f"  LLM Model: {config['llm_model']}")
    print(f"  Embedding Model: {config['embedding_model']}")
    print(f"  Embedding Dimension: {config['embedding_dim']}")

    # Initialize Graphiti
    graphiti = Graphiti(
        uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        llm_client=llm_client,
        embedder=embedding_client,
    )

    # Test episode with rich fantasy lore content
    episode_text = """
    The Crystal Dwarves of Nagburim are master craftsmen who live deep
    beneath the mountains. Their leader, King Thorgar, oversees the mining
    operations in the Great Crystal Cavern. The dwarves use magical crystals
    to power their forges and create legendary weapons. They are known
    throughout the realm for their skill in working with rare metals and gems.
    """

    # Extract entities
    print("\n🔍 Extracting entities from test episode...")

    await graphiti.add_episode(
        name="test_crystal_dwarves",
        episode_body=episode_text,
        source_description="Test episode for entity extraction",
    )

    print("✅ Episode added successfully!")

    # Query for extracted entities
    # Use the Neo4j driver from Graphiti's graph_driver
    async with graphiti.graph_driver.execute_query() as query_fn:
        results = await query_fn("""
            MATCH (e:Entity)
            WHERE e.name CONTAINS 'Crystal'
               OR e.name CONTAINS 'Thorgar'
               OR e.name CONTAINS 'Nagburim'
               OR e.name CONTAINS 'Dwarf'
            RETURN e.name as name, e.entity_type as type
            LIMIT 10
            """)

    print(f"\n✅ Extracted {len(results.records)} entities:")
    entities = []
    for record in results.records:
        entity_name = record["name"]
        entity_type = record.get("type", "Unknown")
        print(f"  - {entity_name} ({entity_type})")
        entities.append(entity_name.lower())

    # Validation
    assert len(results.records) > 0, "No entities were extracted"

    # Should extract at least some key entities
    assert any(
        "crystal" in name or "dwarf" in name or "thorgar" in name or "nagburim" in name
        for name in entities
    ), "Key entities were not extracted"

    print("\n✅ Test passed! Ollama successfully extracted entities.")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graphiti_config_summary():
    """Test that config summary returns expected structure."""
    config = get_graphiti_config_summary()

    # Validate structure
    assert "provider" in config
    assert "llm_model" in config
    assert "embedding_model" in config
    assert "embedding_dim" in config
    assert "temperature" in config

    # Validate values
    assert config["provider"] in ["ollama", "openai"]
    assert isinstance(config["embedding_dim"], int)
    assert config["embedding_dim"] > 0
    assert 0.0 <= config["temperature"] <= 1.0

    print(f"\n✅ Config summary validated: {config}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_switch_providers(monkeypatch):
    """Test switching between Ollama and OpenAI providers."""
    # Test Ollama
    monkeypatch.setenv("GRAPHITI_PROVIDER", "ollama")
    config_ollama = get_graphiti_config_summary()
    assert config_ollama["provider"] == "ollama"
    assert config_ollama["embedding_dim"] == 768  # nomic-embed-text

    # Test OpenAI (if API key is available)
    if os.getenv("OPENAI_API_KEY"):
        monkeypatch.setenv("GRAPHITI_PROVIDER", "openai")
        config_openai = get_graphiti_config_summary()
        assert config_openai["provider"] == "openai"
        assert config_openai["embedding_dim"] == 1536  # text-embedding-3-small

    print("\n✅ Provider switching validated")
