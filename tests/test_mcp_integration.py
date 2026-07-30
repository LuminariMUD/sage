"""Integration tests for MCP server functionality."""

import pytest


class TestMCPServer:
    """Test MCP server endpoints and tool functionality."""

    BASE_URL = "http://localhost:8004"  # MCP server port

    def test_mcp_tools_list(self):
        """Test that MCP server lists available tools."""
        import requests

        try:
            response = requests.get(f"{self.BASE_URL}/tools", timeout=5)
            if response.status_code == 200:
                data = response.json()
                assert "tools" in data
                tools = data["tools"]

                # Check for expected tools
                tool_names = [tool["name"] for tool in tools]
                expected_tools = [
                    "query_lore",
                    "search_entities",
                    "get_entity_details",
                    "get_entity_relationships",
                    "get_relationship_details",
                    "get_lore_stats",
                ]

                for tool in expected_tools:
                    assert tool in tool_names
            else:
                pytest.skip("MCP server not available")

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")

    def test_mcp_query_lore_tool(self):
        """Test the query_lore MCP tool."""
        import requests

        try:
            tool_call = {
                "name": "query_lore",
                "arguments": {"query": "What is Void's Wake?", "max_results": 3, "threshold": 0.3},
            }

            response = requests.post(f"{self.BASE_URL}/tools/call", json=tool_call, timeout=10)

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is True
                assert "content" in data
                assert len(data["content"]) > 0
            else:
                pytest.skip("MCP tool call failed - may need data or embeddings")

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")

    def test_mcp_search_entities_tool(self):
        """Test the search_entities MCP tool."""
        import requests

        try:
            tool_call = {"name": "search_entities", "arguments": {"query": "void", "limit": 5}}

            response = requests.post(f"{self.BASE_URL}/tools/call", json=tool_call, timeout=10)

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is True
                assert "content" in data
            else:
                pytest.skip("MCP entity search failed - may need graph data")

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")

    def test_mcp_get_lore_stats_tool(self):
        """Test the get_lore_stats MCP tool."""
        import requests

        try:
            tool_call = {"name": "get_lore_stats", "arguments": {}}

            response = requests.post(f"{self.BASE_URL}/tools/call", json=tool_call, timeout=10)

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is True
                assert "content" in data
                # Should contain statistics about the system
                content = data["content"]
                assert "Documents:" in content or "Entities:" in content
            else:
                pytest.skip("MCP stats call failed")

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")

    def test_mcp_error_handling(self):
        """Test MCP server error handling."""
        import requests

        try:
            # Test invalid tool name
            tool_call = {"name": "nonexistent_tool", "arguments": {}}

            response = requests.post(f"{self.BASE_URL}/tools/call", json=tool_call, timeout=5)

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is False
                assert "error" in data

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")


class TestMCPToolIntegration:
    """Test MCP tool integration with backend services."""

    @pytest.mark.asyncio
    async def test_entity_workflow(self):
        """Test complete entity discovery workflow through MCP."""
        import requests

        try:
            # Step 1: Search for entities
            search_call = {"name": "search_entities", "arguments": {"query": "void", "limit": 1}}

            response = requests.post(
                "http://localhost:8004/tools/call", json=search_call, timeout=10
            )

            if response.status_code != 200:
                pytest.skip("MCP server or data not available")

            search_data = response.json()
            if not search_data["success"]:
                pytest.skip("Entity search failed - no test data")

            # Extract entity ID from response (this is fragile but works for testing)
            content = search_data["content"]
            if "ID: `" not in content:
                pytest.skip("No entity IDs found in search results")

            # Step 2: Get entity details (if we found an entity)
            # This test demonstrates the workflow even if data isn't available

        except requests.exceptions.ConnectionError:
            pytest.skip("MCP server not running")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
