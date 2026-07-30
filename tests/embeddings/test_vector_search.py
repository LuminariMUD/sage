"""Test vector search with Ollama embeddings."""

import pytest

from src.db import get_postgres_db
from src.llm.embeddings.factory import get_embedder


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_quality():
    """Test vector search returns relevant results."""
    embedder = get_embedder()
    db = await get_postgres_db()

    # Test query
    query = "crystal dwarves mining"
    query_embedding = await embedder.embed_text(query)

    # Search for similar episodes
    results = await db.fetch(
        """
        SELECT
            id,
            text,
            1 - (embedding <=> $1::vector) as similarity
        FROM episodes
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT 5
    """,
        "[" + ",".join(map(str, query_embedding)) + "]",
    )

    print(f"\nQuery: {query}")
    print(f"Found {len(results)} results\n")

    for i, result in enumerate(results, 1):
        print(f"{i}. Similarity: {result['similarity']:.3f}")
        print(f"   Text: {result['text'][:100]}...")
        print()

    # Quality checks
    assert len(results) > 0, "Should find at least one result"
    if results:
        assert results[0]["similarity"] > 0.5, "Top result should be relevant"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embedding_dimension_consistency():
    """Test all embeddings have correct dimension."""
    db = await get_postgres_db()
    embedder = get_embedder()

    results = await db.fetch("""
        SELECT array_length(embedding::float[], 1) as dim, COUNT(*) as count
        FROM episodes
        WHERE embedding IS NOT NULL
        GROUP BY dim
    """)

    print("\nEmbedding dimensions in database:")
    for row in results:
        print(f"  {row['dim']}d: {row['count']} episodes")

    # Should only have one dimension
    if len(results) > 0:
        assert len(results) == 1, "All embeddings should have the same dimension"
        assert (
            results[0]["dim"] == embedder.get_dimension()
        ), f"Database dimension {results[0]['dim']} should match embedder dimension {embedder.get_dimension()}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embedding_similarity_preservation():
    """Test that similar texts have similar embeddings."""
    embedder = get_embedder()

    texts = [
        "The crystal dwarves mine deep underground.",
        "Crystal dwarves are expert miners in underground caverns.",
        "Elves live in the forest and practice archery.",
    ]

    embeddings = await embedder.embed_batch(texts)

    # Calculate cosine similarities
    def cosine_similarity(a, b):
        import math

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot_product / (norm_a * norm_b)

    sim_01 = cosine_similarity(embeddings[0], embeddings[1])
    sim_02 = cosine_similarity(embeddings[0], embeddings[2])

    print(f"\nSimilarity between dwarf texts: {sim_01:.3f}")
    print(f"Similarity between dwarf and elf text: {sim_02:.3f}")

    # Similar texts should be more similar than dissimilar texts
    assert sim_01 > sim_02, "Similar texts should have higher similarity"
    assert sim_01 > 0.7, f"Similar texts should be quite similar (got {sim_01:.3f})"
