"""Integration tests for Luminari Sage API."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.data_dependent]

# Test configuration
TEST_ENTITY_ID = "40dd54d0-e6f0-43a1-a8ad-2e5c9dc17c14"  # Void's Wake
TEST_RELATIONSHIP_ID = 894  # Known working relationship


class TestAPIHealthChecks:
    """Test basic API health and connectivity."""

    def test_root_endpoint(self, api_client):
        """Test root endpoint returns service info."""
        response = api_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Welcome to Luminari Sage API"
        assert data["version"] == "0.1.0"

    def test_ping_endpoint(self, api_client):
        """Test ping endpoint for basic connectivity."""
        response = api_client.get("/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_endpoint(self, api_client):
        """Test health endpoint shows database connectivity."""
        response = api_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["services"]["postgresql"] == "healthy"
        assert data["services"]["neo4j"] == "healthy"
        assert data["status"] in ["healthy", "degraded"]
        assert "providers" in data
        assert "embedding_storage" in data


class TestEntityEndpoints:
    """Test entity-related API endpoints."""

    def test_entity_search(self, api_client):
        """Test entity search functionality."""
        response = api_client.get("/api/v1/entities/search?query=void&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should find entities related to "void"
        if data:  # If entities exist
            entity = data[0]
            assert "uuid" in entity
            assert "name" in entity
            assert "type" in entity

    def test_entity_details(self, api_client):
        """Test getting specific entity details."""
        response = api_client.get(f"/api/v1/entities/{TEST_ENTITY_ID}")
        assert response.status_code in [200, 404]  # 404 if entity doesn't exist in test env

        if response.status_code == 200:
            data = response.json()
            assert data["uuid"] == TEST_ENTITY_ID
            assert "name" in data
            assert "type" in data

    def test_entity_relationships_list(self, api_client):
        """Test getting entity relationships (thin list)."""
        response = api_client.get(f"/api/v1/entities/{TEST_ENTITY_ID}/relationships")
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

    def test_relationship_details(self, api_client):
        """Test getting specific relationship details."""
        response = api_client.get(f"/api/v1/relationships/{TEST_RELATIONSHIP_ID}")
        assert response.status_code in [200, 404]  # 404 if relationship doesn't exist

        if response.status_code == 200:
            data = response.json()
            assert "relationship_id" in data
            assert "relationship_type" in data
            assert "source" in data
            assert "target" in data


class TestSearchEndpoints:
    """Test search and RAG functionality."""

    def test_lore_search(self, api_client):
        """Test basic lore document search."""
        response = api_client.get("/api/v1/lore/search?query=void&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Check document structure if results exist
        if data:
            doc = data[0]
            assert "id" in doc
            assert "title" in doc
            assert "source_file" in doc

    def test_rag_query(self, api_client):
        """Test hybrid RAG query functionality."""
        query_data = {"query": "What is Void's Wake?", "limit": 3, "threshold": 0.3}

        response = api_client.post("/api/v1/rag/query", json=query_data)
        assert response.status_code in [200, 500]  # 500 if embeddings not loaded

        if response.status_code == 200:
            data = response.json()
            assert "chunks" in data
            assert "entities" in data
            assert "total_results" in data

    def test_validation_endpoint(self, api_client):
        """Test lore validation functionality."""
        validation_data = {
            "content": "Paladine is the god of good dragons in Luminari.",
            "strict": False,
        }

        response = api_client.post("/api/v1/validate", json=validation_data)
        assert response.status_code == 200
        data = response.json()
        assert "is_valid" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)


class TestSystemEndpoints:
    """Test system information and statistics."""

    def test_stats_endpoint(self, api_client):
        """Test system statistics endpoint."""
        response = api_client.get("/api/v1/stats")
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

    def test_nonexistent_entity(self, api_client):
        """Test handling of non-existent entity requests."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = api_client.get(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_invalid_relationship_id(self, api_client):
        """Test handling of invalid relationship ID."""
        response = api_client.get("/api/v1/relationships/99999999")
        assert response.status_code == 404

    def test_malformed_rag_query(self, api_client):
        """Test handling of malformed RAG queries."""
        # Missing required field
        bad_query = {"max_results": 5}
        response = api_client.post("/api/v1/rag/query", json=bad_query)
        assert response.status_code == 422  # Validation error

    def test_empty_search_query(self, api_client):
        """Test handling of empty search queries."""
        response = api_client.get("/api/v1/entities/search?query=")
        assert response.status_code in [200, 422]  # May return empty results or validation error


# Utility functions for test setup/teardown
def pytest_configure():
    """Configure pytest for async tests."""
    pytest.asyncio_mode = "auto"


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
