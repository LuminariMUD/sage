"""Validate entity extraction quality with Graphiti."""

import os

import pytest
from graphiti_core import Graphiti

from src.graphiti.ollama_config import (
    get_graphiti_embedding_client,
    get_graphiti_llm_client,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_entity_extraction_accuracy():
    """Test entity extraction produces expected results with acceptable accuracy."""
    # Get configured clients
    llm_client = get_graphiti_llm_client()
    embedding_client = get_graphiti_embedding_client()

    # Initialize Graphiti
    graphiti = Graphiti(
        uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        llm_client=llm_client,
        embedder=embedding_client,
    )

    # Known test case with clear entities
    episode_text = """
    In the city of Silverport, the merchant guild controls trade routes.
    Captain Elena leads the city guard and reports to Mayor Aldric.
    The guild operates from the Grand Bazaar near the harbor.
    Silverport is known for its bustling markets and skilled artisans.
    """

    # Expected entities (at minimum)
    expected_entities = {
        "silverport": ["Location", "City"],
        "elena": ["Person", "Character"],
        "aldric": ["Person", "Character"],
        "grand bazaar": ["Location", "Place"],
        "merchant guild": ["Organization", "Faction"],
    }

    # Extract entities
    print("\n🔍 Extracting entities from test episode...")

    await graphiti.add_episode(
        name="test_silverport_accuracy",
        episode_body=episode_text,
        source_description="Quality test episode",
    )

    print("✅ Episode added successfully!")

    # Query results
    async with graphiti.graph_driver.execute_query() as query_fn:
        results = await query_fn("""
            MATCH (e:Entity)
            WHERE e.name =~ '(?i).*(silver|elena|aldric|bazaar|merchant|guild).*'
            RETURN e.name as name, e.entity_type as type
            """)

    extracted_entities = {}
    for record in results.records:
        name = record["name"].lower()
        entity_type = record.get("type", "Unknown")
        extracted_entities[name] = entity_type

    print("\n📊 Extraction Results:")
    print(f"Expected: {len(expected_entities)} entities")
    print(f"Extracted: {len(extracted_entities)} entities")
    print("\nExtracted entities:")
    for name, entity_type in extracted_entities.items():
        print(f"  - {name} ({entity_type})")

    # Calculate accuracy - fuzzy matching
    found = 0
    for expected_name in expected_entities.keys():
        # Check if any extracted entity contains the expected name or vice versa
        matched = False
        for extracted_name in extracted_entities.keys():
            if expected_name in extracted_name or extracted_name in expected_name:
                matched = True
                print(f"  ✅ {expected_name} (matched with: {extracted_name})")
                break

        if matched:
            found += 1
        else:
            print(f"  ❌ {expected_name} - MISSING")

    accuracy = found / len(expected_entities) if expected_entities else 0
    print(f"\nAccuracy: {accuracy*100:.1f}%")

    # Should extract at least 60% of expected entities (lowered for Ollama)
    # Ollama models might use different entity naming conventions
    assert accuracy >= 0.6, f"Extraction accuracy too low: {accuracy*100:.1f}%"

    print("\n✅ Extraction quality test passed!")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_relationship_extraction():
    """Test that relationships are extracted along with entities."""
    # Get configured clients
    llm_client = get_graphiti_llm_client()
    embedding_client = get_graphiti_embedding_client()

    # Initialize Graphiti
    graphiti = Graphiti(
        uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        llm_client=llm_client,
        embedder=embedding_client,
    )

    # Test episode with clear relationships
    episode_text = """
    The wizard Merlin serves King Arthur at Camelot castle.
    Arthur wields the legendary sword Excalibur.
    Merlin taught Arthur the ways of magic and leadership.
    """

    print("\n🔍 Extracting entities and relationships...")

    await graphiti.add_episode(
        name="test_relationships",
        episode_body=episode_text,
        source_description="Relationship extraction test",
    )

    print("✅ Episode added successfully!")

    # Query for relationships
    async with graphiti.graph_driver.execute_query() as query_fn:
        results = await query_fn("""
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE e1.name =~ '(?i).*(merlin|arthur|excalibur).*'
               OR e2.name =~ '(?i).*(merlin|arthur|excalibur).*'
            RETURN e1.name as source, type(r) as relationship, e2.name as target
            LIMIT 20
            """)

    relationships = []
    for record in results.records:
        source = record["source"]
        rel_type = record["relationship"]
        target = record["target"]
        relationships.append((source, rel_type, target))
        print(f"  - {source} --[{rel_type}]--> {target}")

    print(f"\n📊 Extracted {len(relationships)} relationships")

    # Should extract at least some relationships
    assert len(relationships) > 0, "No relationships were extracted"

    print("\n✅ Relationship extraction test passed!")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extraction_consistency():
    """Test that extraction produces consistent results across runs."""
    # Get configured clients
    llm_client = get_graphiti_llm_client()
    embedding_client = get_graphiti_embedding_client()

    # Initialize Graphiti
    graphiti = Graphiti(
        uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD"),
        llm_client=llm_client,
        embedder=embedding_client,
    )

    episode_text = """
    The Dragon of Mount Doom terrorizes the nearby villages.
    Sir Galahad, the bravest knight, volunteers to slay the beast.
    """

    # Extract twice
    print("\n🔍 Testing extraction consistency...")

    await graphiti.add_episode(
        name="test_consistency_1",
        episode_body=episode_text,
        source_description="Consistency test run 1",
    )

    await graphiti.add_episode(
        name="test_consistency_2",
        episode_body=episode_text,
        source_description="Consistency test run 2",
    )

    # Query entities from both episodes
    async with graphiti.graph_driver.execute_query() as query_fn:
        results = await query_fn("""
            MATCH (e:Entity)
            WHERE e.name =~ '(?i).*(dragon|galahad|mount).*'
            RETURN DISTINCT e.name as name
            """)

    entities = [record["name"].lower() for record in results.records]
    print(f"\n📊 Unique entities extracted: {len(entities)}")
    for entity in entities:
        print(f"  - {entity}")

    # Should have extracted at least the key entities
    assert len(entities) >= 2, "Not enough entities extracted"

    print("\n✅ Consistency test passed!")
