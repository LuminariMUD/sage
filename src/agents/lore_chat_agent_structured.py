"""
Structured Luminari Lore Chat Agent - Uses structured output types for better formatting control.

Instead of having the LLM format everything, we use structured data and format it ourselves.
This gives us better control over the UI and allows us to properly display graph data.
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


class EntityMention(BaseModel):
    """An entity mentioned in the response."""

    name: str
    type: str
    description: str | None = None


class RelationshipMention(BaseModel):
    """A relationship mentioned in the response."""

    source: str
    target: str
    relationship_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ContentSection(BaseModel):
    """A section of content with a header and body."""

    header: str
    content: str
    entities: list[EntityMention] = Field(default_factory=list)
    relationships: list[RelationshipMention] = Field(default_factory=list)


class StructuredResponse(BaseModel):
    """Structured response from the agent that we'll format ourselves."""

    summary: str = Field(description="Brief one-sentence summary of the response")
    sections: list[ContentSection] = Field(description="Main content sections")
    key_entities: list[EntityMention] = Field(description="Important entities discussed")
    key_relationships: list[RelationshipMention] = Field(
        description="Important relationships discussed"
    )
    follow_up_questions: list[str] = Field(description="3-5 suggested follow-up questions")
    sources_referenced: list[str] = Field(
        default_factory=list, description="Source files or documents referenced"
    )


class SearchData(BaseModel):
    """Data from search results to inform the response."""

    chunks: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0


class AgentDependencies(BaseModel):
    """Dependencies for the agent."""

    api_base_url: str
    backend_api_key: str = Field(repr=False, exclude=True)
    # Track search data for the agent to use
    search_data: SearchData | None = None
    search_queries: list[str] = Field(default_factory=list)


class StructuredLoreChatAgent:
    """
    Structured chat agent that returns data for the UI to format.

    Key improvements:
    - Agent returns structured data, not formatted text
    - We handle all formatting in the streaming layer
    - Rich semantic properties from graph are properly utilized
    - RAG results are displayed with proper attribution
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        api_base_url: str = "http://localhost:8003",
    ):
        self.api_base_url = api_base_url

        # Get backend API key for internal calls

        backend_api_key = os.getenv("SAGE_API_KEY", "")

        # Debug logging
        logger.info("Initializing StructuredLoreChatAgent")
        logger.info("Internal lore API endpoint configured")

        # Create dependencies
        self.deps = AgentDependencies(
            api_base_url=api_base_url,
            backend_api_key=backend_api_key,
        )

        # Create agent with structured output
        self.agent = Agent(
            create_text_model("tools", legacy_openai_api_key=openai_api_key),
            deps_type=AgentDependencies,
            output_type=StructuredResponse,
            system_prompt=self._create_system_prompt(),
        )

        # Register the search tool
        @self.agent.tool
        async def search_lore(
            ctx: RunContext[AgentDependencies], query: str, limit: int = 10
        ) -> str:
            """
            Search the Luminari lore database for relevant information.

            Args:
                query: Natural language search query
                limit: Maximum number of results (default 10)

            Returns:
                Search results with entities, relationships, and text chunks
            """
            try:
                # Track the query
                ctx.deps.search_queries.append(query)

                # Call the GraphRAG endpoint
                headers = {"X-API-Key": ctx.deps.backend_api_key}

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{ctx.deps.api_base_url}/api/v1/rag/query",
                        json={
                            "query": query,
                            "limit": limit,
                            "include_entities": True,
                            "threshold": 0.7,
                        },
                        headers=headers,
                    ) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Store the search data for the agent to use
                            ctx.deps.search_data = SearchData(
                                chunks=data.get("chunks", []),
                                entities=data.get("entities", []),
                                relationships=data.get("relationships", []),
                                total_results=data.get("total_results", 0),
                            )

                            # Build a comprehensive summary for the LLM
                            summary_parts = []

                            # Add text chunks with sources
                            if data.get("chunks"):
                                summary_parts.append("RELEVANT TEXT EXCERPTS:")
                                for chunk in data["chunks"][:5]:
                                    source = chunk.get("metadata", {}).get("source_file", "Unknown")
                                    content = chunk.get("content", "")
                                    summary_parts.append(f"\nFrom {source}:\n{content}\n")

                            # Add entities with descriptions
                            if data.get("entities"):
                                summary_parts.append("\nKEY ENTITIES FOUND:")
                                for entity in data["entities"][:20]:
                                    name = entity.get("name", "Unknown")
                                    entity_type = entity.get("type", "Unknown")
                                    description = entity.get("description", "")
                                    summary_parts.append(
                                        f"- [{name}] (Type: {entity_type}): {description}"
                                    )

                            # Add relationships with ALL semantic properties
                            if data.get("relationships"):
                                summary_parts.append("\nRELATIONSHIPS AND CONNECTIONS:")
                                for rel in data["relationships"][:30]:
                                    source = rel.get("source", "Unknown")
                                    target = rel.get("target", "Unknown")
                                    rel_type = rel.get("type", "Unknown")
                                    target_name = rel.get("target_name", target)

                                    # Include ALL semantic properties
                                    props_str = ""
                                    if rel.get("metadata"):
                                        props = []
                                        for key, value in rel["metadata"].items():
                                            if key not in [
                                                "source",
                                                "target",
                                                "type",
                                                "target_name",
                                                "target_type",
                                                "strength",
                                            ]:
                                                props.append(f"{key}: {value}")
                                        if props:
                                            props_str = f" (Properties: {', '.join(props)})"

                                    summary_parts.append(
                                        f"- {source} --[{rel_type}]--> {target_name}{props_str}"
                                    )

                            return "\n".join(summary_parts)
                        else:
                            logger.error("RAG query returned status %s", response.status)
                            return public_error_message("Lore search")

            except aiohttp.ClientError as e:
                logger.error("HTTP client error (%s)", type(e).__name__)
                return public_error_message("Lore search")
            except Exception as e:
                logger.error("Unexpected search error (%s)", type(e).__name__)
                return public_error_message("Lore search")

    def _create_system_prompt(self) -> str:
        """Create system prompt for structured output."""
        return """You are the Luminari Sage, a knowledgeable guide to the fantasy world of Luminari MUD.

