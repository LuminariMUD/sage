# API Reference

**Version**: 0.7.10
**Last Updated**: 2025-11-12

This document provides complete API reference for Luminari Sage, including all endpoints, request/response formats, authentication, and examples.

## Table of Contents

- [Base Configuration](#base-configuration)
- [Authentication](#authentication)
- [Health & System Endpoints](#health--system-endpoints)
- [Entity Endpoints](#entity-endpoints)
- [Lore Search Endpoints](#lore-search-endpoints)
- [RAG (Retrieval-Augmented Generation)](#rag-retrieval-augmented-generation)
- [Validation System](#validation-system)
- [Correction System](#correction-system)
- [Chat Agent](#chat-agent)
- [Debug Endpoints](#debug-endpoints)
- [Error Handling](#error-handling)
- [Code Examples](#code-examples)

---

## Base Configuration

### Base URL

**Development/Local:**

```
http://localhost:8003
```

**Production (behind reverse proxy):**

```
https://yourdomain.com/sage
```

### Content Types

- **Request**: `application/json`
- **Response**: `application/json` (except SSE streaming endpoints)

---

## Authentication

All API endpoints (except `/ping` and `/docs`) require authentication via API key.

### Authentication Header

```http
X-API-Key: your-api-key-here
```

### Key Types

Luminari Sage supports three types of API keys:

1. **Backend API Key** (`SAGE_API_KEY`): Full access to all endpoints
2. **MCP Operations Key** (`SAGE_MCP_KEY`): MCP server operations
3. **MCP Backend Access Key** (`SAGE_MCP_BACKEND_KEY`): Backend access for MCP

### Authentication Example

```bash
curl -X GET http://localhost:8003/api/v1/health \
  -H "X-API-Key: your-api-key-here"
```

### Disabling Authentication (Development Only)

Set environment variable:

```bash
DISABLE_AUTH=true
```

**⚠️ WARNING**: Never disable authentication in production!

---

## Health & System Endpoints

### GET /ping

Simple availability check that doesn't require authentication.

**Response:**

```json
{
  "status": "ok",
  "message": "pong"
}
```

**Status Codes:**

- `200`: Service is running

---

### GET /api/v1/health

Comprehensive health check for all services.

**Authentication**: Required

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgresql": "healthy",
    "neo4j": "healthy",
    "embedding_model": "healthy"
  }
}
```

**Status Values:**

- `healthy`: Service operational
- `degraded`: Some services unavailable
- `unhealthy`: Critical services down

**Status Codes:**

- `200`: Health check completed

---

### GET /api/v1/stats

Get comprehensive statistics about the knowledge base.

**Authentication**: Required

**Response:**

```json
{
  "documents": {
    "total": 83,
    "types": 5,
    "canonical": 83
  },
  "chunks": {
    "total": 1250,
    "avg_size": 350
  },
  "entities": {
    "total": 500,
    "types": 15
  },
  "relationships": {
    "total": 1500,
    "types": 25
  }
}
```

**Status Codes:**

- `200`: Success

---

## Entity Endpoints

### GET /api/v1/entities/search

Search for entities by name or description.

**Authentication**: Required

**Query Parameters:**

- `query` (required): Search term
- `entity_type` (optional): Filter by entity type (e.g., `Character`, `Location`, `Event`)
- `limit` (optional, default: 10, max: 100): Maximum results

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/entities/search?query=crystal&limit=10" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
[
  {
    "uuid": "entity-uuid-123",
    "type": "Faction",
    "name": "Crystal Dwarves",
    "description": "Ancient dwarf clan known for crystal craftsmanship",
    "aliases": ["Crystalborn", "Crystal Clan"],
    "metadata": {
      "status": "active",
      "location": "Crystal Mountains"
    }
  }
]
```

**Status Codes:**

- `200`: Success
- `400`: Invalid query parameters

---

### GET /api/v1/entities/{entity_id}

Get detailed information about a specific entity.

**Authentication**: Required

**Path Parameters:**

- `entity_id`: Neo4j Entity UUID

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/entities/entity-uuid-123 \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "uuid": "entity-uuid-123",
  "type": "Character",
  "name": "Thrain Ironfoot",
  "description": "Legendary dwarf warrior and leader",
  "aliases": ["Ironfoot", "The Unbreakable"],
  "metadata": {
    "attributes": {
      "title": "Knight Commander",
      "status": "active"
    },
    "raw": {
      "birth_year": "1200 DR",
      "faction": "Order of the Silver Hand"
    }
  }
}
```

**Status Codes:**

- `200`: Success
- `404`: Entity not found

---

### GET /api/v1/entities/{entity_id}/relationships

Get relationships for a specific entity (lightweight list).

**Authentication**: Required

**Path Parameters:**

- `entity_id`: Neo4j Entity UUID

**Query Parameters:**

- `limit` (optional, default: 50, max: 100): Maximum results

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/entities/entity-uuid-123/relationships?limit=50" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "relationships": [
    {
      "relationship_id": 12345,
      "relationship_type": "MEMBER_OF",
      "direction": "outgoing",
      "target_id": "entity-uuid-456",
      "target_name": "Order of the Silver Hand",
      "target_type": "Organization"
    },
    {
      "relationship_id": 12346,
      "relationship_type": "LEADS",
      "direction": "incoming",
      "source_id": "entity-uuid-789",
      "source_name": "King Thorin",
      "source_type": "Character"
    }
  ]
}
```

**Status Codes:**

- `200`: Success
- `404`: Entity not found

---

### GET /api/v1/relationships/{relationship_id}

Get detailed information about a specific relationship.

**Authentication**: Required

**Path Parameters:**

- `relationship_id`: Neo4j relationship internal ID (integer)

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/relationships/12345 \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "relationship_id": 12345,
  "relationship_type": "MEMBER_OF",
  "source": {
    "id": "entity-uuid-123",
    "name": "Thrain Ironfoot",
    "type": "Character"
  },
  "target": {
    "id": "entity-uuid-456",
    "name": "Order of the Silver Hand",
    "type": "Organization"
  },
  "properties": {
    "fact": "Thrain Ironfoot is the Knight Commander of the Order of the Silver Hand",
    "rank": "Knight Commander",
    "since": "1450 DR",
    "status": "active"
  }
}
```

**Status Codes:**

- `200`: Success
- `404`: Relationship not found

---

## Lore Search Endpoints

### GET /api/v1/lore/search

Search lore documents using full-text search.

**Authentication**: Required

**Query Parameters:**

- `query` (required): Search query
- `document_type` (optional): Filter by document type
- `canonical_only` (optional, default: false): Only search canonical documents
- `limit` (optional, default: 10, max: 100): Maximum results

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/lore/search?query=sundering&limit=10" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
[
  {
    "id": "doc-uuid-123",
    "title": "The Sundering",
    "document_type": "event",
    "source_file": "ages_and_cataclysms/the_sundering.md",
    "summary": "The Sundering was a cataclysmic event...",
    "canonical": true,
    "metadata": {
      "author": "Lore Team",
      "date_created": "2024-01-01"
    }
  }
]
```

**Status Codes:**

- `200`: Success
- `400`: Invalid query parameters

---

## RAG (Retrieval-Augmented Generation)

### POST /api/v1/rag/query

Execute a hybrid RAG query combining PostgreSQL vector search with Neo4j graph traversal.

**Authentication**: Required

**Request Body:**

```json
{
  "query": "What is the relationship between the Crystal Dwarves and the Sundering?",
  "limit": 5,
  "include_entities": true,
  "threshold": 0.1
}
```

**Request Fields:**

- `query` (required): Natural language query
- `limit` (optional, default: 5, max: 20): Number of chunks to retrieve
- `include_entities` (optional, default: true): Include entity information
- `threshold` (optional, default: 0.1): Similarity threshold (0.0-1.0)

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tell me about the Crystal Dwarves",
    "limit": 5,
    "threshold": 0.3
  }'
```

**Response:**

```json
{
  "query": "Tell me about the Crystal Dwarves",
  "chunks": [
    {
      "chunk_id": "episode-uuid-123",
      "document_id": "doc-uuid-456",
      "text": "The Crystal Dwarves are an ancient clan...",
      "similarity": 0.87,
      "keywords": [],
      "entities": []
    }
  ],
  "entities": [
    {
      "uuid": "entity-uuid-789",
      "type": "Faction",
      "name": "Crystal Dwarves",
      "description": "Ancient dwarf clan...",
      "aliases": ["Crystalborn"],
      "metadata": {}
    }
  ],
  "relationships": [
    {
      "source": "entity-uuid-789",
      "target": "entity-uuid-101",
      "type": "RESIDES_IN",
      "target_name": "Crystal Mountains",
      "target_type": "Location",
      "strength": 1,
      "metadata": {
        "fact": "The Crystal Dwarves reside in the Crystal Mountains",
        "since": "Ancient times"
      }
    }
  ],
  "total_results": 1,
  "metadata": {
    "graph_entities": [...],
    "graph_relationships": [...]
  }
}
```

**Status Codes:**

- `200`: Success
- `400`: Invalid request body
- `503`: Embedding model not loaded

---

## Validation System

### POST /api/v1/validate

Validate content against existing lore knowledge.

**Authentication**: Required

**Request Body:**

```json
{
  "content": "In 1600 DR, Thrain Ironfoot founded the Crystal Dwarves.",
  "context": "Timeline validation",
  "strict": true
}
```

**Request Fields:**

- `content` (required): Content to validate
- `context` (optional): Additional context
- `strict` (optional, default: false): Use strict validation rules

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/validate \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "In 1600 DR, Thrain founded the Order.",
    "strict": true
  }'
```

**Response:**

```json
{
  "is_valid": false,
  "confidence": 0.75,
  "issues": [
    {
      "severity": "error",
      "category": "timeline",
      "message": "Year 1600 is beyond the current timeline (1500 DR)",
      "suggestion": "Check the timeline reference",
      "references": ["ages_and_cataclysms/TIMELINE.md"]
    }
  ],
  "related_entities": [
    {
      "uuid": "entity-uuid-123",
      "type": "Character",
      "name": "Thrain Ironfoot",
      "description": "...",
      "aliases": [],
      "metadata": {}
    }
  ],
  "supporting_lore": ["Timeline Reference: The current year is 1500 DR..."]
}
```

**Status Codes:**

- `200`: Success
- `400`: Invalid request body
- `503`: Embedding model not loaded

---

### POST /api/v1/validate/relationships

Validate entity relationships for consistency and correctness.

**Authentication**: Required

**Request Body:**

```json
{
  "entity_limit": 1000,
  "relationship_limit": 5000,
  "check_bidirectional": true,
  "check_mutual_exclusivity": true,
  "check_hierarchies": true,
  "check_semantic_consistency": true,
  "enable_llm_analysis": true,
  "auto_correct": false,
  "correct_duplicates": true,
  "standardize_semantics": true,
  "confidence_threshold": 0.85,
  "max_corrections": 100,
  "dry_run": true
}
```

**Request Fields:**

- `entity_limit` (optional, default: 1000): Maximum entities to check
- `relationship_limit` (optional, default: 5000): Maximum relationships to analyze
- `check_bidirectional` (optional, default: true): Check bidirectional consistency
- `check_mutual_exclusivity` (optional, default: true): Check mutually exclusive relationships
- `check_hierarchies` (optional, default: true): Validate hierarchical relationships
- `check_semantic_consistency` (optional, default: true): Check semantic property consistency
- `enable_llm_analysis` (optional, default: true): Enable LLM-enhanced analysis
- `auto_correct` (optional, default: false): Enable autonomous corrections
- `correct_duplicates` (optional, default: true): Remove duplicate relationships
- `standardize_semantics` (optional, default: true): Standardize semantic types
- `confidence_threshold` (optional, default: 0.85): Minimum confidence for auto-correction
- `max_corrections` (optional, default: 100): Maximum corrections to apply
- `dry_run` (optional, default: true): Preview corrections without applying

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/validate/relationships \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_limit": 100,
    "auto_correct": false,
    "dry_run": true
  }'
```

**Response:**

```json
{
  "report_id": "report-uuid-123",
  "agent_id": "relationship-validator-001",
  "timestamp": "2025-11-12T10:30:00Z",
  "validation_type": "relationship_validation",
  "scope_description": "Validated 100 entities and 250 relationships",
  "total_items_checked": 350,
  "findings_count": 15,
  "severity_counts": {
    "critical": 2,
    "high": 5,
    "medium": 6,
    "low": 2
  },
  "category_counts": {
    "duplicate_relationship": 8,
    "semantic_inconsistency": 4,
    "missing_property": 3
  },
  "findings": [
    {
      "finding_id": "finding-uuid-456",
      "agent_id": "relationship-validator-001",
      "timestamp": "2025-11-12T10:30:00Z",
      "severity": "high",
      "category": "duplicate_relationship",
      "title": "Duplicate relationship detected",
      "description": "Entity A has duplicate MEMBER_OF relationships to Entity B",
      "confidence_score": 0.95,
      "confidence_explanation": "Exact match on all relationship properties",
      "suggested_action": "Remove duplicate relationship",
      "priority": 8,
      "evidence": ["Relationship ID 12345", "Relationship ID 12346"],
      "affected_entities": ["entity-uuid-A", "entity-uuid-B"],
      "affected_relationships": ["12345", "12346"],
      "reviewed": false
    }
  ],
  "execution_time_seconds": 5.3,
  "success": true,
  "error_message": null,
  "markdown_report": "# Relationship Validation Report\n...",
  "corrections_applied": 0,
  "correction_batch_id": null,
  "duplicates_removed": 0,
  "semantics_standardized": 0,
  "auto_correction_enabled": false,
  "dry_run": true
}
```

**Status Codes:**

- `200`: Success
- `400`: Invalid request body
- `500`: Validation failed

---

### GET /api/v1/validate/history

Get validation report history.

**Authentication**: Required

**Query Parameters:**

- `agent_id` (optional): Filter by agent ID
- `validation_type` (optional): Filter by validation type
- `limit` (optional, default: 50): Maximum results
- `offset` (optional, default: 0): Pagination offset

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/validate/history?limit=20" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
[
  {
    "report_id": "report-uuid-123",
    "agent_id": "relationship-validator-001",
    "timestamp": "2025-11-12T10:30:00Z",
    "validation_type": "relationship_validation",
    "findings_count": 15,
    "success": true
  }
]
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

### GET /api/v1/validate/report/{report_id}

Get a specific validation report with all findings.

**Authentication**: Required

**Path Parameters:**

- `report_id`: Validation report UUID

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/validate/report/report-uuid-123 \
  -H "X-API-Key: your-api-key"
```

**Response:**
Same format as `/api/v1/validate/relationships` response.

**Status Codes:**

- `200`: Success
- `404`: Report not found
- `500`: Server error

---

### GET /api/v1/validate/findings/unreviewed

Get unreviewed validation findings for human review.

**Authentication**: Required

**Query Parameters:**

- `severity` (optional): Filter by severity (critical, high, medium, low)
- `category` (optional): Filter by category
- `agent_id` (optional): Filter by agent ID
- `limit` (optional, default: 100): Maximum results

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/validate/findings/unreviewed?severity=high&limit=50" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
[
  {
    "finding_id": "finding-uuid-456",
    "agent_id": "relationship-validator-001",
    "timestamp": "2025-11-12T10:30:00Z",
    "severity": "high",
    "category": "duplicate_relationship",
    "title": "Duplicate relationship detected",
    "description": "Entity A has duplicate relationships to Entity B",
    "confidence_score": 0.95,
    "confidence_explanation": "Exact match on properties",
    "suggested_action": "Remove duplicate",
    "priority": 8,
    "evidence": ["Relationship 12345", "Relationship 12346"],
    "affected_entities": ["entity-uuid-A"],
    "affected_relationships": ["12345", "12346"],
    "reviewed": false
  }
]
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

### POST /api/v1/validate/findings/{finding_id}/review

Mark a validation finding as reviewed by a human.

**Authentication**: Required

**Path Parameters:**

- `finding_id`: Finding UUID

**Request Body:**

```json
{
  "reviewer": "admin-user-123",
  "action": "accepted",
  "notes": "Duplicate confirmed, scheduled for removal"
}
```

**Request Fields:**

- `reviewer` (required): Name/ID of the reviewer
- `action` (required): Action taken (e.g., accepted, rejected, deferred)
- `notes` (optional): Review notes

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/validate/findings/finding-uuid-456/review \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer": "admin",
    "action": "accepted",
    "notes": "Confirmed duplicate"
  }'
```

**Response:**

```json
{
  "message": "Finding marked as reviewed",
  "finding_id": "finding-uuid-456"
}
```

**Status Codes:**

- `200`: Success
- `404`: Finding not found
- `500`: Server error

---

### GET /api/v1/validate/stats

Get validation statistics summary.

**Authentication**: Required

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/validate/stats \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "total_validations": 50,
  "total_findings": 200,
  "findings_by_severity": {
    "critical": 10,
    "high": 30,
    "medium": 80,
    "low": 80
  },
  "findings_by_category": {
    "duplicate_relationship": 50,
    "semantic_inconsistency": 40,
    "missing_property": 60,
    "other": 50
  },
  "review_stats": {
    "reviewed": 150,
    "unreviewed": 50,
    "accepted": 120,
    "rejected": 30
  }
}
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

## Correction System

### POST /api/v1/corrections/{correction_id}/rollback

Rollback a single correction.

**Authentication**: Required

**Path Parameters:**

- `correction_id`: Correction UUID

**Request Body:**

```json
{
  "rollback_by": "admin-user-123",
  "rollback_reason": "Correction was incorrect"
}
```

**Request Fields:**

- `rollback_by` (required): Who is performing the rollback
- `rollback_reason` (optional, default: "Manual rollback requested"): Reason for rollback

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/corrections/correction-uuid-123/rollback \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "rollback_by": "admin",
    "rollback_reason": "Incorrect correction"
  }'
```

**Response:**

```json
{
  "success": true,
  "message": "Correction rolled back successfully",
  "rollback_by": "admin",
  "rollback_reason": "Incorrect correction",
  "rollback_timestamp": "2025-11-12T11:00:00Z",
  "statistics": null
}
```

**Status Codes:**

- `200`: Success
- `400`: Rollback failed
- `404`: Correction not found
- `500`: Server error

---

### POST /api/v1/corrections/batch/{batch_id}/rollback

Rollback all corrections in a batch.

**Authentication**: Required

**Path Parameters:**

- `batch_id`: Correction batch UUID

**Request Body:**
Same as single correction rollback.

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/corrections/batch/batch-uuid-456/rollback \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "rollback_by": "admin",
    "rollback_reason": "Batch contained errors"
  }'
```

**Response:**

```json
{
  "success": true,
  "message": "Batch rolled back successfully",
  "rollback_by": "admin",
  "rollback_reason": "Batch contained errors",
  "rollback_timestamp": "2025-11-12T11:00:00Z",
  "statistics": {
    "corrections_rolled_back": 15,
    "entities_affected": 8,
    "relationships_affected": 12
  }
}
```

**Status Codes:**

- `200`: Success
- `400`: Rollback failed
- `404`: Batch not found
- `500`: Server error

---

### GET /api/v1/corrections/batch/{batch_id}/preview

Preview what would be rolled back in a batch.

**Authentication**: Required

**Path Parameters:**

- `batch_id`: Correction batch UUID

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/corrections/batch/batch-uuid-456/preview \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "success": true,
  "batch_id": "batch-uuid-456",
  "total_corrections": 15,
  "corrections": [
    {
      "correction_id": "correction-uuid-789",
      "correction_type": "relationship_removal",
      "affected_entity": "entity-uuid-A",
      "rollback_action": "Restore relationship"
    }
  ],
  "summary": {
    "entities_affected": 8,
    "relationships_affected": 12,
    "relationship_removals": 10,
    "property_updates": 5
  }
}
```

**Status Codes:**

- `200`: Success
- `404`: Batch not found
- `500`: Server error

---

### GET /api/v1/corrections/history

Get correction history.

**Authentication**: Required

**Query Parameters:**

- `limit` (optional, default: 100): Maximum results

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/corrections/history?limit=50" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "corrections": [
    {
      "correction_id": "correction-uuid-123",
      "batch_id": "batch-uuid-456",
      "correction_type": "relationship_removal",
      "entity_id": "entity-uuid-A",
      "applied_at": "2025-11-12T10:00:00Z",
      "status": "applied"
    }
  ],
  "total_count": 1
}
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

### GET /api/v1/corrections/stats

Get correction and rollback statistics.

**Authentication**: Required

**Query Parameters:**

- `days` (optional, default: 30): Number of days to analyze

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/corrections/stats?days=30" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "total_corrections": 250,
  "total_rollbacks": 15,
  "corrections_by_type": {
    "relationship_removal": 150,
    "property_update": 100
  },
  "corrections_by_status": {
    "applied": 235,
    "rolled_back": 15
  },
  "recent_batches": [
    {
      "batch_id": "batch-uuid-456",
      "created_at": "2025-11-12T10:00:00Z",
      "corrections_count": 15,
      "status": "applied"
    }
  ]
}
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

### GET /api/v1/corrections/{correction_id}

Get details of a specific correction.

**Authentication**: Required

**Path Parameters:**

- `correction_id`: Correction UUID

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/corrections/correction-uuid-123 \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "correction_id": "correction-uuid-123",
  "batch_id": "batch-uuid-456",
  "correction_type": "relationship_removal",
  "entity_id": "entity-uuid-A",
  "applied_at": "2025-11-12T10:00:00Z",
  "status": "applied",
  "rollback_data": {
    "relationship_id": 12345,
    "properties": {...}
  }
}
```

**Status Codes:**

- `200`: Success
- `404`: Correction not found
- `500`: Server error

---

### GET /api/v1/corrections/batch/{batch_id}/summary

Get summary of a correction batch.

**Authentication**: Required

**Path Parameters:**

- `batch_id`: Correction batch UUID

**Example Request:**

```bash
curl -X GET http://localhost:8003/api/v1/corrections/batch/batch-uuid-456/summary \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "batch_id": "batch-uuid-456",
  "created_at": "2025-11-12T10:00:00Z",
  "total_corrections": 15,
  "status": "applied",
  "corrections_by_type": {
    "relationship_removal": 10,
    "property_update": 5
  },
  "entities_affected": 8,
  "relationships_affected": 12,
  "validation_report_id": "report-uuid-123"
}
```

**Status Codes:**

- `200`: Success
- `404`: Batch not found
- `500`: Server error

---

## Chat Agent

### POST /api/v1/chat/message

Send a message to the chat agent and initiate streaming response.

**Authentication**: Required

**Request Body:**

```json
{
  "message": "Tell me about the Crystal Dwarves",
  "conversation_id": "conversation-uuid-123",
  "user_id": "user-123",
  "metadata": {},
  "engine": "langchain"
}
```

**Request Fields:**

- `message` (required): The user's message
- `conversation_id` (optional): Existing conversation ID, or null to create new
- `user_id` (optional): User identifier
- `metadata` (optional): Additional request metadata
- `engine` (optional): Chat engine to use: `langchain` (default) or `legacy`

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/chat/message \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about the Crystal Dwarves",
    "engine": "langchain"
  }'
```

