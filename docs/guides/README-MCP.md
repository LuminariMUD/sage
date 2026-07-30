# Luminari Lore MCP Server

**Documentation Type**: MCP Server Setup & Usage Guide  
**Audience**: Claude Desktop Users, MCP Client Integrators

> **Note**: For general project documentation, setup, and API information, see [README.md](./README.md).

This directory contains a Model Context Protocol (MCP) server that provides Claude Desktop and other MCP clients with direct access to the Luminari MUD world lore via the Graph RAG API.

## Overview

The MCP server runs alongside the FastAPI server in the same container, providing 5 tools for querying the comprehensive fantasy world knowledge base:

- **query_lore**: Natural language queries using RAG (Retrieval-Augmented Generation)
- **search_entities**: Find entities by name or type (deities, locations, people, etc.)
- **get_entity_details**: Get comprehensive information about specific entities
- **get_entity_relationships**: Explore entity connections in the knowledge graph
- **get_lore_stats**: Get system statistics and health metrics

## Setup

### 1. Container Configuration

The MCP server runs on port 8004 alongside the FastAPI server (port 8003) using supervisor:

- **API Server**: `http://localhost:8003` (FastAPI with Graph RAG endpoints)
- **MCP Server**: `http://localhost:8004` (stdio-based MCP protocol)

### 2. Claude Desktop Configuration

Add this to your Claude Desktop MCP settings file:

**Location**: 
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "luminari-lore": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "luminari-sage-api-1",
        "python",
        "-m",
        "src.mcp.server"
      ],
      "env": {
        "PYTHONPATH": "/app"
      },
      "description": "Access to the Luminari MUD world lore via Graph RAG API"
    }
  }
}
```

### 3. Alternative: Direct Connection

If running locally without Docker:

```json
{
  "mcpServers": {
    "luminari-lore": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/luminari-sage",
      "env": {
        "PYTHONPATH": "/path/to/luminari-sage"
      }
    }
  }
}
```

## Available Tools

### query_lore
Query the lore using natural language. Returns semantically relevant text chunks from the knowledge base.

**Parameters**:
- `query` (required): Natural language question about the lore
- `max_results` (optional): Number of chunks to return (1-20, default 5)
- `threshold` (optional): Similarity threshold (0.0-1.0, default 0.1)

**Example**: "Tell me about the Knights of the Crimson Loom"

### search_entities
Find entities by name or description with optional type filtering.

**Parameters**:
- `query` (required): Search term (entity name or keyword)
- `entity_type` (optional): Filter by type (Deity, Organization, Person, Location, etc.)
- `limit` (optional): Max results (1-50, default 10)

**Example**: Search for "Paladine" with entity_type "Deity"

### get_entity_details
Get comprehensive information about a specific entity including properties and metadata.

**Parameters**:
- `entity_id` (required): Unique identifier from search_entities

### get_entity_relationships
Explore knowledge graph connections for an entity.

**Parameters**:
- `entity_id` (required): Unique identifier from search_entities

**Returns**: Relationships like Commands, ServesUnder, OpposedTo, Influences, etc.

### get_lore_stats
Get system statistics including document counts, entity counts by type, and relationship counts.

**No parameters required.**

## Entity Types

The system recognizes 13 entity types:
- **Deity**: Gods and divine beings
- **Organization**: Orders, guilds, institutions  
- **Person**: Named individuals, NPCs
- **Location**: Cities, regions, landmarks
- **Concept**: Abstract ideas, philosophies
- **Artifact**: Magic items, relics
- **Event**: Historical occurrences
- **Race**: Player races, species
- **Faction**: Political groups, alliances
- **Creature**: Monsters, beings
- **Magic**: Spells, magical concepts
- **Prophecy**: Foretelling, destiny
- **Realm**: Planes, dimensions

## Relationship Types

The knowledge graph uses 14 relationship types:
- **Commands**: Leadership relationships
- **ServesUnder**: Service hierarchies
- **OpposedTo**: Conflicts and opposition
- **Influences**: Indirect effects
- **Protects**: Guardian relationships
- **Embodies**: Conceptual representation
- **AlliedWith**: Partnerships
- **DescendedFrom**: Ancestry, lineage
- **CreatedBy**: Creation relationships
- **TransformedInto**: Changes, evolution
- **BoundTo**: Magical/spiritual bonds
- **Corrupts**: Negative influence
- **TeachesTo**: Knowledge transfer
- **MENTIONS**: General references

## Data Coverage

The lore system contains 1000+ episodes covering:
- Complete pantheon with 40+ deities
- Six sacred knight orders
- World history across 7 ages
- Magic systems and spells
- Races, classes, and character builds
- Legendary locations and artifacts
- Factions like the Forgotten Tide pirates
- Adventure hooks and quest design

## Troubleshooting

### Connection Issues

1. **Check container status**: `docker ps` - ensure luminari-sage-api-1 is running
2. **Check API health**: `curl http://localhost:8003/api/v1/health`
3. **Check MCP server logs**: `docker logs luminari-sage-api-1`

### Empty Results

1. **Verify data load**: Use `get_lore_stats` to check entity/document counts
2. **Check similarity threshold**: Lower the threshold for broader results
3. **Try different query terms**: Use specific names or concepts

### Performance

- The system uses hybrid search: PostgreSQL (pgvector) for fast similarity + Neo4j for graph traversal
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
- Response time typically < 2 seconds for queries

## Development

The MCP server code is in `/src/mcp/server.py` and uses:
- **mcp** package for protocol implementation
- **aiohttp** for API communication
- **asyncio** for async operations

Logs are available in `/var/log/supervisor/mcp_stdout.log` and `mcp_stderr.log`.