Your task is to provide comprehensive, detailed information about the world using the search results.

IMPORTANT INSTRUCTIONS:

1. USE THE SEARCH DATA: The search results contain rich information including:
   - Text excerpts from source documents
   - Entities with types and descriptions
   - Relationships with semantic properties (alliance_type, transformation_type, etc.)

2. BUILD COMPREHENSIVE RESPONSES:
   - Each section should have a meaningful header and detailed content
   - Reference specific entities and their types
   - Describe relationships using the semantic properties provided
   - Use information from the text chunks to provide context

3. STRUCTURE YOUR RESPONSE:
   - Summary: One clear sentence summarizing the main topic
   - Sections: Break down the information into logical sections with headers
   - Key Entities: List the most important entities discussed
   - Key Relationships: List the most important relationships with their properties
   - Follow-up Questions: Suggest 3-5 specific questions for deeper exploration

4. UTILIZE RELATIONSHIP PROPERTIES:
   When you see relationship properties like:
   - alliance_type: "mutual defense"
   - strength: 0.9
   - transformation_type: "corruption"
   - conflict_type: "ideological"
   Use these to enrich your descriptions!

5. BE SPECIFIC:
   - Don't say "various deities" - name them
   - Don't say "several ages" - list them with details
   - Don't say "important relationships" - describe them with their properties