**Response:**

```json
{
  "conversation_id": "conversation-uuid-123",
  "stream_url": "/api/v1/chat/stream/stream-id-456",
  "stream_id": "stream-id-456",
  "message_id": "message-uuid-789"
}
```

**Status Codes:**

- `200`: Success
- `400`: Invalid request (empty message)
- `404`: Conversation not found (if conversation_id provided)
- `500`: Server error

---

### GET /api/v1/chat/stream/{stream_id}

Server-Sent Events (SSE) endpoint for streaming chat responses.

**Authentication**: Required (via query parameter for SSE compatibility)

**Path Parameters:**

- `stream_id`: Stream session ID from `/api/v1/chat/message`

**Query Parameters:**

- `trace` (optional, default: 0): Include trace events if set to 1

**Example Request:**

```javascript
const eventSource = new EventSource(
  "http://localhost:8003/api/v1/chat/stream/stream-id-456?trace=1",
  { headers: { "X-API-Key": "your-api-key" } },
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**Event Types:**

**Route Announcement:**

```json
{
  "type": "route",
  "route": "direct_answer",
  "confidence": 0.95
}
```

**Token Streaming:**

```json
{
  "type": "token",
  "content": "The Crystal Dwarves"
}
```

**Retrieval Preview (trace=1):**

```json
{
  "type": "trace",
  "retrieval_preview": {
    "blocks": ["Context block 1", "Context block 2"],
    "entities": ["Crystal Dwarves", "Crystal Mountains"]
  }
}
```

**Final Response:**

```json
{
  "type": "final",
  "answer": "Complete answer text...",
  "route": "direct_answer",
  "confidence": 0.95
}
```

**Error:**

```json
{
  "type": "error",
  "content": "Error message",
  "timestamp": "2025-11-12T11:00:00Z"
}
```

**Status Codes:**

- `200`: Streaming initiated
- `404`: Stream session not found

---

### GET /api/v1/chat/conversations

List user conversations with pagination.

**Authentication**: Required

**Query Parameters:**

- `user_id` (optional): Filter by user ID
- `limit` (optional, default: 50, max: 100): Results per page
- `offset` (optional, default: 0): Pagination offset

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/chat/conversations?limit=20" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "conversations": [
    {
      "id": "conversation-uuid-123",
      "user_id": "user-123",
      "created_at": "2025-11-12T10:00:00Z",
      "updated_at": "2025-11-12T10:30:00Z",
      "metadata": {
        "engine": "langchain"
      }
    }
  ]
}
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

### GET /api/v1/chat/conversations/{conversation_id}

Get conversation history with messages.

**Authentication**: Required

**Path Parameters:**

- `conversation_id`: Conversation UUID

**Query Parameters:**

- `limit` (optional, default: 100, max: 200): Maximum messages
- `offset` (optional, default: 0): Pagination offset

**Example Request:**

```bash
curl -X GET "http://localhost:8003/api/v1/chat/conversations/conversation-uuid-123?limit=50" \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "conversation": {
    "id": "conversation-uuid-123",
    "user_id": "user-123",
    "created_at": "2025-11-12T10:00:00Z",
    "updated_at": "2025-11-12T10:30:00Z",
    "metadata": {
      "engine": "langchain"
    }
  },
  "messages": [
    {
      "id": "message-uuid-456",
      "message_type": "user",
      "content": "Tell me about the Crystal Dwarves",
      "created_at": "2025-11-12T10:00:00Z",
      "metadata": {},
      "tools_used": null
    },
    {
      "id": "message-uuid-789",
      "message_type": "assistant",
      "content": "The Crystal Dwarves are...",
      "created_at": "2025-11-12T10:00:05Z",
      "metadata": {
        "engine": "langchain",
        "route": "direct_answer"
      },
      "tools_used": ["hybrid_rag_tool"]
    }
  ]
}
```

**Status Codes:**

- `200`: Success
- `404`: Conversation not found
- `500`: Server error

---

### DELETE /api/v1/chat/conversations/{conversation_id}

Delete a conversation and all its messages.

**Authentication**: Required

**Path Parameters:**

- `conversation_id`: Conversation UUID

**Example Request:**

```bash
curl -X DELETE http://localhost:8003/api/v1/chat/conversations/conversation-uuid-123 \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "message": "Conversation deleted successfully"
}
```

**Status Codes:**

- `200`: Success
- `404`: Conversation not found
- `500`: Server error

---

### POST /api/v1/chat/cleanup

Clean up expired stream sessions (maintenance endpoint).

**Authentication**: Required

**Example Request:**

```bash
curl -X POST http://localhost:8003/api/v1/chat/cleanup \
  -H "X-API-Key: your-api-key"
