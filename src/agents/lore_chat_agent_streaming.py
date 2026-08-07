"""
Streaming Luminari Lore Chat Agent - Properly implements pydantic-ai streaming.

Uses run_stream() and event handlers for real-time updates.
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


class StreamingResponse(BaseModel):
    """Response that can be streamed incrementally."""

    content: str = Field(description="The main response content")
    entities_mentioned: list[str] = Field(
        default_factory=list, description="Entities mentioned so far"
    )
    follow_up_questions: list[str] = Field(
        default_factory=list, description="Suggested follow-up questions"
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
    tools_called: list[dict[str, Any]] = Field(default_factory=list)

    # Track response construction metadata
    used_episodes: list[dict[str, Any]] = Field(
        default_factory=list
    )  # Episodes actually referenced
    used_entities: list[dict[str, Any]] = Field(default_factory=list)  # Entities incorporated
    used_relationships: list[dict[str, Any]] = Field(default_factory=list)  # Relationships used
    used_subgraphs: list[dict[str, Any]] = Field(
        default_factory=list
    )  # Subgraphs identified and scored
    search_strategy: str = ""  # Reasoning for search terms chosen
    decision_points: list[str] = Field(default_factory=list)  # Key decisions made
    graph_contribution: float = 0.0  # Percentage from graph vs text
    response_text: str = ""  # Store the generated response for analysis


class StreamingLoreChatAgent:
    """
    Streaming chat agent with proper pydantic-ai streaming implementation.

    Key features:
    - Uses run_stream() for real-time streaming
    - Event stream handler for intermediate events
    - Properly formatted SSE output
    - Tool call transparency during streaming
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
        logger.info("Initializing StreamingLoreChatAgent")
        logger.info("Internal lore API endpoint configured")

        # Create dependencies
        self.deps = AgentDependencies(
            api_base_url=api_base_url,
            backend_api_key=backend_api_key,
        )

        # Create agent with simpler output for streaming
        self.agent = Agent(
            create_text_model("tools", legacy_openai_api_key=openai_api_key),
            deps_type=AgentDependencies,
            output_type=str,  # Simple string output for easier streaming
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
                # Track the query and tool call
                ctx.deps.search_queries.append(query)
                ctx.deps.tools_called.append(
                    {"tool": "search_lore", "query": query, "timestamp": datetime.now().isoformat()}
                )

                # Record search strategy
                ctx.deps.search_strategy = (
                    f"Searching for '{query}' with limit {limit} to answer user's question"
                )
                ctx.deps.decision_points.append(f"Initiated search with query: '{query}'")

                # Call the GraphRAG endpoint
                headers = {"X-API-Key": ctx.deps.backend_api_key}

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{ctx.deps.api_base_url}/api/v1/rag/query",
                        json={
                            "query": query,
                            "limit": limit,
                            "include_entities": True,
                            "threshold": 0.1,
                        },
                        headers=headers,
                    ) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Store the search data for reference
                            ctx.deps.search_data = SearchData(
                                chunks=data.get("chunks", []),
                                entities=data.get("entities", []),
                                relationships=data.get("relationships", []),
                                total_results=data.get("total_results", 0),
                            )

                            # Track what we found
                            ctx.deps.decision_points.append(
                                f"Found {len(data.get('chunks', []))} text episodes, "
                                f"{len(data.get('entities', []))} entities, "
                                f"{len(data.get('relationships', []))} relationships"
                            )

                            # Extract subgraph information if available
                            subgraph_summary = ""
                            if data.get("metadata") and data["metadata"].get("subgraph_analysis"):
                                subgraph_info = data["metadata"]["subgraph_analysis"]
                                ctx.deps.decision_points.append(
                                    f"Found {subgraph_info['total_subgraphs']} connected subgraphs"
                                )

                                if subgraph_info.get("ranked_subgraphs"):
                                    # Track all ranked subgraphs
                                    for sg_data in subgraph_info["ranked_subgraphs"]:
                                        ctx.deps.used_subgraphs.append(
                                            {
                                                "subgraph": sg_data.get("subgraph", {}),
                                                "scores": sg_data.get("scores", {}),
                                            }
                                        )

                                    top_subgraph = subgraph_info["ranked_subgraphs"][0]
                                    subgraph_summary = f"\nGRAPH STRUCTURE: Primary subgraph (score: {top_subgraph['total_score']:.2f}) contains {top_subgraph['num_nodes']} entities and {top_subgraph['num_edges']} relationships. "
                                    subgraph_summary += f"Relevance: {top_subgraph['semantic_relevance']:.2f}, Connectivity: {top_subgraph['connectivity']:.2f}\n"

                            # Build a comprehensive summary for the LLM
                            summary_parts = []

                            if subgraph_summary:
                                summary_parts.append(subgraph_summary)

                            # Add text chunks with sources
                            if data.get("chunks"):
                                summary_parts.append("RELEVANT TEXT EXCERPTS:")
                                for i, chunk in enumerate(data["chunks"][:5], 1):
                                    chunk_id = chunk.get("chunk_id", "Unknown")
                                    document_id = chunk.get("document_id", "Unknown")
                                    content = chunk.get("text", "")
                                    similarity = chunk.get("similarity", 0)

                                    # Track this episode as potentially used
                                    ctx.deps.used_episodes.append(
                                        {
                                            "episode_id": chunk_id,
                                            "document_id": document_id,
                                            "similarity": similarity,
                                            "rank": i,
                                            "contribution": "TBD",  # Will be analyzed later
                                        }
                                    )

                                    summary_parts.append(
                                        f"\n[Episode {i}] (ID: {chunk_id[:8]}..., Doc: {document_id[:8]}..., Similarity: {similarity:.3f}):\n{content}\n"
                                    )

                            # Add entities with descriptions
                            if data.get("entities"):
                                summary_parts.append("\nKEY ENTITIES FOUND:")
                                for entity in data["entities"][:20]:
                                    name = entity.get("name", "Unknown")
                                    entity_type = entity.get("type", "Unknown")
                                    description = entity.get("description", "")

                                    # Track entities
                                    ctx.deps.used_entities.append(
                                        {"name": name, "type": entity_type, "from_graph": True}
                                    )

                                    summary_parts.append(
                                        f"- [{name}] (Type: {entity_type}): {description}"
                                    )

                            # Add relationships with ALL semantic properties
                            if data.get("relationships"):
                                summary_parts.append("\nRELATIONSHIPS AND CONNECTIONS:")
                                # No limit on relationships since we're limiting episodes instead
                                for rel in data["relationships"]:
                                    source = rel.get("source", "Unknown")
                                    target = rel.get("target", "Unknown")
                                    rel_type = rel.get("type", "Unknown")
                                    target_name = rel.get("target_name", target)

                                    # Track relationships
                                    ctx.deps.used_relationships.append(
                                        {
                                            "source": source,
                                            "target": target_name,
                                            "type": rel_type,
                                            "from_graph": True,
                                        }
                                    )

                                    # Include semantic properties (safety filter for embeddings)
                                    props_str = ""
                                    if rel.get("metadata"):
                                        props = []
                                        for key, value in rel["metadata"].items():
                                            # Skip standard fields and embeddings (belt-and-suspenders)
                                            if (
                                                key
                                                not in [
                                                    "source",
                                                    "target",
                                                    "type",
                                                    "target_name",
                                                    "target_type",
                                                    "strength",
                                                ]
                                                and not key.endswith("_embedding")
                                                and key != "fact_embedding"
                                            ):
                                                # Truncate very long values
                                                value_str = (
                                                    str(value)[:100]
                                                    if len(str(value)) > 100
                                                    else str(value)
                                                )
                                                props.append(f"{key}: {value_str}")
                                        if props:
                                            props_str = f" (Properties: {', '.join(props)})"

                                    summary_parts.append(
                                        f"- {source} --[{rel_type}]--> {target_name}{props_str}"
                                    )

                            return "\n".join(summary_parts)
                        else:
                            logger.error("RAG query returned status %s", response.status)
                            return f"Search failed: Status {response.status}"

            except Exception as e:
                logger.error("Search error (%s)", type(e).__name__)
                return public_error_message("Lore search")

    def _analyze_response_construction(
        self, response_text: str, deps: AgentDependencies
    ) -> dict[str, Any]:
        """Analyze how the response was constructed from search results."""
        analysis = {
            "search_strategy": deps.search_strategy or "No search performed",
            "primary_sources": [],
            "graph_enhancement": {
                "entities_used": [],
                "relationships_leveraged": [],
                "subgraphs_identified": [],
                "graph_contribution_percent": 0,
                "text_contribution_percent": 100,
                "subgraph_contribution_percent": 0,
            },
            "decision_points": deps.decision_points,
            "construction_process": [],
        }

        # Analyze which episodes contributed most
        if deps.used_episodes:
            for episode in deps.used_episodes[:5]:  # Top 5 episodes
                # Check if episode content appears to be referenced in response
                contribution = "Low"
                if episode["similarity"] > 0.8:
                    contribution = "High - Primary source"
                elif episode["similarity"] > 0.6:
                    contribution = "Medium - Supporting context"

                analysis["primary_sources"].append(
                    {
                        "episode_id": episode["episode_id"],
                        "similarity": episode["similarity"],
                        "rank": episode["rank"],
                        "contribution": contribution,
                    }
                )

            analysis["construction_process"].append(
                f"Prioritized {len(deps.used_episodes)} episodes based on similarity scores"
            )

        # Analyze entity usage
        if deps.used_entities:
            # Extract unique entity names that were actually mentioned
            entity_mentions = []
            for entity in deps.used_entities:
                if entity["name"].lower() in response_text.lower():
                    entity_mentions.append(f"{entity['name']} ({entity['type']})")

            analysis["graph_enhancement"]["entities_used"] = entity_mentions
            analysis["construction_process"].append(
                f"Incorporated {len(entity_mentions)} entities from graph database"
            )

        # Analyze relationship usage
        if deps.used_relationships:
            # Track which relationships were leveraged
            rel_mentions = []
            for rel in deps.used_relationships[:10]:  # Top 10 relationships
                rel_str = f"{rel['source']} --[{rel['type']}]--> {rel['target']}"
                rel_mentions.append(rel_str)

            analysis["graph_enhancement"]["relationships_leveraged"] = rel_mentions
            analysis["construction_process"].append(
                f"Leveraged {len(rel_mentions)} relationships from graph"
            )

        # Analyze subgraph contributions
        if hasattr(deps, "used_subgraphs") and deps.used_subgraphs:
            subgraph_info = []
            for idx, subgraph_data in enumerate(deps.used_subgraphs[:3], 1):  # Top 3 subgraphs
                subgraph = subgraph_data.get("subgraph", {})
                scores = subgraph_data.get("scores", {})

                # Extract key entities in this subgraph
                key_entities = []
                for node in subgraph.get("nodes", [])[:5]:  # Top 5 nodes
                    key_entities.append(node.get("name", "Unknown"))

                subgraph_info.append(
                    {
                        "rank": idx,
                        "size": len(subgraph.get("nodes", [])),
                        "edges": len(subgraph.get("edges", [])),
                        "total_score": round(scores.get("total_score", 0), 3),
                        "semantic_relevance": round(scores.get("semantic_relevance", 0), 3),
                        "connectivity": round(scores.get("connectivity", 0), 3),
                        "key_entities": key_entities,
                    }
                )

            analysis["graph_enhancement"]["subgraphs_identified"] = subgraph_info
            analysis["construction_process"].append(
                f"Identified {len(deps.used_subgraphs)} connected subgraphs, using top {min(3, len(deps.used_subgraphs))} by relevance"
            )

        # Calculate contribution percentages with subgraph awareness
        has_graph_data = bool(deps.used_entities or deps.used_relationships)
        has_text_data = bool(deps.used_episodes)
        has_subgraph_data = bool(hasattr(deps, "used_subgraphs") and deps.used_subgraphs)

        if has_graph_data and has_text_data:
            # Estimate based on presence of entities/relationships/subgraphs
            graph_weight = len(deps.used_entities) * 2 + len(deps.used_relationships) * 3
            text_weight = len(deps.used_episodes) * 10
            subgraph_weight = 0

            if has_subgraph_data:
                # Subgraphs contribute significantly when present
                subgraph_weight = sum(
                    sg.get("scores", {}).get("total_score", 0) * 20
                    for sg in deps.used_subgraphs[:3]
                )

            total_weight = graph_weight + text_weight + subgraph_weight

            if total_weight > 0:
                analysis["graph_enhancement"]["graph_contribution_percent"] = int(
                    (graph_weight / total_weight) * 100
                )
                analysis["graph_enhancement"]["text_contribution_percent"] = int(
                    (text_weight / total_weight) * 100
                )
                analysis["graph_enhancement"]["subgraph_contribution_percent"] = int(
                    (subgraph_weight / total_weight) * 100
                )
        elif has_graph_data:
            if has_subgraph_data:
                # Split between graph and subgraph
                analysis["graph_enhancement"]["graph_contribution_percent"] = 60
                analysis["graph_enhancement"]["subgraph_contribution_percent"] = 40
            else:
                analysis["graph_enhancement"]["graph_contribution_percent"] = 100
            analysis["graph_enhancement"]["text_contribution_percent"] = 0

        # Add final summary
        if has_graph_data or has_subgraph_data:
            contrib_parts = []
            if analysis["graph_enhancement"]["text_contribution_percent"] > 0:
                contrib_parts.append(
                    f"{analysis['graph_enhancement']['text_contribution_percent']}% text"
                )
            if analysis["graph_enhancement"]["graph_contribution_percent"] > 0:
                contrib_parts.append(
                    f"{analysis['graph_enhancement']['graph_contribution_percent']}% graph"
                )
            if analysis["graph_enhancement"]["subgraph_contribution_percent"] > 0:
                contrib_parts.append(
                    f"{analysis['graph_enhancement']['subgraph_contribution_percent']}% subgraph structure"
                )

            analysis["construction_process"].append(
                f"Response composition: {', '.join(contrib_parts)}"
            )
        else:
            analysis["construction_process"].append(
                "Response based entirely on text search results"
            )

        return analysis

    def _create_system_prompt(self) -> str:
        """Create system prompt for streaming output."""
        return """You are the Luminari Sage, a knowledgeable guide to the fantasy world of Luminari MUD.

CRITICAL: You MUST use the search_lore tool for EVERY question about Luminari. Do not attempt to answer without searching first.

MANDATORY WORKFLOW:
1. ALWAYS call search_lore with relevant keywords for the user's question
2. Use the search results to provide detailed, specific answers
3. If search returns no results, acknowledge this and ask for clarification

WHEN TO SEARCH:
- Questions about ages, history, timeline → search_lore("ages of luminari") or search_lore("age of vigil age of marking")
- Questions about deities → search_lore("deities gods pantheon")
- Questions about locations → search_lore("geography locations realms")
- Questions about characters → search_lore("character name mentioned")
- ANY question about Luminari lore → Use the EXACT terms from the user's question when possible
- ALWAYS search first with specific terms from the question, then try broader terms if needed

NEVER say "I don't have information" or "let me gather information" without actually calling search_lore.

RESPONSE FORMAT after searching:
- Use specific names, dates, and details from the search results
- Quote exact text from sources when available
- Include entity markers like [Paladine, Deity]
- Describe relationships with their semantic properties
- Reference source files when mentioned

If the search finds information, provide comprehensive details. If the search finds nothing, say so explicitly and suggest related topics that might have information."""

    async def stream_chat(self, message: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream chat response using pydantic-ai's streaming capabilities.

        Yields SSE-formatted events as the agent processes.
        """
        try:
            # Show initial status
            yield {
                "type": "status",
                "content": "🔮 Consulting the archives...",
                "timestamp": datetime.now().isoformat(),
            }
            await asyncio.sleep(0.1)

            # Clear previous data
            self.deps.search_data = None
            self.deps.search_queries = []
            self.deps.tools_called = []

            # Event handler to capture intermediate events
            async def event_handler(event_type: str, event_data: Any):
                """Handle intermediate events during streaming."""
                if event_type == "tool_call":
                    yield {
                        "type": "tool_use",
                        "content": f"🔍 Searching: {event_data.get('query', 'lore database')}",
                        "data": event_data,
                        "timestamp": datetime.now().isoformat(),
                    }
                elif event_type == "model_response":
                    # This would be partial model responses
                    pass

            # Use run_stream for real-time streaming
            previous_text = ""
            async with self.agent.run_stream(message, deps=self.deps) as stream:
                # Stream text as it's generated by the LLM
                async for full_text in stream.stream_text():
                    if full_text and len(full_text) > len(previous_text):
                        # Only send the new text that was added
                        new_text = full_text[len(previous_text) :]
                        previous_text = full_text

                        yield {
                            "type": "content",
                            "content": new_text,
                            "timestamp": datetime.now().isoformat(),
                        }
                        # Very short delay for smooth streaming
                        await asyncio.sleep(0.01)

            # Store the complete response for analysis
            self.deps.response_text = previous_text

            # After streaming, show detailed search results
            if self.deps.search_data and self.deps.search_data.chunks:
                # Build sources data
                sources_data = []
                for i, chunk in enumerate(self.deps.search_data.chunks[:10], 1):
                    sources_data.append(
                        {
                            "episode_number": i,
                            "episode_id": chunk.get("chunk_id"),
                            "document_id": chunk.get("document_id"),
                            "similarity": chunk.get("similarity", 0),
                            "preview": (
                                chunk.get("text", "")[:100] + "..."
                                if chunk.get("text", "")
                                else "No content"
                            ),
                        }
                    )

                # Build entities data
                entities_data = []
                if self.deps.search_data.entities:
                    for entity in self.deps.search_data.entities[:20]:
                        entities_data.append(
                            {
                                "name": entity.get("name", "Unknown"),
                                "type": entity.get("type", "Unknown"),
                                "description": entity.get("description", "No description"),
                            }
                        )

                # Build relationships data
                relationships_data = []
                if self.deps.search_data.relationships:
                    for rel in self.deps.search_data.relationships[:15]:
                        relationships_data.append(
                            {
                                "source": rel.get("source", "Unknown"),
                                "target": rel.get("target", "Unknown"),
                                "type": rel.get("type", "Unknown"),
                                "properties": rel.get("metadata", {}),
                            }
                        )

                yield {
                    "type": "search_details",
                    "content": f"📚 Search Results Details ({len(sources_data)} episodes found)",
                    "data": {
                        "query": (
                            self.deps.search_queries[-1] if self.deps.search_queries else "Unknown"
                        ),
                        "sources": sources_data,
                        "entities": entities_data,
                        "relationships": relationships_data,
                        "summary": {
                            "episodes": len(sources_data),
                            "entities": len(entities_data),
                            "relationships": len(relationships_data),
                        },
                    },
                    "timestamp": datetime.now().isoformat(),
                }

            # Emit reasoning analysis event
            if self.deps.search_data:
                reasoning_analysis = self._analyze_response_construction(
                    self.deps.response_text, self.deps
                )

                yield {
                    "type": "reasoning",
                    "content": "📊 Response Construction Analysis",
                    "data": reasoning_analysis,
                    "timestamp": datetime.now().isoformat(),
                }

            # Generate dynamic follow-up questions based on search results
            follow_ups = []

            if self.deps.search_data and self.deps.search_data.chunks:
                # Extract key topics from the chunks for contextual questions
                chunk_text = " ".join(
                    [chunk.get("text", "") for chunk in self.deps.search_data.chunks[:3]]
                )

                # Look for specific entities or topics mentioned
                if "age" in chunk_text.lower() and (
                    "vigil" in chunk_text.lower() or "marking" in chunk_text.lower()
                ):
                    follow_ups.append("Tell me more about the Age of Vigil and Age of Marking")
                if "prisoner" in chunk_text.lower():
                    follow_ups.append("What is the Prisoner and why is it important?")
                if "luminari" in chunk_text.lower() and (
                    "mark" in chunk_text.lower() or "heroes" in chunk_text.lower()
                ):
                    follow_ups.append("Who are the Luminari and what is their mark?")
                if "arcanite" in chunk_text.lower():
                    follow_ups.append("What is Arcanite and how is it used?")
                # Add entity-specific follow-ups based on what was found
                if len(self.deps.search_data.entities) > 0:
                    # Pick the most interesting entities for follow-up
                    entity_names = [
                        e.name for e in self.deps.search_data.entities[:3] if hasattr(e, "name")
                    ]
                    if entity_names:
                        if len(entity_names) == 1:
                            follow_ups.append(f"Tell me more about {entity_names[0]}")
                        elif len(entity_names) >= 2:
                            follow_ups.append(
                                f"How are {entity_names[0]} and {entity_names[1]} connected?"
                            )

                # Add relationship-specific follow-ups if we have facts
                if len(self.deps.search_data.relationships) > 0:
                    # Look for relationships with facts
                    facts_found = False
                    for rel in self.deps.search_data.relationships[:5]:
                        if hasattr(rel, "metadata") and rel.metadata and "fact" in rel.metadata:
                            facts_found = True
                            break

                    if facts_found:
                        follow_ups.append(
                            "What do the relationship facts tell us about this topic?"
                        )

                # Add subgraph-specific follow-ups
                if hasattr(self.deps.search_data, "subgraphs") and self.deps.search_data.subgraphs:
                    if len(self.deps.search_data.subgraphs) > 0:
                        follow_ups.append("Explain the connections in the knowledge graph")

            # Fallback questions if no specific content found
            if not follow_ups:
                follow_ups = [
                    "Search for more specific topics",
                    "Try a different search term",
                    "What other lore topics are available?",
                ]

            yield {
                "type": "follow_up_questions",
                "content": "Explore further:",
                "data": {"suggested_questions": follow_ups},
                "timestamp": datetime.now().isoformat(),
            }

            # Send completion
            yield {
                "type": "complete",
                "content": "✨ Response complete",
                "data": {"suggested_questions": follow_ups},
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Stream error (%s)", type(e).__name__)

            yield {
                "type": "error",
                "content": public_error_message("Chat stream"),
                "timestamp": datetime.now().isoformat(),
            }