Remember: The search tool provides rich data. Use ALL of it to create comprehensive, informative responses."""

    async def chat(self, message: str) -> StructuredResponse:
        """
        Process a chat message and return structured response.

        Args:
            message: User's question or message

        Returns:
            StructuredResponse with sections, entities, relationships, and follow-ups
        """
        # Clear previous search data
        self.deps.search_data = None
        self.deps.search_queries = []

        # Run the agent
        result = await self.agent.run(message, deps=self.deps)

        # Add sources from search
        if self.deps.search_data and self.deps.search_data.chunks:
            sources = set()
            for chunk in self.deps.search_data.chunks:
                if source := chunk.get("metadata", {}).get("source_file"):
                    sources.add(source)
            result.output.sources_referenced = list(sources)

        return result.output

    def format_response(self, response: StructuredResponse) -> str:
        """
        Format a structured response into rich markdown.

        Args:
            response: The structured response from the agent

        Returns:
            Formatted markdown string
        """
        parts = []

        # Add summary as an engaging introduction
        if response.summary:
            parts.append(f"_{response.summary}_\n")

        # Format each section
        for section in response.sections:
            parts.append(f"**{section.header}**\n")
            parts.append(f"{section.content}\n")

        # Add key entities if present
        if response.key_entities:
            parts.append("**📚 Key Entities Referenced**\n")
            for entity in response.key_entities:
                desc = f" - {entity.description}" if entity.description else ""
                parts.append(f"• [{entity.name}, {entity.type}]{desc}")
            parts.append("")

        # Add key relationships if present
        if response.key_relationships:
            parts.append("**🔗 Important Relationships**\n")
            for rel in response.key_relationships:
                props = ""
                if rel.properties:
                    prop_strs = [f"{k}: {v}" for k, v in rel.properties.items()]
                    props = f" ({', '.join(prop_strs)})"
                parts.append(f"• {rel.source} --[{rel.relationship_type}]--> {rel.target}{props}")
            parts.append("")

        # Add sources if present
        if response.sources_referenced:
            parts.append("**📖 Sources**\n")
            for source in response.sources_referenced:
                parts.append(f"• {source}")
            parts.append("")

        return "\n".join(parts)

    async def stream_chat(self, message: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream chat response using pydantic-ai's run_stream() for real-time updates.

        Yields SSE-formatted events as the agent processes.
        """
        try:
            # Show thinking status
            yield {
                "type": "status",
                "content": "Analyzing your question...",
                "timestamp": datetime.now().isoformat(),
            }

            # Clear previous data
            self.deps.search_data = None
            self.deps.search_queries = []

            # Use run_stream for real-time streaming
            async with self.agent.run_stream(message, deps=self.deps) as stream:
                # Stream partial structured outputs as they become available
                async for partial_response in stream:
                    # Check if this is a partial StructuredResponse
                    if hasattr(partial_response, "sections"):
                        # Stream sections as they're being built
                        for section in partial_response.sections:
                            if section.header and section.content:
                                yield {
                                    "type": "content_section",
                                    "header": section.header,
                                    "content": section.content,
                                    "timestamp": datetime.now().isoformat(),
                                }
                                await asyncio.sleep(0.01)  # Small delay for smooth streaming

                    # Stream summary if available
                    if hasattr(partial_response, "summary") and partial_response.summary:
                        yield {
                            "type": "summary",
                            "content": partial_response.summary,
                            "timestamp": datetime.now().isoformat(),
                        }

                # Get the final complete response
                response = await stream.get_final_response()

            # Show tool usage if searches were performed
            for query in self.deps.search_queries:
                yield {
                    "type": "tool_use",
                    "content": f"🔍 Searching: {query}",
                    "data": {"query": query, "tool": "search_lore"},
                    "timestamp": datetime.now().isoformat(),
                }
                await asyncio.sleep(0.1)

            # Show search results summary
            if self.deps.search_data:
                yield {
                    "type": "search_results",
                    "content": f"Found {len(self.deps.search_data.entities)} entities, {len(self.deps.search_data.relationships)} relationships, and {len(self.deps.search_data.chunks)} text excerpts",
                    "data": {
                        "entities": len(self.deps.search_data.entities),
                        "relationships": len(self.deps.search_data.relationships),
                        "chunks": len(self.deps.search_data.chunks),
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                await asyncio.sleep(0.1)

            # Stream the formatted response
            formatted = self.format_response(response)
            lines = formatted.split("\n")

            for line in lines:
                yield {"type": "content", "content": line, "timestamp": datetime.now().isoformat()}
                # Short delay for smooth streaming
                await asyncio.sleep(0.02)

            # Send follow-up questions as clickable suggestions
            if response.follow_up_questions:
                yield {
                    "type": "follow_up_questions",
                    "content": "You might also want to explore:",
                    "data": response.follow_up_questions,
                    "timestamp": datetime.now().isoformat(),
                }

            # Send completion
            yield {
                "type": "complete",
                "content": "Response complete",
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Stream error (%s)", type(e).__name__)

            yield {
                "type": "error",
                "content": public_error_message("Chat stream"),
                "timestamp": datetime.now().isoformat(),
            }
