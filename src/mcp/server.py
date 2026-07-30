"""
Luminari Lore MCP Server

Provides HTTP API access to the Luminari MUD world lore
via the Graph RAG API. Enables any LLM to connect remotely
to query the comprehensive fantasy world knowledge base.

Available Tools:
- query_lore: Ask questions about the lore (RAG query)
- search_entities: Find entities (deities, locations, people, etc.)
- get_entity_details: Get full information about a specific entity
- get_entity_relationships: Explore entity connections in the graph
- get_lore_stats: Get system statistics

Server runs on port 8004 with HTTP transport alongside FastAPI on port 8003.
"""

import logging
import os
from typing import Any

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, field_validator

# Import authentication for MCP endpoints
from src.auth import AuthMiddleware
from src.auth.host_validation import get_allowed_hosts
from src.security import (
    SensitiveDataFormatter,
    install_sensitive_logging,
    public_error_message,
    redact_sensitive_text,
)

# Configure logging
logging.basicConfig(level=logging.INFO, force=True)
for handler in logging.getLogger().handlers:
    handler.setFormatter(
        SensitiveDataFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
install_sensitive_logging()
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = "http://localhost:8003"
MCP_PORT = 8004

# Initialize FastAPI app
app = FastAPI(
    title="Luminari Lore MCP Server",
    description="HTTP API server for Luminari MUD world lore access via Graph RAG",
    version="1.0.0",
    root_path="",
)

# Browser access is opt-in and limited to explicit origins. API-key authentication
# does not use cookies, so credentialed cross-origin requests are unnecessary.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "MCP_CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Add authentication middleware
# Exclude health and info endpoints from auth
app.add_middleware(
    AuthMiddleware,
    exclude_paths={"/", "/health", "/docs", "/redoc", "/openapi.json"},
    mcp_path_prefix="/",  # MCP endpoints are at root level
    backend_path_prefix="/api",  # Not used in MCP server
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_allowed_hosts())


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Prevent authenticated MCP responses from being cached or embedded."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# Pydantic models for request/response
class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]


class PromptRequest(BaseModel):
    name: str
    arguments: dict[str, Any] | None = None


class ToolResponse(BaseModel):
    success: bool
    content: str | None = None
    error: str | None = None

    @field_validator("content", "error", mode="before")
    @classmethod
    def redact_credentials(cls, value: object) -> object:
        """Prevent credentials in upstream data from crossing the MCP boundary."""
        return redact_sensitive_text(value) if value is not None else None


