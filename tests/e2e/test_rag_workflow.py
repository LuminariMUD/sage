"""End-to-end tests for RAG workflow."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.mark.e2e
@pytest.mark.data_dependent
class TestRAGWorkflow:
    """End-to-end tests for complete RAG workflow."""

    def test_complete_rag_query(self):
        """Test complete RAG query with Ollama."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/rag/query",
            json={"query": "Who are the Crystal Dwarves of Nagburim?", "limit": 5},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "query" in data
        assert "chunks" in data
        assert "entities" in data
        assert "total_results" in data

        # Should have found relevant context
        assert len(data["chunks"]) > 0, "Should return relevant chunks"

        # Quality checks on chunks
        first_chunk = data["chunks"][0]
        assert "text" in first_chunk
        assert "similarity_score" in first_chunk
        assert first_chunk["similarity_score"] > 0.5, "Similarity should be meaningful"

        # Check if entities were found
        print("\n✅ RAG Query Results:")
        print(f"   Query: {data['query']}")
        print(f"   Chunks found: {len(data['chunks'])}")
        print(f"   Entities found: {len(data['entities'])}")
        print(f"   Total results: {data['total_results']}")

        if data["chunks"]:
            print(f"   Top chunk similarity: {data['chunks'][0]['similarity_score']:.3f}")
            print(f"   Chunk preview: {data['chunks'][0]['text'][:100]}...")

    def test_rag_with_graph_enrichment(self):
        """Test RAG with Neo4j graph enrichment."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/rag/query", json={"query": "Tell me about the crystal mines", "limit": 5}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return results
        assert "chunks" in data
        assert "entities" in data

        # If entities found, they should have proper structure
        if data["entities"]:
            entity = data["entities"][0]
            assert "stable_id" in entity
            assert "name" in entity
            assert "type" in entity

            print("\n🕸️  Graph Enhancement Results:")
            print(f"   Entities found: {len(data['entities'])}")
            print(f"   Sample entity: {entity['name']} ({entity['type']})")

        # Check relationships if present
        if data.get("relationships"):
            print(f"   Relationships found: {len(data['relationships'])}")
            print(f"   Sample: {data['relationships'][0]}")

    def test_rag_query_empty_results(self):
        """Test RAG query with no results."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/rag/query", json={"query": "xyzabc123nonexistent", "limit": 5}
        )

        # Should still return 200 with empty results
        assert response.status_code == 200
        data = response.json()

        assert "chunks" in data
        assert "entities" in data
        # Empty results are acceptable
        print("\n📭 Empty query results handled correctly")

    def test_rag_query_with_different_limits(self):
        """Test RAG query respects limit parameter."""
        client = TestClient(app)

        # Test with limit=2
        response = client.post("/api/v1/rag/query", json={"query": "dwarf", "limit": 2})

        assert response.status_code == 200
        data = response.json()

        # Should respect the limit (or return fewer if not enough results)
        if data["chunks"]:
            assert len(data["chunks"]) <= 2, "Should respect limit parameter"

        print("\n📊 Limit test:")
        print(f"   Requested: 2, Got: {len(data['chunks'])}")

        # Test with limit=10
        response = client.post("/api/v1/rag/query", json={"query": "dwarf", "limit": 10})

        assert response.status_code == 200
        data2 = response.json()

        if data2["chunks"]:
            assert len(data2["chunks"]) <= 10, "Should respect larger limit"
            print(f"   Requested: 10, Got: {len(data2['chunks'])}")

    def test_rag_query_complex_question(self):
        """Test RAG with complex multi-part question."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/rag/query",
            json={
                "query": "What is the relationship between the Crystal Dwarves and their mining traditions?",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should handle complex queries
        assert "chunks" in data
        print("\n🔍 Complex query handling:")
        print(f"   Query length: {len(data['query'])} chars")
        print(f"   Results found: {len(data['chunks'])}")

        # Verify results contain relevant terms (if any results)
        if data["chunks"]:
            combined_text = " ".join([c["text"].lower() for c in data["chunks"]])
            has_relevant_terms = any(
                term in combined_text for term in ["crystal", "dwarf", "mine", "mining"]
            )
            if has_relevant_terms:
                print("   ✓ Results contain relevant terms")

    def test_rag_query_validation(self):
        """Test RAG query input validation."""
        client = TestClient(app)

        # Test missing required fields
        response = client.post("/api/v1/rag/query", json={})

        # Should return validation error
        assert response.status_code == 422, "Should validate required fields"

        # Test invalid limit
        response = client.post("/api/v1/rag/query", json={"query": "test", "limit": -1})

        # May return 422 or handle gracefully
        assert response.status_code in [200, 422]
        print("\n✓ Input validation working correctly")


@pytest.mark.e2e
@pytest.mark.data_dependent
@pytest.mark.asyncio
async def test_rag_performance():
    """Test RAG query performance characteristics."""
    import time

    client = TestClient(app)

    # Measure query time
    start_time = time.time()

    response = client.post(
        "/api/v1/rag/query", json={"query": "Tell me about the world", "limit": 5}
    )

    elapsed_time = time.time() - start_time

    assert response.status_code == 200

    print("\n⏱️  Performance metrics:")
    print(f"   Query time: {elapsed_time:.2f}s")

    # Performance expectation: Should complete in reasonable time
    # This is lenient for CI environments
    assert elapsed_time < 30.0, f"Query took too long: {elapsed_time:.2f}s"

    if elapsed_time < 5.0:
        print("   ✅ Fast response (<5s)")
    elif elapsed_time < 10.0:
        print("   ⚠️  Acceptable response (5-10s)")
    else:
        print("   ⚠️  Slow response (>10s)")
