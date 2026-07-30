"""
Simplified Luminari Lore Chat Agent using pydantic-ai.

This agent lets GPT-4 do the heavy lifting for tool selection, context management,
and response synthesis. The architecture is intentionally simple:
- Single search tool that calls GraphRAG directly
- Let GPT-4 handle intent classification and tool choice
- Focus on good prompting rather than complex pre-processing
"""

import asyncio
import logging
import os
from typing import Any

import aiohttp
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from src.llm.pydantic_ai_factory import create_openai_chat_model
from src.security import public_error_message

logger = logging.getLogger(__name__)


class LoreSearchResult(BaseModel):
    """Result from lore search."""

    chunks: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    total_results: int


class SimpleLoreChatAgent:
    """
    Simplified chat agent that lets GPT-4 handle complexity.

    Architecture:
    - One tool: search_lore (calls GraphRAG endpoint)
    - GPT-4 decides when and how to use it
    - Focus on synthesis and accuracy
    """

    def __init__(self, openai_api_key: str, api_base_url: str = "http://localhost:8003"):
        self.api_base_url = api_base_url

        # Create the pydantic-ai agent with GPT-4
        self.agent = Agent(
            create_openai_chat_model(openai_api_key),
            output_type=str,  # Expect string responses
            system_prompt=self._create_system_prompt(),
            deps_type=SimpleLoreChatAgent,
        )

        # Register the search tool
        self.agent.tool(self._search_lore)

        logger.info("✅ Simplified Lore Chat Agent initialized")

    def _create_system_prompt(self) -> str:
        """Create the system prompt that guides GPT-4."""
        return """You are the Luminari Lore Expert, a knowledgeable guide to the rich fantasy world of Luminari MUD.

You have access to a comprehensive knowledge graph containing:
- Detailed lore about deities, locations, characters, organizations, artifacts
- Rich semantic relationships between entities
- Historical events, prophecies, and world-building details
- Episodes from lore documents with full context

TOOL USAGE:
- Use search_lore for ANY lore-related query
- The tool returns entities, relationships, and text chunks
- You can call it multiple times to explore related topics
- Results include semantic relationship properties (alliance_type, strength, etc.)

RESPONSE GUIDELINES:
1. **Accuracy First**: Only provide information from search results
2. **Rich Context**: Use entity relationships to provide deeper insights
3. **Cite Sources**: Reference specific episodes/documents when helpful
4. **Explore Connections**: Highlight interesting relationships between entities
5. **Encourage Discovery**: Suggest related topics users might find interesting

EXAMPLES:
- "What are the ages of Luminari?" → search for "ages timeline history"
- "Tell me about Paladine" → search "Paladine deity", then explore relationships
- "Knights of Luminari" → search "knights orders", examine each organization

Remember: You're not just searching - you're a knowledgeable guide helping users explore and understand this rich fantasy world. Use your intelligence to synthesize information and provide insights that go beyond simple facts."""

    async def _search_lore(
        self, ctx: RunContext["SimpleLoreChatAgent"], query: str, limit: int = 10
    ) -> LoreSearchResult:
        """
        Search the Luminari lore knowledge graph.

        Args:
            query: Search query (can be questions, entity names, or topics)
            limit: Maximum number of results to return (default: 10)

        Returns:
            Rich results with entities, relationships, and text chunks
        """
        try:
            headers = {"X-API-Key": os.getenv("SAGE_API_KEY", "")}

            # Call the GraphRAG endpoint directly
            async with aiohttp.ClientSession() as session:
                payload = {
                    "query": query,
                    "limit": limit,
                    "threshold": 0.1,
                    "include_entities": True,
                }

                async with session.post(
                    f"{ctx.deps.api_base_url}/api/v1/rag/query", json=payload, headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return LoreSearchResult(
                            chunks=data.get("chunks", []),
                            entities=data.get("entities", []),
                            relationships=data.get("relationships", []),
                            total_results=data.get("total_results", 0),
                        )
                    else:
                        logger.error("Lore API returned status %s", response.status)
                        return LoreSearchResult(
                            chunks=[], entities=[], relationships=[], total_results=0
                        )

        except Exception as e:
            logger.error("Search failed (%s)", type(e).__name__)
            return LoreSearchResult(chunks=[], entities=[], relationships=[], total_results=0)

    async def chat(self, message: str) -> str:
        """
        Process a chat message and return response.

        Args:
            message: User's message/question

        Returns:
            Agent's response
        """
        try:
            # Let GPT-4 handle everything - no pre-processing needed!
            result = await self.agent.run(message, deps=self)
            return result.output

        except Exception as e:
            logger.error("Chat failed (%s)", type(e).__name__)
            return public_error_message("Chat")

    async def stream_chat(self, message: str):
        """
        Stream a chat response (for future implementation).

        Args:
            message: User's message/question

        Yields:
            Response chunks as they're generated
        """
        # For now, just return the full response
        # Could be enhanced with pydantic-ai streaming in the future
        response = await self.chat(message)
        yield response


# Factory function for easy initialization
async def create_simple_agent(openai_api_key: str) -> SimpleLoreChatAgent:
    """Create and initialize a simple lore chat agent."""
    return SimpleLoreChatAgent(openai_api_key)


# Test the agent
async def test_simple_agent():
    """Test function to verify the agent works."""
    import os

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return

    agent = await create_simple_agent(api_key)

    test_queries = [
        "What are the ages of Luminari?",
        "Tell me about Paladine",
        "What are the Knights?",
        "Explain the Loom of Aether",
    ]

    for query in test_queries:
        print(f"\n🔍 Query: {query}")
        print("─" * 50)
        response = await agent.chat(query)
        print(response)
        print("═" * 50)


if __name__ == "__main__":
    asyncio.run(test_simple_agent())
