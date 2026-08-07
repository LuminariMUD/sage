"""
Enhanced Luminari Lore Chat Agent with Transparency.

Simplified architecture with GPT-4 handling complexity, but adds:
- Transparent tool usage display
- Source citations
- Entity tracking for context
- Streaming responses showing agent thinking
- Rich formatted responses with metadata
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import aiohttp
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from src.llm.pydantic_ai_factory import create_text_model
from src.security import public_error_message

logger = logging.getLogger(__name__)


class LoreSearchResult(BaseModel):
    """Result from lore search with rich metadata."""

    chunks: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    total_results: int


class StreamEvent(BaseModel):
    """Event for streaming responses."""

    type: str  # thinking, tool_use, content, source, entity_found, complete
    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Convert to SSE format."""
        event_data = {
            "type": self.type,
            "content": self.content,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
        return f"data: {json.dumps(event_data)}\n\n"


class EnhancedLoreChatAgent:
    """
    Enhanced chat agent with transparency and better UX.

    Keeps the simple architecture but adds visibility into:
    - What tools are being called
    - What sources are being used
    - What entities are found
    - How the answer is constructed
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        api_base_url: str = "http://localhost:8003",
    ):
        self.api_base_url = api_base_url

        # Track conversation context
        self.last_search_results: LoreSearchResult | None = None
        self.entities_mentioned: list[dict[str, Any]] = []
        self.sources_used: list[dict[str, Any]] = []

        # Create agent with enhanced prompt
        self.agent = Agent(
            create_text_model("tools", legacy_openai_api_key=openai_api_key),
            output_type=str,
            system_prompt=self._create_enhanced_prompt(),
            deps_type=EnhancedLoreChatAgent,
        )

        # Register the search tool
        self.agent.tool(self._search_lore)

        logger.info("✅ Enhanced Lore Chat Agent initialized")

    def _create_enhanced_prompt(self) -> str:
        """Create an enhanced system prompt with better tone and citation requirements."""
        return """You are the Luminari Sage, a knowledgeable and friendly guide to the rich fantasy world of Luminari MUD.

Your personality:
- Enthusiastic about the lore and eager to share knowledge
- Helpful and thorough in your explanations
- Professional but approachable in tone
- Always cite your sources when providing information

You have access to a comprehensive knowledge graph containing detailed lore about the world.

IMPORTANT RESPONSE FORMAT:
When answering questions, structure your response as follows:

1. **Direct Answer**: Start with a clear, concise answer to the question
2. **Detailed Explanation**: Provide rich context and details
3. **Key Entities**: Mention important entities found (deities, locations, characters, etc.)
4. **Relationships**: Highlight interesting connections between entities
5. **Sources**: List the specific episodes/documents you're drawing from

TOOL USAGE GUIDELINES:
- Use search_lore for ANY lore-related query
- You may call it multiple times to explore related topics
- The tool returns:
  - Text chunks with source information
  - Entities with their properties
  - Relationships with semantic attributes (alliance_type, strength, etc.)

CITATION FORMAT:
When citing sources, use this format:
- [Source: document_name, Episode X] for specific episodes
- [Entity: Name (Type)] when mentioning entities
- [Relationship: Entity1 -> Entity2 (type)] for connections

TONE GUIDELINES:
- Begin responses with engagement: "Ah, the Ages of Luminari!" or "Let me tell you about..."
- Use transitions like "Interestingly," "Furthermore," "It's worth noting that..."
- End with suggestions: "You might also be interested in..." or "Related topics include..."

Remember: You're not just a search engine - you're a sage who understands the deep connections and significance of the lore. Help users discover the rich tapestry of this fantasy world."""

    async def _search_lore(
        self, ctx: RunContext["EnhancedLoreChatAgent"], query: str, limit: int = 10
    ) -> LoreSearchResult:
        """
        Search the Luminari lore knowledge graph.

        This tool searches through episodes, entities, and relationships.
        Returns comprehensive results with source information.
        """
        try:
            headers = {"X-API-Key": os.getenv("SAGE_API_KEY", "")}

            # Log the search for transparency
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
                        result = LoreSearchResult(
                            chunks=data.get("chunks", []),
                            entities=data.get("entities", []),
                            relationships=data.get("relationships", []),
                            total_results=data.get("total_results", 0),
                        )

                        # Store for reference
                        ctx.deps.last_search_results = result

                        # Track entities and sources
                        ctx.deps.entities_mentioned.extend(result.entities)
                        for chunk in result.chunks:
                            source = {
                                "document_id": chunk.get("document_id"),
                                "chunk_id": chunk.get("chunk_id"),
                                "text_preview": chunk.get("text", "")[:100] + "...",
                            }
                            if source not in ctx.deps.sources_used:
                                ctx.deps.sources_used.append(source)

                        logger.info(
                            f"✅ Found {result.total_results} results with {len(result.entities)} entities"
                        )
                        return result
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
        Process a chat message with full response.

        Returns a formatted response with sources and entities.
        """
        try:
            # Clear tracking for new query
            self.entities_mentioned = []
            self.sources_used = []

            # Run the agent
            result = await self.agent.run(message, deps=self)

            # Format the response with metadata
            response = result.output

            # Add entity summary if any were found
            if self.entities_mentioned:
                response += "\n\n**📚 Key Entities Mentioned:**\n"
                seen = set()
                for entity in self.entities_mentioned[:10]:  # Limit to 10
                    entity_id = entity.get("stable_id", entity.get("id"))
                    if entity_id not in seen:
                        seen.add(entity_id)
                        response += (
                            f"- {entity.get('name', 'Unknown')} ({entity.get('type', 'Entity')})\n"
                        )

            # Add sources if any were used
            if self.sources_used:
                response += "\n\n**📖 Sources:**\n"
                for i, source in enumerate(self.sources_used[:5], 1):  # Limit to 5
                    response += f"{i}. Document {source['document_id'][:8]}...\n"

            return response

        except Exception as e:
            logger.error("Chat failed (%s)", type(e).__name__)
            return public_error_message("Chat")

    async def stream_chat(self, message: str) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream a chat response with transparency.

        Yields events showing what the agent is doing.
        """
        try:
            # Clear tracking
            self.entities_mentioned = []
            self.sources_used = []

            # Yield thinking event
            yield StreamEvent(type="thinking", content="Analyzing your question...")

            # Run the agent with streaming
            # Note: pydantic-ai doesn't support true streaming yet,
            # but we can simulate it by showing tool calls

            # For now, we'll run normally and then stream the response
            result = await self.agent.run(message, deps=self)

            # Check if tools were called (look at the message history). Tool activity lives
            # on message *parts* in pydantic-ai, and new_messages() is a method.
            if hasattr(result, "new_messages"):
                for msg in result.new_messages():
                    for part in getattr(msg, "parts", []):
                        if isinstance(part, ToolCallPart):
                            args = part.args if isinstance(part.args, dict) else {}
                            yield StreamEvent(
                                type="tool_use",
                                content=f"Searching for: {args.get('query', 'information')}",
                                data={"tool": part.tool_name, "args": args},
                            )
                        elif isinstance(part, ToolReturnPart):
                            if self.last_search_results:
                                yield StreamEvent(
                                    type="source",
                                    content=f"Found {self.last_search_results.total_results} results",
                                    data={
                                        "entities_found": len(self.last_search_results.entities),
                                        "chunks_found": len(self.last_search_results.chunks),
                                    },
                                )

            # Stream the main content
            content = result.output

            # Split into paragraphs for streaming
            paragraphs = content.split("\n\n")
            for paragraph in paragraphs:
                if paragraph.strip():
                    yield StreamEvent(type="content", content=paragraph)
                    await asyncio.sleep(0.1)  # Small delay for streaming effect

            # Send entity summary
            if self.entities_mentioned:
                entities_data = []
                seen = set()
                for entity in self.entities_mentioned[:10]:
                    entity_id = entity.get("stable_id", entity.get("id"))
                    if entity_id not in seen:
                        seen.add(entity_id)
                        entities_data.append(
                            {
                                "name": entity.get("name", "Unknown"),
                                "type": entity.get("type", "Entity"),
                            }
                        )

                yield StreamEvent(
                    type="entity_found",
                    content="Key entities identified",
                    data={"entities": entities_data},
                )

            # Send sources
            if self.sources_used:
                yield StreamEvent(
                    type="source",
                    content="Sources consulted",
                    data={"sources": self.sources_used[:5]},
                )

            # Send completion
            yield StreamEvent(type="complete", content="", data={"message_complete": True})

        except Exception as e:
            logger.error("Stream failed (%s)", type(e).__name__)
            yield StreamEvent(type="error", content=public_error_message("Chat stream"))


# Factory function
async def create_enhanced_agent(
    openai_api_key: str | None = None,
) -> EnhancedLoreChatAgent:
    """Create and initialize an enhanced lore chat agent."""
    return EnhancedLoreChatAgent(openai_api_key)


# Test function
async def test_enhanced_agent():
    """Test the enhanced agent."""
    agent = await create_enhanced_agent()

    # Test regular chat
    print("\n🔍 Testing: What are the ages of Luminari?")
    print("─" * 50)
    response = await agent.chat("What are the ages of Luminari?")
    print(response)

    # Test streaming
    print("\n\n🔍 Testing streaming: Tell me about Paladine")
    print("─" * 50)
    async for event in agent.stream_chat("Tell me about Paladine"):
        if event.type == "thinking":
            print(f"💭 {event.content}")
        elif event.type == "tool_use":
            print(f"🔧 {event.content}")
        elif event.type == "source":
            print(f"📚 {event.content}")
        elif event.type == "content":
            print(f"\n{event.content}")
        elif event.type == "entity_found":
            print(f"\n🏷️ {event.content}: {event.data}")
        elif event.type == "complete":
            print("\n✅ Complete")


if __name__ == "__main__":
    asyncio.run(test_enhanced_agent())
