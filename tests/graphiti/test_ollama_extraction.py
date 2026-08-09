"""Test Graphiti entity extraction with Ollama."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.graphiti.ollama_config import get_graphiti_config_summary


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_entity_extraction(graphiti_client):
    """Test extracting entities from a test episode using Ollama."""
    # Show configuration
    config = get_graphiti_config_summary()
    print("\n🔧 Graphiti Configuration:")
    print(f"  Provider: {config['provider']}")
    print(f"  LLM Model: {config['llm_model']}")
    print(f"  Embedding Model: {config['embedding_model']}")
    print(f"  Embedding Dimension: {config['embedding_dim']}")

    graphiti = graphiti_client
    group_id = f"sage-test-ollama-{uuid4()}"

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
        reference_time=datetime.now(UTC),
        group_id=group_id,
    )

    print("✅ Episode added successfully!")

    # Query for extracted entities through Graphiti's supported driver API.
    results = await graphiti.driver.execute_query(
        """
            MATCH (e:Entity)
            WHERE e.group_id = $group_id
              AND (e.name CONTAINS 'Crystal'
                   OR e.name CONTAINS 'Thorgar'
                   OR e.name CONTAINS 'Nagburim'
                   OR e.name CONTAINS 'Dwarf')
            RETURN e.name as name, e.entity_type as type
            LIMIT 10
        """,
        params={"group_id": group_id},
    )

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
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "ollama")
    config_ollama = get_graphiti_config_summary()
    assert config_ollama["provider"] == "ollama"
    assert config_ollama["embedding_dim"] == 768  # nomic-embed-text

    # Test OpenAI (if API key is available)
    if os.getenv("OPENAI_API_KEY"):
        monkeypatch.delenv("GRAPHITI_EMBEDDING_MODEL", raising=False)
        monkeypatch.delenv("GRAPHITI_EMBEDDING_DIMENSIONS", raising=False)
        monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "openai")
        monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "openai")
        config_openai = get_graphiti_config_summary()
        assert config_openai["provider"] == "openai"
        assert config_openai["embedding_dim"] == 1536  # text-embedding-3-small

    print("\n✅ Provider switching validated")