```

**Response:**

```json
{
  "message": "Cleaned up 5 expired stream sessions"
}
```

**Status Codes:**

- `200`: Success
- `500`: Server error

---

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "detail": {
    "error": "error_type",
    "message": "Human-readable error message",
    "stage": "operation_stage",
    "context": {}
  }
}
```

For simple errors:

```json
{
  "detail": "Simple error message"
}
```

### Common HTTP Status Codes

- `200 OK`: Success
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

### Common Error Types

- `unauthorized`: Missing or invalid API key
- `invalid_request`: Malformed request data
- `not_found`: Resource not found
- `server_error`: Internal server error
- `service_unavailable`: Dependency unavailable
- `chat_message_failed`: Chat message processing failed
- `validation_failed`: Validation operation failed

### Error Examples

**Authentication Error:**

```json
{
  "detail": "Invalid API key"
}
```

**Validation Error:**

```json
{
  "detail": {
    "error": "validation_failed",
    "message": "Invalid request body",
    "context": {
      "field": "limit",
      "error": "Must be between 1 and 100"
    }
  }
}
```

**Not Found Error:**

```json
{
  "detail": "Entity not found with ID: entity-uuid-123"
}
```

---

## Code Examples

### Python

**Basic RAG Query:**

```python
import requests

API_KEY = "your-api-key"
BASE_URL = "http://localhost:8003"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Execute RAG query
response = requests.post(
    f"{BASE_URL}/api/v1/rag/query",
    json={
        "query": "Tell me about the Crystal Dwarves",
        "limit": 5
    },
    headers=headers
)

data = response.json()
print(f"Found {data['total_results']} results")
for chunk in data['chunks']:
    print(f"- {chunk['text'][:100]}...")
```

