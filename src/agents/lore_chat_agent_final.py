"""
Final Luminari Lore Chat Agent - Simple architecture with excellent UX.

Combines:
- Simple single-tool architecture (GPT-4 handles complexity)
- Rich formatting and UI from original agent
- Tool call transparency
- Proper streaming with status updates
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
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
    # Track for rich display
    entities_mentioned: list[dict[str, Any]] = Field(default_factory=list)
    sources_used: list[dict[str, Any]] = Field(default_factory=list)
    relationships_found: list[dict[str, Any]] = Field(default_factory=list)
    last_search_query: str = ""
    tools_called: list[dict[str, Any]] = Field(default_factory=list)


class FinalLoreChatAgent:
    """
    Final implementation with simple architecture and rich UI.

    Features:
    - Single search tool (GPT-4 decides usage)
    - Rich formatted responses
    - Tool call transparency
    - Suggested follow-up questions
    - Proper citations and sources
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

        # Create agent
        self.agent = Agent(
            create_text_model("tools", legacy_openai_api_key=openai_api_key),
            deps_type=AgentDependencies,
            output_type=str,
            system_prompt=self._create_system_prompt(),
        )

        # Register the search tool
        @self.agent.tool
        async def search_lore(
            ctx: RunContext[AgentDependencies], query: str, limit: int = 10
        ) -> str:
            """
            Search the Luminari lore knowledge graph.

            Returns comprehensive results including text chunks, entities, and relationships.
            """
            # Track the tool call
            ctx.deps.last_search_query = query
            ctx.deps.tools_called.append(
                {"tool": "search_lore", "query": query, "timestamp": datetime.now().isoformat()}
            )

            try:
                headers = {"X-API-Key": ctx.deps.api_key}

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

                            # Track for rich display
                            ctx.deps.entities_mentioned.extend(result.entities)
                            ctx.deps.relationships_found.extend(result.relationships)

                            # Track sources
                            for chunk in result.chunks:
                                source = {
                                    "document_id": chunk.get("document_id", ""),
                                    "chunk_id": chunk.get("chunk_id", ""),
                                    "similarity": chunk.get("similarity", 0),
                                    "text_preview": (
                                        chunk.get("text", "")[:200] + "..."
                                        if chunk.get("text")
                                        else ""
                                    ),
                                }
                                ctx.deps.sources_used.append(source)

                            # Return formatted for LLM
                            summary = f"Found {result.total_results} results.\n\n"

                            if result.chunks:
                                summary += "=== KEY INFORMATION ===\n"
                                for i, chunk in enumerate(result.chunks[:5], 1):
                                    summary += f"\n[{i}] {chunk.get('text', '')[:300]}...\n"

                            if result.entities:
                                summary += f"\n=== ENTITIES ({len(result.entities)}) ===\n"
                                for entity in result.entities[:15]:
                                    name = entity.get("name", "Unknown")
                                    etype = entity.get("type", "Entity")
                                    desc = entity.get("description", "")
                                    summary += f"• {name} [{etype}]"
                                    if desc:
                                        summary += f": {desc[:100]}..."
                                    summary += "\n"

                            if result.relationships:
                                summary += (
                                    f"\n=== RELATIONSHIPS ({len(result.relationships)}) ===\n"
                                )
                                for rel in result.relationships[:15]:
                                    source = rel.get("source_name", rel.get("source", "?"))
                                    target = rel.get("target_name", rel.get("target", "?"))
                                    rel_type = rel.get("type", "relates_to")
                                    summary += f"• {source} → {target} [{rel_type}]\n"

                                    # Include semantic properties if available
                                    if rel.get("metadata"):
                                        for key, value in rel["metadata"].items():
                                            if key not in ["source", "target", "type"] and value:
                                                summary += f"  - {key}: {value}\n"

                            return summary

                        else:
                            logger.error("Lore API returned status %s", response.status)
                            return f"Search failed (status {response.status})"

            except Exception as e:
                logger.error("Search error (%s)", type(e).__name__)
                return public_error_message("Lore search")

        logger.info("✅ Final Lore Chat Agent initialized")

    def _create_system_prompt(self) -> str:
        """Create system prompt with formatting instructions."""
        return """You are the Luminari Sage, a knowledgeable guide to the fantasy world of Luminari MUD.

CRITICAL FORMATTING RULES:
- NEVER use numbered lists (1. 2. 3.) - they break markdown
- Use **bold headers** followed by description paragraphs instead
- Use • for bullet points when listing items
- Add blank lines between major sections

RESPONSE STRUCTURE:

Start with an engaging hook:
"Ah, the Ages of Luminari! This world's history spans magnificent epochs, each marking profound transformations in the fabric of reality itself."

Then provide rich, detailed content organized by bold headers:

**The First Age - The Awakening**
Description paragraph here with rich details. Explain what happened, who was involved, and why it matters. Make it engaging and informative.

**The Second Age - The Sundering**
Another rich paragraph with specific details from the search results. Include key events, important figures, and the consequences of this age.

For lists, use bullet points:
• Key event one with brief description
• Key event two with context
• Key event three with implications

IMPORTANT CONTENT GUIDELINES:
- Provide COMPREHENSIVE information, not brief overviews
- Include specific details from search results
- Explain the significance and connections between elements
- Use entity markers: [Paladine, Deity] when first mentioning entities
- Describe relationships: "X opposes Y" or "A created B"
- Make responses substantive - at least 3-4 solid paragraphs

QUALITY STANDARDS:
- Each age/topic should have a full paragraph of description
- Include specific events, names, and consequences
- Explain WHY things matter, not just WHAT they are
- Connect different elements to show the bigger picture
- Draw from the search results to provide accurate, detailed information

TONE:
- Enthusiastic: "This is particularly fascinating because..."
- Knowledgeable: "According to the ancient records..."
- Engaging: "What makes this remarkable is..."
- Helpful: "To fully understand this, it helps to know..."

End with specific, contextual suggestions based on what was discussed.

Remember: Users want DEPTH and DETAIL, not summaries. Give them the rich lore they're seeking."""

    async def chat(self, message: str) -> str:
        """
        Process a chat message with rich formatting.

        Returns a formatted response with all UI elements.
        """
        try:
            # Clear tracking for new query
            self.deps.entities_mentioned = []
            self.deps.sources_used = []
            self.deps.relationships_found = []
            self.deps.tools_called = []

            # Run the agent
            result = await self.agent.run(message, deps=self.deps)

            # Get the main response
            response = result.output

            # Add graph information section if we have it
            if self.deps.entities_mentioned or self.deps.relationships_found:
                response += "\n\n---\n\n### 📊 **Knowledge Graph Information**\n\n"

                if self.deps.entities_mentioned:
                    # Deduplicate entities
                    seen = set()
                    unique_entities = []
                    for entity in self.deps.entities_mentioned:
                        entity_id = entity.get(
                            "stable_id", entity.get("id", entity.get("name", ""))
                        )
                        if entity_id and entity_id not in seen:
                            seen.add(entity_id)
                            unique_entities.append(entity)

                    response += "**Entities Found:**\n"
                    for entity in unique_entities[:10]:
                        name = entity.get("name", "Unknown")
                        etype = entity.get("type", "Entity")
                        response += f"• [{name}]({name.replace(' ', '_')}) *({etype})*\n"
                    response += "\n"

                if self.deps.relationships_found:
                    response += "**Key Relationships:**\n"
                    for rel in self.deps.relationships_found[:8]:
                        source = rel.get("source_name", rel.get("source", "?"))
                        target = rel.get("target_name", rel.get("target", "?"))
                        rel_type = rel.get("type", "relates_to")
                        response += f"• {source} → {target} *({rel_type})*\n"
                    response += "\n"

            # Add sources section
            if self.deps.sources_used:
                response += "\n---\n\n### 📚 **Sources**\n\n"
                # Group by document
                docs = {}
                for source in self.deps.sources_used:
                    doc_id = source.get("document_id", "Unknown")
                    if doc_id not in docs:
                        docs[doc_id] = []
                    docs[doc_id].append(source)

                for i, (doc_id, sources) in enumerate(docs.items(), 1):
                    if doc_id:
                        response += f"{i}. Document `{doc_id[:12]}...` "
                        response += (
                            f"({len(sources)} relevant section{'s' if len(sources) > 1 else ''})\n"
                        )

            # Add suggested follow-up questions
            response += "\n---\n\n### 💡 **Explore Further**\n\n"

            # Generate contextual suggestions based on what was found
            suggestions = []

            # Based on entities found
            for entity in self.deps.entities_mentioned[:3]:
                name = entity.get("name")
                if name:
                    suggestions.append(f"Tell me more about {name}")

            # Based on relationships
            if self.deps.relationships_found:
                suggestions.append("What relationships exist between these entities?")

            # Default suggestions if needed
            if len(suggestions) < 3:
                if "ages" in message.lower():
                    suggestions.extend(
                        [
                            "What happened during the Age of Dragons?",
                            "Tell me about the cataclysms",
                            "Who are the Luminari?",
                        ]
                    )
                elif "knight" in message.lower():
                    suggestions.extend(
                        [
                            "What are the different knight orders?",
                            "Tell me about the Knights of Solamnia",
                            "What deities do the knights serve?",
                        ]
                    )

            # Format as clickable
            for suggestion in suggestions[:4]:
                response += f"• [{suggestion}](#{suggestion.replace(' ', '_')})\n"

            return response

        except Exception as e:
            logger.error("Chat error (%s)", type(e).__name__)
            return public_error_message("Chat")

    async def stream_chat(self, message: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream chat response line-by-line for better UX.
        """
        try:
            # Clear tracking
            self.deps.entities_mentioned = []
            self.deps.sources_used = []
            self.deps.relationships_found = []
            self.deps.tools_called = []

            # Initial thinking event
            yield {
                "type": "thinking",
                "content": "Analyzing your question...",
                "timestamp": datetime.now().isoformat(),
            }
            await asyncio.sleep(0.3)

            # Run the agent (this is where the actual API call happens)
            result = await self.agent.run(message, deps=self.deps)

            # Show tool calls immediately after they happen
            for tool_call in self.deps.tools_called:
                yield {
                    "type": "tool_use",
                    "content": f"🔍 Searching for: {tool_call['query']}",
                    "data": tool_call,
                    "timestamp": datetime.now().isoformat(),
                }
                await asyncio.sleep(0.2)

                # Show results found
                yield {
                    "type": "tool_result",
                    "content": f"Found {len(self.deps.entities_mentioned)} entities and {len(self.deps.sources_used)} sources",
                    "timestamp": datetime.now().isoformat(),
                }
                await asyncio.sleep(0.2)

            # Stream the main content LINE BY LINE for immediate display
            response = result.output

            # Split by lines first to stream more granularly
            lines = response.split("\n")
            current_paragraph = []

            for line in lines:
                if line.strip():
                    # Send each line immediately
                    yield {
                        "type": "content",
                        "content": line,
                        "timestamp": datetime.now().isoformat(),
                    }
                    # Very short delay for smooth streaming
                    await asyncio.sleep(0.02)
                elif current_paragraph:
                    # Empty line means paragraph break
                    yield {
                        "type": "content",
                        "content": "",  # Send empty line for paragraph break
                        "timestamp": datetime.now().isoformat(),
                    }
                    await asyncio.sleep(0.02)
                    current_paragraph = []

            # Send completion
            yield {
                "type": "complete",
                "content": "",
                "data": {
                    "entities_count": len(self.deps.entities_mentioned),
                    "sources_count": len(self.deps.sources_used),
                    "tools_used": len(self.deps.tools_called),
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Stream error (%s)", type(e).__name__)
            yield {
                "type": "error",
                "content": public_error_message("Chat stream"),
                "timestamp": datetime.now().isoformat(),
            }


# Test function
async def test_agent():
    """Test the final agent."""
    agent = FinalLoreChatAgent()

    print("\n🔍 Testing: What are the ages of Luminari?")
    print("═" * 60)
    response = await agent.chat("What are the ages of Luminari?")
    print(response)
    print("═" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent())
