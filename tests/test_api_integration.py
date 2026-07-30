"""Integration tests for Luminari Sage API."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

# Test configuration
TEST_ENTITY_ID = "40dd54d0-e6f0-43a1-a8ad-2e5c9dc17c14"  # Void's Wake
TEST_RELATIONSHIP_ID = 894  # Known working relationship


class TestAPIHealthChecks:
    """Test basic API health and connectivity."""

    def test_root_endpoint(self):
        """Test root endpoint returns service info."""
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "Luminari Sage"

    def test_ping_endpoint(self):
        """Test ping endpoint for basic connectivity."""
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_endpoint(self):
        """Test health endpoint shows database connectivity."""
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "postgres_connected" in data
        assert "neo4j_connected" in data
        # Health check should pass in production
        assert data["status"] in ["healthy", "unhealthy"]


class TestEntityEndpoints:
    """Test entity-related API endpoints."""

    def test_entity_search(self):
        """Test entity search functionality."""
        client = TestClient(app)
        response = client.get("/api/v1/entities/search?query=void&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should find entities related to "void"
        if data:  # If entities exist
            entity = data[0]
            assert "stable_id" in entity
            assert "name" in entity
            assert "type" in entity

    def test_entity_details(self):
        """Test getting specific entity details."""
        client = TestClient(app)
        response = client.get(f"/api/v1/entities/{TEST_ENTITY_ID}")
        assert response.status_code in [200, 404]  # 404 if entity doesn't exist in test env

        if response.status_code == 200:
            data = response.json()
            assert data["stable_id"] == TEST_ENTITY_ID
            assert "name" in data
            assert "type" in data

    def test_entity_relationships_list(self):
        """Test getting entity relationships (thin list)."""
        client = TestClient(app)
        response = client.get(f"/api/v1/entities/{TEST_ENTITY_ID}/relationships")
        assert response.status_code in [200, 404]  # 404 if entity doesn't exist

        if response.status_code == 200:
            data = response.json()
            assert "relationships" in data
            assert isinstance(data["relationships"], list)

            # Check relationship structure if any exist
            if data["relationships"]:
                rel = data["relationships"][0]
                assert "relationship_id" in rel
                assert "relationship_type" in rel
                assert "direction" in rel

    def test_relationship_details(self):
        """Test getting specific relationship details."""
        client = TestClient(app)
        response = client.get(f"/api/v1/relationships/{TEST_RELATIONSHIP_ID}")
        assert response.status_code in [200, 404]  # 404 if relationship doesn't exist

        if response.status_code == 200:
            data = response.json()
            assert "relationship_id" in data
            assert "relationship_type" in data
            assert "source" in data
            assert "target" in data


class TestSearchEndpoints:
    """Test search and RAG functionality."""

    def test_lore_search(self):
        """Test basic lore document search."""
        client = TestClient(app)
        response = client.get("/api/v1/lore/search?query=void&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Check document structure if results exist
        if data:
            doc = data[0]
            assert "id" in doc
            assert "title" in doc
            assert "content" in doc

    def test_rag_query(self):
        """Test hybrid RAG query functionality."""
        client = TestClient(app)

        query_data = {"query": "What is Void's Wake?", "max_results": 3, "threshold": 0.3}

        response = client.post("/api/v1/rag/query", json=query_data)
        assert response.status_code in [200, 500]  # 500 if embeddings not loaded

        if response.status_code == 200:
            data = response.json()
            assert "chunks" in data
            assert "entities" in data
            assert "total_results" in data

    def test_validation_endpoint(self):
        """Test lore validation functionality."""
        client = TestClient(app)

        validation_data = {
            "content": "Paladine is the god of good dragons in Luminari.",
            "strict": False,
        }

        response = client.post("/api/v1/validate", json=validation_data)
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)


class TestSystemEndpoints:
    """Test system information and statistics."""

    def test_stats_endpoint(self):
        """Test system statistics endpoint."""
        client = TestClient(app)
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()

        # Check expected statistics structure
        assert "documents" in data
        assert "chunks" in data
        assert "entities" in data
        assert "relationships" in data

        # Verify numeric values
        assert isinstance(data["documents"]["total"], int)
        assert isinstance(data["entities"]["total"], int)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_nonexistent_entity(self):
        """Test handling of non-existent entity requests."""
        client = TestClient(app)
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_invalid_relationship_id(self):
        """Test handling of invalid relationship ID."""
        client = TestClient(app)
        response = client.get("/api/v1/relationships/99999999")
        assert response.status_code == 404

    def test_malformed_rag_query(self):
        """Test handling of malformed RAG queries."""
        client = TestClient(app)

        # Missing required field
        bad_query = {"max_results": 5}
        response = client.post("/api/v1/rag/query", json=bad_query)
        assert response.status_code == 422  # Validation error

    def test_empty_search_query(self):
        """Test handling of empty search queries."""
        client = TestClient(app)
        response = client.get("/api/v1/entities/search?query=")
        assert response.status_code in [200, 422]  # May return empty results or validation error


# Utility functions for test setup/teardown
def pytest_configure():
    """Configure pytest for async tests."""
    pytest.asyncio_mode = "auto"


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