**Chat with Streaming:**

```python
import requests
import json

# Start chat
response = requests.post(
    f"{BASE_URL}/api/v1/chat/message",
    json={"message": "Tell me about the Sundering"},
    headers=headers
)

stream_url = response.json()["stream_url"]

# Stream response
stream = requests.get(
    f"{BASE_URL}{stream_url}",
    headers=headers,
    stream=True
)

for line in stream.iter_lines():
    if line:
        if line.startswith(b'data: '):
            data = json.loads(line[6:])
            if data['type'] == 'token':
                print(data['content'], end='', flush=True)
            elif data['type'] == 'final':
                print(f"\n\nRoute: {data['route']}")
```

**Entity Search:**

```python
# Search entities
response = requests.get(
    f"{BASE_URL}/api/v1/entities/search",
    params={"query": "crystal", "limit": 10},
    headers=headers
)

entities = response.json()
for entity in entities:
    print(f"{entity['name']} ({entity['type']}): {entity['description']}")
```

---

### JavaScript (Node.js)

**Basic RAG Query:**

```javascript
const fetch = require("node-fetch");

const API_KEY = "your-api-key";
const BASE_URL = "http://localhost:8003";

const headers = {
  "X-API-Key": API_KEY,
  "Content-Type": "application/json",
};

// Execute RAG query
async function queryLore(query) {
  const response = await fetch(`${BASE_URL}/api/v1/rag/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, limit: 5 }),
  });

  const data = await response.json();
  console.log(`Found ${data.total_results} results`);

  data.chunks.forEach((chunk) => {
    console.log(`- ${chunk.text.substring(0, 100)}...`);
  });
}

