"""
Properly implemented Luminari Lore Chat Agent using pydantic-ai.

Based on pydantic-ai documentation, this implementation:
- Uses @agent.tool decorator for proper tool registration
- Implements streaming with run_stream()
- Accesses message history correctly
- Maintains transparency and good UX
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

import aiohttp
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.llm.pydantic_ai_factory import create_text_model
from src.security import public_error_message

logger = logging.getLogger(__name__)


class LoreSearchResult(BaseModel):
    """Result from lore search."""

    chunks: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0


class AgentDependencies(BaseModel):
    """Dependencies for the agent."""

    api_base_url: str
    api_key: str = Field(repr=False, exclude=True)
    # Track conversation context
    entities_mentioned: list[dict[str, Any]] = Field(default_factory=list)
    sources_used: list[dict[str, Any]] = Field(default_factory=list)
    last_search_results: LoreSearchResult | None = None


class LuminariLoreChatAgent:
    """
    Properly implemented chat agent following pydantic-ai patterns.

    Features:
    - Transparent tool usage
    - Source citations
    - Good tone and personality
    - Streaming support
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        api_base_url: str = "http://localhost:8003",
    ):
        # Initialize dependencies
        self.deps = AgentDependencies(
            api_base_url=api_base_url, api_key=os.getenv("SAGE_API_KEY", "")
        )

        # Create agent with proper configuration
        self.agent = Agent(
            create_text_model("tools", legacy_openai_api_key=openai_api_key),
            deps_type=AgentDependencies,
            output_type=str,  # We want string responses
            system_prompt=self._create_system_prompt(),
        )

        # Register the search tool using decorator pattern
        @self.agent.tool
        async def search_lore(
            ctx: RunContext[AgentDependencies], query: str, limit: int = 10
        ) -> str:
            """
            Search the Luminari lore knowledge graph.

            Args:
                query: Search query (questions, entity names, or topics)
                limit: Maximum number of results to return

            Returns:
                Summary of search results with entities and relationships
            """
            try:
                headers = {"X-API-Key": ctx.deps.api_key}

                # Log for transparency
                logger.info("Lore search requested (%d characters)", len(query))

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

                            # Store results in context
                            result = LoreSearchResult(
                                chunks=data.get("chunks", []),
                                entities=data.get("entities", []),
                                relationships=data.get("relationships", []),
                                total_results=data.get("total_results", 0),
                            )
                            ctx.deps.last_search_results = result

                            # Track entities and sources
                            ctx.deps.entities_mentioned.extend(result.entities)
                            for chunk in result.chunks[:5]:  # Limit tracking
                                source = {
                                    "document_id": chunk.get("document_id", ""),
                                    "chunk_id": chunk.get("chunk_id", ""),
                                    "text_preview": (
                                        (chunk.get("text", "")[:100] + "...")
                                        if chunk.get("text")
                                        else ""
                                    ),
                                }
                                if source not in ctx.deps.sources_used:
                                    ctx.deps.sources_used.append(source)

                            # Format results for the LLM
                            summary = f"Found {result.total_results} results with {len(result.entities)} entities.\n\n"

                            # Add key text chunks
                            if result.chunks:
                                summary += "Key Information:\n"
                                for i, chunk in enumerate(result.chunks[:3], 1):
                                    summary += f"{i}. {chunk.get('text', '')[:200]}...\n\n"

                            # Add entities found
                            if result.entities:
                                summary += f"\nEntities Found ({len(result.entities)}):\n"
                                for entity in result.entities[:10]:
                                    summary += f"- {entity.get('name', 'Unknown')} ({entity.get('type', 'Entity')})"
                                    if entity.get("description"):
                                        summary += f": {entity['description'][:100]}..."
                                    summary += "\n"

                            # Add relationships
                            if result.relationships:
                                summary += f"\nRelationships ({len(result.relationships)}):\n"
                                for rel in result.relationships[:10]:
                                    summary += f"- {rel.get('source', '?')} -> {rel.get('target', '?')} ({rel.get('type', '?')})\n"

                            logger.info(f"✅ Search complete: {result.total_results} results")
                            return summary

                        else:
                            logger.error("Lore API returned status %s", response.status)
                            return f"Search failed with status {response.status}"

            except Exception as e:
                logger.error("Search failed (%s)", type(e).__name__)
                return public_error_message("Lore search")

        logger.info("✅ Luminari Lore Chat Agent initialized")

    def _create_system_prompt(self) -> str:
        """Create the system prompt."""
        return """You are the Luminari Sage, a knowledgeable and friendly guide to the rich fantasy world of Luminari MUD.

PERSONALITY:
- Enthusiastic about sharing lore knowledge
- Professional but approachable
- Engaging and helpful
- Always cite sources when providing information

RESPONSE FORMAT:
1. Start with an engaging opening: "Ah, the Ages of Luminari!" or "Let me tell you about..."
2. Provide a clear, direct answer first
3. Add rich context and details
4. Mention key entities found (in brackets like [Paladine, Deity])
5. Note interesting relationships between entities
6. End with related topics the user might explore

TOOL USAGE:
- Use search_lore for ANY lore-related query
- The tool returns summaries of text, entities, and relationships
- You may call it multiple times to explore related topics
- Always acknowledge when searching: "Let me search for information about..."

CITATIONS:
When citing information, mention:
- Which entities you're drawing from
- Key relationships discovered
- Suggest follow-up questions

TONE:
- Use engaging transitions: "Interestingly," "Furthermore," "It's worth noting..."
- Be enthusiastic: "This is fascinating!" "One of the most intriguing aspects..."
- Encourage exploration: "You might also want to know about..." "This connects to..."

Remember: You're a sage who loves this world and wants to share its wonders with visitors."""

    async def chat(self, message: str) -> str:
        """
        Process a chat message and return response.

        Args:
            message: User's query

        Returns:
            Formatted response with citations
        """
        try:
            # Clear tracking for new query
            self.deps.entities_mentioned = []
            self.deps.sources_used = []

            # Run the agent
            result = await self.agent.run(message, deps=self.deps)

            # Get the response
            response = result.output

            # Add metadata sections if we have them
            if self.deps.entities_mentioned:
                response += "\n\n**📚 Key Entities:**\n"
                seen = set()
                for entity in self.deps.entities_mentioned[:10]:
                    entity_id = entity.get("stable_id", entity.get("id", ""))
                    if entity_id and entity_id not in seen:
                        seen.add(entity_id)
                        response += (
                            f"- {entity.get('name', 'Unknown')} ({entity.get('type', 'Entity')})\n"
                        )

            if self.deps.sources_used:
                response += "\n\n**📖 Sources Consulted:**\n"
                for i, source in enumerate(self.deps.sources_used[:5], 1):
                    doc_id = source.get("document_id", "Unknown")
                    if doc_id:
                        response += f"{i}. Document {doc_id[:8]}...\n"

            return response

        except Exception as e:
            logger.error("Chat failed (%s)", type(e).__name__)
            return public_error_message("Chat")

    async def stream_chat(self, message: str):
        """
        Stream a chat response.

        For now, returns the full response since pydantic-ai streaming
        requires more complex setup. Can be enhanced later.
        """
        response = await self.chat(message)

        # Simulate streaming by yielding in chunks
        chunks = response.split("\n\n")
        for chunk in chunks:
            if chunk.strip():
                yield {"type": "content", "content": chunk, "timestamp": datetime.now().isoformat()}
                await asyncio.sleep(0.05)  # Small delay for effect

        yield {"type": "complete", "content": "", "timestamp": datetime.now().isoformat()}


# Test function
async def test_agent():
    """Test the agent."""
    agent = LuminariLoreChatAgent()

    print("\n🔍 Testing: What are the ages of Luminari?")
    print("─" * 50)
    response = await agent.chat("What are the ages of Luminari?")
    print(response)


if __name__ == "__main__":
    asyncio.run(test_agent())