class ToolInfo(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class PromptInfo(BaseModel):
    name: str
    description: str
    arguments: list[dict[str, Any]]


class ServerInfo(BaseModel):
    name: str
    version: str
    tools: list[ToolInfo]
    prompts: list[PromptInfo]


class LuminariLoreClient:
    """Client for interacting with the Luminari Lore API."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to the API."""
        url = f"{self.base_url}{endpoint}"

        # Prepare headers with authentication
        headers = {}
        api_key = os.getenv("SAGE_MCP_BACKEND_KEY")
        if api_key:
            headers["X-API-Key"] = api_key

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                if method.upper() == "GET":
                    async with session.get(url, params=params) as response:
                        response.raise_for_status()
                        return await response.json()
                elif method.upper() == "POST":
                    async with session.post(url, json=json_data) as response:
                        response.raise_for_status()
                        return await response.json()
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
            except aiohttp.ClientResponseError as e:
                logger.error("API request failed with status %s", e.status)
                raise RuntimeError(public_error_message("Upstream API request")) from e
            except aiohttp.ClientError as e:
                logger.error("API connection failed (%s)", type(e).__name__)
                raise RuntimeError(public_error_message("Upstream API connection")) from e
            except Exception as e:
                logger.error("Unexpected error in API request (%s)", type(e).__name__)
                raise RuntimeError(public_error_message("Upstream API request")) from e

    async def query_lore(
        self, query: str, max_results: int = 5, threshold: float = 0.1
    ) -> dict[str, Any]:
        """Query the lore using RAG (Retrieval-Augmented Generation)."""
        return await self._make_request(
            "POST",
            "/api/v1/rag/query",
            json_data={
                "query": query,
                "max_results": max_results,
                "threshold": threshold,
                "include_entities": True,
            },
        )

    async def search_entities(
        self, query: str, entity_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search for entities by name or description."""
        params = {"query": query, "limit": limit}
        if entity_type:
            params["entity_type"] = entity_type
        return await self._make_request("GET", "/api/v1/entities/search", params=params)

    async def get_entity_details(self, entity_id: str) -> dict[str, Any]:
        """Get detailed information about a specific entity."""
        return await self._make_request("GET", f"/api/v1/entities/{entity_id}")

    async def get_entity_relationships(self, entity_id: str) -> dict[str, Any]:
        """Get lightweight list of relationships for a specific entity."""
        return await self._make_request("GET", f"/api/v1/entities/{entity_id}/relationships")

    async def get_relationship_details(self, relationship_id: int) -> dict[str, Any]:
        """Get detailed information about a specific relationship."""
        return await self._make_request("GET", f"/api/v1/relationships/{relationship_id}")

    async def get_lore_stats(self) -> dict[str, Any]:
        """Get system statistics."""
        return await self._make_request("GET", "/api/v1/stats")


# Initialize the client
lore_client = LuminariLoreClient()

# Define available tools and prompts as data
AVAILABLE_TOOLS = [
    ToolInfo(
        name="query_lore",
        description="Query the Luminari MUD world lore using natural language. This uses RAG (Retrieval-Augmented Generation) to find relevant information from 1000+ episodes covering deities, knights, locations, races, magic, history, and more. Returns text chunks with high semantic relevance.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language question about Luminari lore (e.g., 'Tell me about the Knights of the Crimson Loom', 'What deities control magic?', 'Describe the Crystal Dwarves')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of text chunks to return (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold for results (0.0-1.0, lower = more permissive)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.1,
                },
            },
            "required": ["query"],
        },
    ),
    ToolInfo(
        name="search_entities",
        description="Search for specific entities in the Luminari world by name or description. Entities include deities, organizations, people, locations, concepts, artifacts, events, races, factions, creatures, magic systems, prophecies, and realms. Returns structured entity data with types and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (entity name or description keyword)",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type",
                    "enum": [
                        "Deity",
                        "Organization",
                        "Person",
                        "Location",
                        "Concept",
                        "Artifact",
                        "Event",
                        "Race",
                        "Faction",
                        "Creature",
                        "Magic",
                        "Prophecy",
                        "Realm",
                    ],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entities to return (1-50)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    ToolInfo(
        name="get_entity_details",
        description="Get comprehensive information about a specific entity including its properties, aliases, and metadata. Use this after finding an entity with search_entities to get the full details.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Unique identifier of the entity (obtained from search_entities)",
                }
            },
            "required": ["entity_id"],
        },
    ),
    ToolInfo(
        name="get_entity_relationships",
        description="Get a lightweight list of relationships for an entity. Returns relationship IDs, types, and connected entity names. Use get_relationship_details for full properties.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Unique identifier of the entity (obtained from search_entities)",
                }
            },
            "required": ["entity_id"],
        },
    ),
    ToolInfo(
        name="get_relationship_details",
        description="Get detailed information about a specific relationship including all properties and metadata. Use this after getting relationship IDs from get_entity_relationships.",
        inputSchema={
            "type": "object",
            "properties": {
                "relationship_id": {
                    "type": "integer",
                    "description": "Neo4j relationship ID (obtained from get_entity_relationships)",
                }
            },
            "required": ["relationship_id"],
        },
    ),
    ToolInfo(
        name="get_lore_stats",
        description="Get statistics about the Luminari lore knowledge base including document counts, entity counts by type, relationship counts, and system health metrics.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
]

AVAILABLE_PROMPTS = [
    PromptInfo(
        name="explore_entity_relationships",
        description="Deep dive into an entity's connections and relationships in the knowledge graph",
        arguments=[
            {
                "name": "entity_name",
                "description": "Name of the entity to explore",
                "required": True,
            },
            {
                "name": "relationship_focus",
                "description": "Type of relationships to focus on (optional)",
                "required": False,
            },
        ],
    ),
    PromptInfo(
        name="lore_research_query",
        description="Research a topic thoroughly using multiple search strategies",
        arguments=[
            {"name": "topic", "description": "Topic or question to research", "required": True},
            {
                "name": "context",
                "description": "Additional context or specific angle (optional)",
                "required": False,
            },
        ],
    ),
    PromptInfo(
        name="faction_analysis",
        description="Comprehensive analysis of a faction, organization, or group",
        arguments=[
            {
                "name": "faction_name",
                "description": "Name of the faction or organization",
                "required": True,
            }
        ],
    ),
    PromptInfo(
        name="deity_worship_network",
        description="Map the worship network and influence of a deity",
        arguments=[{"name": "deity_name", "description": "Name of the deity", "required": True}],
    ),
    PromptInfo(
        name="historical_investigation",
        description="Investigate a historical event and its consequences",
        arguments=[
            {
                "name": "event_or_period",
                "description": "Historical event or time period",
                "required": True,
            }
        ],
    ),
]


# FastAPI endpoints
@app.get("/", response_model=ServerInfo)
async def get_server_info():
    """Get server information including available tools and prompts."""
    return ServerInfo(
        name="luminari-lore", version="1.0.0", tools=AVAILABLE_TOOLS, prompts=AVAILABLE_PROMPTS
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        stats = await lore_client.get_lore_stats()
        return {
            "status": "healthy",
            "api_connected": True,
            "entities": stats["entities"]["total"],
            "relationships": stats["relationships"]["total"],
        }
    except Exception as e:
        logger.error("Health check failed (%s)", type(e).__name__)
        return {
            "status": "unhealthy",
            "api_connected": False,
            "error": public_error_message("Health check"),
        }


@app.get("/tools")
async def list_tools():
    """List available tools."""
    return {"tools": AVAILABLE_TOOLS}


@app.get("/prompts")
async def list_prompts():
    """List available prompts."""
    return {"prompts": AVAILABLE_PROMPTS}


@app.post("/tools/call", response_model=ToolResponse)
async def call_tool(tool_call: ToolCall):
    """Execute a tool call."""
    try:
        name = tool_call.name
        arguments = tool_call.arguments

        if name == "query_lore":
            query = arguments["query"]
            max_results = arguments.get("max_results", 5)
            threshold = arguments.get("threshold", 0.1)

            result = await lore_client.query_lore(query, max_results, threshold)

            # Format the response with enhanced graph data
            response_text = f"**Query:** {query}\n\n"
            response_text += (
                f"**Found {result['total_results']} relevant chunks with graph expansion:**\n\n"
            )

            for i, chunk in enumerate(result["chunks"], 1):
                response_text += f"### Chunk {i} (Similarity: {chunk['similarity']:.3f})\n"
                response_text += f"**Source:** Document {chunk['document_id']}\n\n"
                response_text += f"{chunk['text']}\n\n"

                # Show entities mentioned in this chunk
                if chunk.get("entities"):
                    response_text += (
                        f"**Entities in this chunk:** {len(chunk['entities'])} found\n\n"
                    )

                response_text += "---\n\n"

            # Show all discovered entities
            if result["entities"]:
                response_text += "**📍 Entities Found:**\n"
                for entity in result["entities"]:
                    response_text += f"- **{entity['name']}** ({entity['type']})\n"
                    if entity.get("description"):
                        response_text += f"  - {entity['description'][:100]}...\n"
                response_text += "\n"

            # Show graph relationships (the key enhancement!)
            if result.get("relationships"):
                response_text += "**🔗 Graph Relationships:**\n"

                # Group by strength for better readability
                direct_rels = [r for r in result["relationships"] if r.get("strength", 1) == 1]
                indirect_rels = [r for r in result["relationships"] if r.get("strength", 1) == 2]

                if direct_rels:
                    response_text += "*Direct connections:*\n"
                    for rel in direct_rels[:10]:  # Limit to first 10
                        response_text += f"  - **{rel['target_name']}** ({rel['target_type']}) — *{rel['type']}*\n"
                    if len(direct_rels) > 10:
                        response_text += (
                            f"  - ... and {len(direct_rels) - 10} more direct connections\n"
                        )
                    response_text += "\n"

                if indirect_rels:
                    response_text += "*Indirect connections (2-hop):*\n"
                    for rel in indirect_rels[:5]:  # Limit to first 5 for indirect
                        response_text += f"  - **{rel['target_name']}** ({rel['target_type']}) — *via {rel['type']}*\n"
                    if len(indirect_rels) > 5:
                        response_text += (
                            f"  - ... and {len(indirect_rels) - 5} more indirect connections\n"
                        )

            return ToolResponse(success=True, content=response_text)

        elif name == "search_entities":
            query = arguments["query"]
            entity_type = arguments.get("entity_type")
            limit = arguments.get("limit", 10)

            entities = await lore_client.search_entities(query, entity_type, limit)

            if not entities:
                return ToolResponse(success=True, content=f"No entities found matching '{query}'")

            response_text = f"**Found {len(entities)} entities matching '{query}':**\n\n"

            for entity in entities:
                response_text += f"**{entity['name']}** ({entity['type']})\n"
                response_text += f"- ID: `{entity['stable_id']}`\n"
                if entity.get("description"):
                    response_text += f"- Description: {entity['description']}\n"
                if entity.get("aliases"):
                    response_text += f"- Aliases: {', '.join(entity['aliases'])}\n"
                response_text += "\n"

            return ToolResponse(success=True, content=response_text)

        elif name == "get_entity_details":
            entity_id = arguments["entity_id"]

            entity = await lore_client.get_entity_details(entity_id)

            response_text = f"**Entity Details: {entity['name']}**\n\n"
            response_text += f"- **Type:** {entity['type']}\n"
            response_text += f"- **ID:** `{entity['stable_id']}`\n"

            if entity.get("description"):
                response_text += f"- **Description:** {entity['description']}\n"

            if entity.get("aliases"):
                response_text += f"- **Aliases:** {', '.join(entity['aliases'])}\n"

            if entity.get("metadata"):
                response_text += "\n**Additional Properties:**\n"
                for key, value in entity["metadata"].items():
                    response_text += f"- **{key.replace('_', ' ').title()}:** {value}\n"

            return ToolResponse(success=True, content=response_text)

        elif name == "get_entity_relationships":
            entity_id = arguments["entity_id"]

            try:
                relationships = await lore_client.get_entity_relationships(entity_id)
            except Exception as rel_error:
                logger.error(
                    "Failed to get entity relationships (%s)",
                    type(rel_error).__name__,
                )
                return ToolResponse(
                    success=False,
                    error=public_error_message("Relationship retrieval"),
                )

            response_text = f"**Relationships for Entity ID: {entity_id}**\n\n"

            if not relationships or not relationships.get("relationships"):
                response_text += "No relationships found for this entity."
            else:
                response_text += f"Found {len(relationships['relationships'])} relationships:\n\n"
                for rel in relationships["relationships"]:
                    if rel["direction"] == "outgoing":
                        response_text += f"**{rel['relationship_type']}** → {rel['target_name']} ({rel['target_type']})\n"
                    else:
                        response_text += f"**{rel['relationship_type']}** ← {rel['source_name']} ({rel['source_type']})\n"
                    response_text += f"  - ID: `{rel['relationship_id']}` (use get_relationship_details for full properties)\n\n"

            return ToolResponse(success=True, content=response_text)

        elif name == "get_relationship_details":
            relationship_id = arguments["relationship_id"]

            try:
                details = await lore_client.get_relationship_details(relationship_id)
            except Exception as rel_error:
                logger.error(
                    "Failed to get relationship details (%s)",
                    type(rel_error).__name__,
                )
                return ToolResponse(
                    success=False,
                    error=public_error_message("Relationship retrieval"),
                )

            response_text = f"**Relationship Details (ID: {relationship_id})**\n\n"
            response_text += f"**Type:** {details['relationship_type']}\n\n"
            response_text += (
                f"**Source:** {details['source']['name']} ({details['source']['type']})\n"
            )
            response_text += (
                f"**Target:** {details['target']['name']} ({details['target']['type']})\n\n"
            )

            if details.get("properties"):
                response_text += "**Properties:**\n"
                for key, value in details["properties"].items():
                    response_text += f"- **{key.replace('_', ' ').title()}:** {value}\n"
            else:
                response_text += "No additional properties found.\n"

            return ToolResponse(success=True, content=redact_sensitive_text(response_text))

        elif name == "get_lore_stats":
            stats = await lore_client.get_lore_stats()

            response_text = "**Luminari Lore System Statistics:**\n\n"
            response_text += "**Documents:**\n"
            response_text += f"- Total: {stats['documents']['total']}\n"
            response_text += f"- Types: {stats['documents']['types']}\n"
            response_text += f"- Canonical: {stats['documents']['canonical']}\n\n"

            response_text += "**Episodes (Text Chunks):**\n"
            response_text += f"- Total: {stats['chunks']['total']}\n"
            response_text += f"- Average size: {stats['chunks']['avg_size']} characters\n\n"

            response_text += "**Knowledge Graph:**\n"
            response_text += f"- Entities: {stats['entities']['total']}\n"
            response_text += f"- Entity types: {stats['entities']['types']}\n"
            response_text += f"- Relationships: {stats['relationships']['total']}\n"
            response_text += f"- Relationship types: {stats['relationships']['types']}\n"

            return ToolResponse(success=True, content=response_text)

        else:
            return ToolResponse(success=False, error="Unknown tool")

    except Exception as e:
        logger.error("Tool execution failed (%s)", type(e).__name__)
        return ToolResponse(success=False, error=public_error_message("Tool execution"))


@app.post("/prompts/get")
async def get_prompt(prompt_request: PromptRequest):
    """Get a specific prompt with instructions for effective lore querying."""
    name = prompt_request.name
    arguments = prompt_request.arguments or {}

    prompt_templates = {
        "explore_entity_relationships": """Let's explore the relationships and connections of {entity_name} in the Luminari lore.{focus_text}

First, search for the entity:
- Use search_entities with query "{entity_name}" to find the exact entity
- Note the entity_id from the results

Then get comprehensive information:
- Use get_entity_details with the entity_id to understand what/who this is
- Use get_entity_relationships with the entity_id to map all connections

For each related entity discovered:
- Use get_entity_details to understand the nature of each connection
- Look for patterns in relationship types (Commands, ServesUnder, OpposedTo, etc.)

Finally, use query_lore to find additional context:
- Query for stories or events involving {entity_name}
- Search for historical significance or recent developments

This approach will give you the richest view of {entity_name}'s place in the world.""",
        "lore_research_query": """Let's research {topic} thoroughly{context_text} using multiple approaches:

1. Direct Query:
   - Use query_lore with "{topic}" to get the most relevant text chunks
   - Note any entities mentioned in the results

2. Entity Discovery:
   - Use search_entities to find entities related to "{topic}"
   - Try different entity types (Deity, Location, Organization, etc.) if relevant
   - Get details for the most promising entities

3. Relationship Mapping:
   - For key entities found, use get_entity_relationships
   - Look for connecting patterns and influences

4. Broader Context:
   - Query related terms and synonyms
   - Search for historical events or consequences
   - Look for opposing forces or conflicts

5. Synthesis:
   - Combine the information from all sources
   - Identify gaps or contradictions
   - Note areas for deeper investigation

This systematic approach ensures comprehensive coverage of {topic}.""",
        "faction_analysis": """Let's conduct a comprehensive analysis of {faction_name}:

1. Core Identity:
   - Search for {faction_name} using search_entities (try "Organization" or "Faction" types)
   - Get full details to understand purpose, structure, and beliefs

2. Leadership Structure:
   - Use get_entity_relationships to find who Commands or leads the faction
   - Get details on key leaders and their backgrounds
   - Map the hierarchy and power structure

3. Membership & Allies:
   - Find entities that ServesUnder or are AlliedWith {faction_name}
   - Identify member races, classes, or types
   - Map allied organizations and support networks

4. Opposition & Conflicts:
   - Find entities OpposedTo {faction_name}
   - Search for historical conflicts and current tensions
   - Identify threats and challenges

5. Influence & Operations:
   - Find what {faction_name} Influences or Protects
   - Search for their activities, territories, and goals
   - Look for recent developments or changes

6. Historical Context:
   - Query for the faction's origins and founding
   - Research major events and turning points
   - Understand their role in world history

This provides a complete picture of {faction_name}'s role in the world.""",
        "deity_worship_network": """Let's map the worship network and divine influence of {deity_name}:

1. Divine Profile:
   - Search for {deity_name} using search_entities with type "Deity"
   - Get full details on domains, alignment, and divine nature
   - Note any aliases or alternate names

2. Direct Worship:
   - Find entities that ServesUnder {deity_name} (priesthoods, temples)
   - Look for organizations that Embodies their principles
   - Search for sacred sites and religious centers

3. Mortal Champions:
   - Find people or groups that {deity_name} Influences
   - Look for blessed champions or chosen heroes
   - Identify divine servants and avatars

4. Divine Relationships:
   - Use get_entity_relationships to map connections with other deities
   - Note allies (AlliedWith), enemies (OpposedTo), and family relations
   - Understand the divine hierarchy and politics

5. Worship Practices:
   - Query for rituals, holy days, and sacred practices
   - Search for temples, shrines, and pilgrimage sites
   - Find religious artifacts and relics

6. Worldly Impact:
   - Look for what {deity_name} Protects or Creates
   - Search for divine interventions and miracles
   - Understand their role in world events

This reveals {deity_name}'s complete sphere of influence.""",
        "historical_investigation": """Let's investigate {event_or_period} and trace its historical impact:

1. Core Event Research:
   - Search for {event_or_period} using search_entities with type "Event"
   - Use query_lore to find detailed accounts and descriptions
   - Establish timeline, key participants, and immediate consequences

2. Key Participants:
   - Identify all entities involved (people, organizations, locations)
   - Get details on major figures and their roles
   - Map relationships between participants (allies, enemies, neutral parties)

3. Causal Chain:
   - Find what CreatedBy or TransformedInto relationships connect to this event
   - Look for entities that were DescendedFrom consequences
   - Trace the chain of cause and effect

4. Geographic Impact:
   - Identify affected locations and regions
   - Look for places that were BoundTo or changed by these events
   - Map the geographic scope of influence

5. Long-term Consequences:
   - Find entities that were Created, Transformed, or Corrupted
   - Look for ongoing conflicts or alliances that stem from this period
   - Identify cultural, political, or religious changes

6. Modern Legacy:
   - Query for current references or ongoing effects
   - Find prophecies or expectations connected to these events
   - Understand how {event_or_period} shapes the present world

This investigation reveals the full historical significance and lasting impact.""",
    }

    if name not in prompt_templates:
        raise HTTPException(status_code=404, detail="Prompt not found")

    template = prompt_templates[name]

    # Format template with arguments
    if name == "explore_entity_relationships":
        entity_name = arguments.get("entity_name", "[ENTITY_NAME]")
        relationship_focus = arguments.get("relationship_focus", "")
        focus_text = (
            f" Focus particularly on {relationship_focus} relationships."
            if relationship_focus
            else ""
        )
        content = template.format(entity_name=entity_name, focus_text=focus_text)

    elif name == "lore_research_query":
        topic = arguments.get("topic", "[TOPIC]")
        context = arguments.get("context", "")
        context_text = f" with focus on {context}" if context else ""
        content = template.format(topic=topic, context_text=context_text)

    elif name == "faction_analysis":
        faction_name = arguments.get("faction_name", "[FACTION_NAME]")
        content = template.format(faction_name=faction_name)

    elif name == "deity_worship_network":
        deity_name = arguments.get("deity_name", "[DEITY_NAME]")
        content = template.format(deity_name=deity_name)

    elif name == "historical_investigation":
        event_or_period = arguments.get("event_or_period", "[EVENT/PERIOD]")
        content = template.format(event_or_period=event_or_period)

    return {"success": True, "content": content}


if __name__ == "__main__":
    uvicorn.run(
        "src.mcp.server:app",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=MCP_PORT,
        log_level="info",
        reload=False,
    )