queryLore("Tell me about the Crystal Dwarves");
```

**Chat with EventSource:**

```javascript
const EventSource = require("eventsource");

async function chat(message) {
  // Start chat
  const response = await fetch(`${BASE_URL}/api/v1/chat/message`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });

  const { stream_url } = await response.json();

  // Stream response
  const eventSource = new EventSource(`${BASE_URL}${stream_url}`, {
    headers: { "X-API-Key": API_KEY },
  });

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "token") {
      process.stdout.write(data.content);
    } else if (data.type === "final") {
      console.log(`\n\nRoute: ${data.route}`);
      eventSource.close();
    }
  };

  eventSource.onerror = (error) => {
    console.error("Stream error:", error);
    eventSource.close();
  };
}

chat("Tell me about the Sundering");
```

---

### cURL

**Health Check:**

```bash
curl -X GET http://localhost:8003/api/v1/health \
  -H "X-API-Key: your-api-key"
```

**RAG Query:**

```bash
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the Sundering?",
    "limit": 5
  }'
```

**Entity Search:**

```bash
curl -X GET "http://localhost:8003/api/v1/entities/search?query=dwarf&limit=10" \
  -H "X-API-Key: your-api-key"
```

**Validate Relationships:**

```bash
curl -X POST http://localhost:8003/api/v1/validate/relationships \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_limit": 100,
    "dry_run": true
  }'
```

**Start Chat:**

```bash
curl -X POST http://localhost:8003/api/v1/chat/message \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about the Crystal Dwarves",
    "engine": "langchain"
  }'
```

**Get System Stats:**

```bash
curl -X GET http://localhost:8003/api/v1/stats \
  -H "X-API-Key: your-api-key"
```

---

## Additional Resources

- **[Developer Guide](./DEVELOPER_GUIDE.md)**: Implementation details and development patterns
- **[Agent System](./AGENT_SYSTEM.md)**: Agent architecture and workflows
- **[Validation System](./VALIDATION_AGENT_GUIDE.md)**: Validation system details
- **[Deployment Guide](./DEPLOYMENT_GUIDE.md)**: Production deployment instructions
- **[OpenAPI Docs](http://localhost:8003/docs)**: Interactive API documentation
- **[ReDoc](http://localhost:8003/redoc)**: Alternative API documentation

---

**Last Updated**: 2025-11-12
**Version**: 0.7.10
**Status**: Production Ready
