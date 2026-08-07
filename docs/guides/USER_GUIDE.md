# User Guide

**Version**: 0.7.10
**Status**: Production Ready
**Last Updated**: 2025-11-12

Complete user guide for interacting with Luminari Sage through the API and Claude Desktop (MCP).

---

## Table of Contents

- [Introduction](#introduction)
- [Getting Started](#getting-started)
- [Using the API](#using-the-api)
- [Using with Claude Desktop (MCP)](#using-with-claude-desktop-mcp)
- [Common Use Cases](#common-use-cases)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Introduction

### What is Luminari Sage?

Luminari Sage is an intelligent lore management system for LuminariMUD that combines:

- **Knowledge Graph**: Neo4j stores entities (characters, locations, factions) and their relationships
- **Vector Search**: PostgreSQL with pgvector enables semantic search across lore documents
- **AI Agents**: Automated validation, correction, and creative assistance for game lore
- **Hybrid RAG**: Combines graph traversal and semantic search for contextual answers

### What Can You Do?

- **Search Lore**: Find information about characters, locations, events, and factions
- **Ask Questions**: Get intelligent answers combining multiple sources
- **Validate Lore**: Check for contradictions and inconsistencies
- **Generate Content**: Create quests, stories, and character interactions
- **Explore Relationships**: Discover connections between entities

---

## Getting Started

### Access Methods

You can interact with Luminari Sage through:

1. **REST API**: Direct HTTP requests (for developers)
2. **Claude Desktop**: Natural language interface via MCP (for content creators)
3. **Postman**: Pre-configured API collections (for testing)

### Authentication

Protected API requests require an API key. From a repository checkout, use the
helper so the value does not appear in the process list:

```bash
./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
```

**API Key Types**:

- `BACKEND_API`: Full access to all endpoints
- `MCP_OPERATIONS`: Access for MCP server operations
- `MCP_BACKEND_ACCESS`: Backend access for MCP

---

## Using the API

### Base URL

```
Production: https://your-domain.com/sage/api
Local: http://localhost:8003
```

### Common Endpoints

#### 1. Search Lore

Find documents by keyword or semantic similarity:

```bash
# Basic search
curl "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves&limit=5" \
  -H "X-API-Key: your-api-key"
```

Response:

```json
{
  "results": [
    {
      "id": "doc-uuid",
      "title": "Crystal Dwarves of Hir-Pesh",
      "snippet": "The Crystal Dwarves are...",
      "similarity": 0.85,
      "source_file": "canon/cultures/crystal_dwarves.md"
    }
  ],
  "query": "crystal dwarves",
  "count": 5
}
```

#### 2. Ask Questions (RAG)

Get intelligent answers combining multiple sources:

```bash
curl -X POST "http://localhost:8003/api/v1/rag/query" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who are the Crystal Dwarves?",
    "limit": 5
  }'
```

Response:

```json
{
  "answer": "The Crystal Dwarves are an ancient dwarven civilization...",
  "sources": [
    {
      "title": "Crystal Dwarves of Hir-Pesh",
      "snippet": "...",
      "relevance": 0.92
    }
  ],
  "entities": [
    {
      "name": "Crystal Dwarves",
      "type": "Race",
      "relationships": ["worships Earth Mother", "inhabits Hir-Pesh"]
    }
  ]
}
```

#### 3. Search Entities

Find entities in the knowledge graph:

```bash
curl "http://localhost:8003/api/v1/entities/search?query=void&entity_types=Location,Faction" \
  -H "X-API-Key: your-api-key"
```

Response:

```json
{
  "entities": [
    {
      "id": "entity-uuid",
      "name": "Void's Wake",
      "type": "Location",
      "summary": "A mysterious location where reality fragments...",
      "relationships_count": 12
    }
  ]
}
```

#### 4. Get Entity Details

Retrieve complete information about an entity:

```bash
curl "http://localhost:8003/api/v1/entities/entity-uuid" \
  -H "X-API-Key: your-api-key"
```

Response:

```json
{
  "id": "entity-uuid",
  "name": "Void's Wake",
  "type": "Location",
  "summary": "A mysterious location...",
  "properties": {
    "terrain": "void-touched",
    "danger_level": "extreme"
  },
  "created_at": "2025-01-15T10:30:00Z"
}
```

#### 5. Get Entity Relationships

Find connections between entities:

```bash
curl "http://localhost:8003/api/v1/entities/entity-uuid/relationships" \
  -H "X-API-Key: your-api-key"
```

Response:

```json
{
  "entity": {
    "id": "entity-uuid",
    "name": "Void's Wake"
  },
  "relationships": [
    {
      "id": "rel-uuid",
      "type": "RELATES_TO",
      "semantic_type": "Connected_To",
      "target_entity": {
        "id": "other-uuid",
        "name": "Forgotten Tide",
        "type": "Faction"
      },
      "fact": "Void's Wake is connected to the Forgotten Tide through ancient portals"
    }
  ]
}
```

### Chat Interface

Stream conversational responses:

```bash
curl -X POST "http://localhost:8003/api/v1/chat" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about the Void Witch",
    "conversation_id": "optional-conv-id"
  }'
```

Response (Server-Sent Events stream):

```
data: {"type": "chunk", "content": "The Void Witch "}
data: {"type": "chunk", "content": "is a mysterious "}
data: {"type": "chunk", "content": "figure who..."}
data: {"type": "done"}
```

---

## Using with Claude Desktop (MCP)

### Setup

1. **Configure Claude Desktop**:

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "luminari-sage": {
      "command": "uvx",
      "args": ["--from", "/path/to/luminari-sage", "mcp-server-luminari-sage"],
      "env": {
        "BACKEND_API_BASE_URL": "http://localhost:8003",
        "BACKEND_API_KEY": "your-backend-api-key",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "luminari_sage",
        "POSTGRES_USER": "luminari",
        "POSTGRES_PASSWORD": "your-password"
      }
    }
  }
}
```

2. **Restart Claude Desktop**

3. **Verify Connection**:

In Claude Desktop, ask: "Can you search Luminari lore for crystal dwarves?"

### Natural Language Queries

With MCP, you can interact naturally:

**Example Conversations**:

```
You: What do you know about Void's Wake?

Claude: Let me search the lore for information about Void's Wake.
[Uses hybrid_rag_search tool]

Void's Wake is a mysterious location where reality itself fragments...
```

```
You: Show me all factions that are connected to the Void's Wake.

Claude: I'll query the knowledge graph for faction relationships.
[Uses get_entity_relationships tool]

The following factions are connected to Void's Wake:
1. Forgotten Tide - Connected through ancient portals
2. Void Watchers - Protects the boundaries of Void's Wake
```

```
You: Generate a quest involving the Crystal Dwarves.

Claude: I'll create a quest for you.
[Uses quest planning workflow]

Quest: "The Crystal Forge"
Objective: Help the Crystal Dwarves rekindle their ancient forge...
```

### Available MCP Tools

Claude can use these tools automatically:

| Tool                       | Purpose                                           |
| -------------------------- | ------------------------------------------------- |
| `hybrid_rag_search`        | Search lore with semantic + keyword search        |
| `get_entity_by_name`       | Look up specific entity details                   |
| `get_entity_relationships` | Find connections between entities                 |
| `search_entities_by_type`  | Filter entities by type (Location, Faction, etc.) |
| `validate_content`         | Check lore for consistency                        |
| `direct_answer`            | Get focused answers to specific questions         |

---

## Common Use Cases

### 1. Research a Location

**Goal**: Learn everything about a specific location

**Via API**:

```bash
# Step 1: Search for the location
curl "http://localhost:8003/api/v1/entities/search?query=Hir-Pesh" \
  -H "X-API-Key: your-api-key"

# Step 2: Get entity details
curl "http://localhost:8003/api/v1/entities/{entity-id}" \
  -H "X-API-Key: your-api-key"

# Step 3: Get relationships
curl "http://localhost:8003/api/v1/entities/{entity-id}/relationships" \
  -H "X-API-Key: your-api-key"
```

**Via Claude (MCP)**:

```
You: Tell me everything about Hir-Pesh, including who lives there
     and what factions are nearby.
```

### 2. Validate New Lore

**Goal**: Check if new content contradicts existing lore

**Via API**:

```bash
curl -X POST "http://localhost:8003/api/v1/validate" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "The Crystal Dwarves worship the Ocean God.",
    "context": {
      "document_type": "lore_note",
      "author": "user"
    }
  }'
```

Response:

```json
{
  "valid": false,
  "confidence": 0.85,
  "issues": [
    {
      "severity": "warning",
      "message": "Contradiction detected: Crystal Dwarves are documented to worship the Earth Mother, not the Ocean God",
      "evidence": [
        {
          "source": "canon/cultures/crystal_dwarves.md",
          "snippet": "The Crystal Dwarves worship the Earth Mother..."
        }
      ]
    }
  ]
}
```

**Via Claude (MCP)**:

```
You: Is it consistent with existing lore that the Crystal Dwarves
     worship the Ocean God?
```

### 3. Generate a Quest

**Goal**: Create a quest involving specific entities

**Via Claude (MCP)**:

```
You: Create a quest that involves the Void's Wake and the
     Forgotten Tide faction. Make it suitable for level 10-15 players.

Claude: I'll generate a quest for you...
[Uses quest_workflow tool]

Quest: "Echoes of the Forgotten"
Level Range: 10-15
Location: Void's Wake

Synopsis: The Forgotten Tide has discovered an ancient artifact...
```

### 4. Explore Entity Connections

**Goal**: Discover how entities are related

**Via API**:

```bash
# Get relationships
curl "http://localhost:8003/api/v1/entities/{entity-id}/relationships" \
  -H "X-API-Key: your-api-key"
```

**Via Claude (MCP)**:

```
You: Show me how the Void Witch is connected to other entities
     in the lore. Include up to 2 degrees of separation.
```

### 5. Search by Theme

**Goal**: Find all lore related to a specific theme

**Via API**:

```bash
# Semantic search
curl -X POST "http://localhost:8003/api/v1/rag/query" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "ancient magical artifacts with corrupting influence",
    "limit": 10
  }'
```

**Via Claude (MCP)**:

```
You: Find all lore related to ancient magical artifacts that
     have corrupting influences on their users.
```

---

## Best Practices

### 1. Use Specific Queries

**❌ Bad**: "Tell me about stuff"
**✅ Good**: "What is the relationship between Void's Wake and the Forgotten Tide?"

### 2. Specify Entity Types

When searching entities, filter by type for better results:

```bash
# More precise
curl "http://localhost:8003/api/v1/entities/search?query=void&entity_types=Location,Faction"

# Less precise
curl "http://localhost:8003/api/v1/entities/search?query=void"
```

### 3. Validate Before Adding

Always validate new lore against existing content:

```bash
curl -X POST "http://localhost:8003/api/v1/validate" \
  -H "X-API-Key: your-api-key" \
  -d '{"content": "Your new lore content here"}'
```

### 4. Use RAG for Context

For questions requiring context from multiple sources, use the RAG endpoint:

```bash
# Better for complex questions
POST /api/v1/rag/query

# Better for simple lookups
GET /api/v1/lore/search
```

### 5. Provide Context

When asking questions, provide relevant context:

**❌ Vague**: "Who is she?"
**✅ Clear**: "Who is the Void Witch mentioned in the Forgotten Tide lore?"

---

## Troubleshooting

### Common Issues

#### No Results Found

**Problem**: Search returns empty results

**Solutions**:

1. Check if data is loaded: `GET /api/v1/health`
2. Try broader search terms
3. Use semantic search (RAG) instead of exact matching
4. Check for typos in entity names

#### Authentication Errors

**Problem**: `403 Forbidden` or `401 Unauthorized`

**Solutions**:

1. Verify API key is correct
2. Check API key is included in `X-API-Key` header
3. Ensure you're using the correct key type for the endpoint

#### Slow Queries

**Problem**: Requests take too long

**Solutions**:

1. Reduce `limit` parameter in search queries
2. Be more specific in search queries
3. Use entity ID lookups instead of searches when possible
4. Check system status: `GET /api/v1/health`

#### MCP Connection Issues

**Problem**: Claude can't connect to Luminari Sage

**Solutions**:

1. Verify services are running: `docker compose ps`
2. Check Claude Desktop config has correct URLs
3. Restart Claude Desktop
4. Check MCP server logs

### Getting Help

- **API Issues**: Check [API Reference](../reference/API_REFERENCE.md)
- **MCP Issues**: See [MCP Guide](README-MCP.md)
- **System Issues**: See [Deployment Guide](DEPLOYMENT_GUIDE.md)
- **Development**: See [Developer Guide](../development/DEVELOPER_GUIDE.md)

---

## Appendix

### HTTP Status Codes

| Code | Meaning             | Common Causes                        |
| ---- | ------------------- | ------------------------------------ |
| 200  | Success             | Request completed successfully       |
| 400  | Bad Request         | Invalid parameters or malformed JSON |
| 401  | Unauthorized        | Missing API key                      |
| 403  | Forbidden           | Invalid or unauthorized API key      |
| 404  | Not Found           | Entity or resource doesn't exist     |
| 429  | Too Many Requests   | Rate limit exceeded                  |
| 500  | Server Error        | Internal error (check logs)          |
| 503  | Service Unavailable | Service is down or restarting        |

### Rate Limits

- **Search**: 60 requests/minute
- **RAG Queries**: 20 requests/minute
- **Chat**: 30 messages/minute
- **Validation**: 10 requests/minute

### Supported Entity Types

- **Deity**: Gods and divine beings
- **Person**: Named individuals
- **Organization**: Groups and orders
- **Race**: Species and ethnicities
- **Faction**: Political/military groups
- **Location**: Places and regions
- **Creature**: Monsters and beasts
- **Magic**: Spells and magical systems
- **Artifact**: Magical items
- **Event**: Historical occurrences
- **Concept**: Abstract ideas
- **Prophecy**: Predictions and omens
- **Realm**: Planes and dimensions

---

## Related Documentation

- [Quickstart Guide](QUICKSTART.md)
- [API Reference](../reference/API_REFERENCE.md)
- [MCP Integration Guide](README-MCP.md)
- [Architecture Overview](../reference/ARCHITECTURE.md)
