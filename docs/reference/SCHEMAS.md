# Database Schemas Reference

**Version**: 0.7.3
**Status**: Production Ready  
**Last Updated**: 2025-11-12

Complete reference for PostgreSQL and Neo4j database schemas used in Luminari Sage.

---

## Table of Contents

- [Overview](#overview)
- [PostgreSQL Schema](#postgresql-schema)
- [Neo4j Schema](#neo4j-schema)
- [Schema Design Principles](#schema-design-principles)
- [Query Patterns](#query-patterns)
- [Performance Optimizations](#performance-optimizations)
- [Maintenance](#maintenance)

---

## Overview

### Hybrid Database Architecture

Luminari Sage uses a hybrid database architecture that leverages the strengths of both PostgreSQL and Neo4j:

- **PostgreSQL + pgvector**: Document storage, full-text search, and vector embeddings
- **Neo4j**: Knowledge graph with entities and relationships

### Why This Split?

1. **Neo4j for Graphs**
   - Native graph traversals (100x faster than SQL joins)
   - Cypher query language designed for relationships
   - Pattern matching and pathfinding algorithms
   - Visual graph exploration tools

2. **PostgreSQL + pgvector for Documents/Vectors**
   - Unified storage reduces complexity
   - ACID transactions for document integrity
   - Excellent full-text search capabilities
   - pgvector performance rivals dedicated vector DBs
   - Single backup/restore process

### Data Flow

```mermaid
graph LR
    MD[Markdown Files] --> LOAD[load_documents.py]
    LOAD --> PG[PostgreSQL]
    PG --> EXTRACT[extract_entities.py]
    EXTRACT --> GRAPHITI[Graphiti]
    GRAPHITI --> N4J[Neo4j]
    PG --> |Embeddings| SEARCH[Hybrid Search]
    N4J --> |Graph Context| SEARCH
```

---

## PostgreSQL Schema

### Extensions

Required PostgreSQL extensions:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- Cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Trigram similarity search
CREATE EXTENSION IF NOT EXISTS "btree_gist";     -- Advanced indexing
CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector for embeddings
```

### Core Tables

#### 1. lore_documents

Full markdown document storage with metadata.

```sql
CREATE TABLE lore_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stable_id VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    document_type document_type NOT NULL,
    source_file VARCHAR(500) NOT NULL,
    body_md TEXT NOT NULL,
    summary TEXT,
    canonical BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    indexed_at TIMESTAMPTZ,
    
    -- Pipeline processing
    processing_status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    
    -- Graphiti processing
    graphiti_status TEXT DEFAULT 'pending',
    graphiti_content_hash TEXT,
    graphiti_processed_at TIMESTAMP,
    
    -- Full-text search vector
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(body_md, '')), 'C')
    ) STORED
);
```

**Key Fields**:
- `stable_id`: ULID/KSUID for cross-database references
- `document_type`: Enum (codex, chronicle, lore_note, etc.)
- `graphiti_status`: Processing state (pending, processing, completed, failed)
- `search_vector`: Auto-generated full-text search vector

#### 2. episodes

Semantic chunks for Graphiti integration (replaces `chunks` in hybrid RAG).

```sql
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES lore_documents(id) ON DELETE CASCADE,
    episode_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(384),   -- sentence-transformers (change to 1536 for OpenAI)
    graphiti_synced BOOLEAN DEFAULT FALSE,
    graphiti_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    entity_refs JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT episodes_document_episode_unique UNIQUE(document_id, episode_index)
);
```

**Key Fields**:
- `episode_index`: Position within document
- `embedding`: 384-dim vector (MiniLM) or 1536-dim (OpenAI)
- `graphiti_synced`: Whether synced to Neo4j via Graphiti
- `entity_refs`: JSONB array of entity references

#### 3. validation_reports

Validation report metadata from validation agents.

```sql
CREATE TABLE validation_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id VARCHAR(255) UNIQUE NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Report details
    validation_type VARCHAR(255) NOT NULL,
    scope_description TEXT NOT NULL,
    total_items_checked INTEGER NOT NULL DEFAULT 0,
    
    -- Summary statistics
    findings_count INTEGER NOT NULL DEFAULT 0,
    severity_counts JSONB NOT NULL DEFAULT '{}',
    category_counts JSONB NOT NULL DEFAULT '{}',
    
    -- Execution details
    execution_time_seconds DECIMAL(10, 3) NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    markdown_report TEXT,
    metadata JSONB DEFAULT '{}'
);
```

#### 4. validation_findings

Individual validation findings with review tracking.

```sql
CREATE TABLE validation_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id VARCHAR(255) UNIQUE NOT NULL,
    report_id UUID NOT NULL REFERENCES validation_reports(id) ON DELETE CASCADE,
    agent_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Finding classification
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    category VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    
    -- Evidence and confidence
    confidence_score DECIMAL(3, 2) NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    confidence_explanation TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]',
    
    -- Suggested actions
    suggested_action TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority >= 1 AND priority <= 5),
    
    -- Affected items
    affected_entities JSONB NOT NULL DEFAULT '[]',
    affected_relationships JSONB NOT NULL DEFAULT '[]',
    
    -- Human review tracking
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewer VARCHAR(255),
    review_timestamp TIMESTAMP WITH TIME ZONE,
    review_action VARCHAR(255),
    review_notes TEXT,
    
    metadata JSONB DEFAULT '{}'
);
```

#### 5. relationship_corrections

Complete audit trail for relationship corrections with rollback support.

```sql
CREATE TABLE relationship_corrections (
    correction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    validation_report_id UUID REFERENCES validation_reports(id),
    correction_batch_id UUID NOT NULL,
    
    -- Correction metadata
    correction_type TEXT NOT NULL CHECK (correction_type IN ('DEDUPLICATION', 'SEMANTIC_STANDARDIZATION')),
    action TEXT NOT NULL CHECK (action IN ('DELETE', 'UPDATE')),
    confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    agent_reasoning TEXT NOT NULL,
    
    -- Neo4j relationship identification
    relationship_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_node_name TEXT,
    target_node_name TEXT,
    source_node_labels TEXT[],
    target_node_labels TEXT[],
    
    -- Complete relationship backup
    original_properties JSONB NOT NULL,
    new_properties JSONB,
    
    -- Semantic type tracking
    original_semantic_type TEXT,
    new_semantic_type TEXT,
    duplicate_count INTEGER,
    
    -- Audit timestamps
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Rollback tracking
    rolled_back BOOLEAN DEFAULT FALSE,
    rollback_at TIMESTAMP WITH TIME ZONE,
    rollback_by TEXT,
    rollback_reason TEXT,
    
    metadata JSONB DEFAULT '{}'::jsonb
);
```

### Enums

```sql
CREATE TYPE document_type AS ENUM (
    'codex',           -- Core reference documents
    'chronicle',       -- Historical documents
    'lore_note',       -- World-building notes
    'map_note',        -- Geographic descriptions
    'quest',           -- Quest and adventure content
    'character_bio',   -- Character backstories
    'misc'            -- Other document types
);

CREATE TYPE confidence_level AS ENUM (
    'canonical',      -- 100% confirmed
    'high',          -- 80-99% confidence
    'medium',        -- 60-79% confidence
    'low',           -- 40-59% confidence
    'speculative'    -- <40% confidence
);

CREATE TYPE validation_status AS ENUM (
    'pending',
    'valid',
    'warning',
    'error',
    'conflict'
);
```

### Key Indexes

```sql
-- Vector similarity indexes
CREATE INDEX idx_episodes_embedding ON episodes
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Full-text search
CREATE INDEX idx_documents_search ON lore_documents 
USING GIN (search_vector);

-- JSONB indexes
CREATE INDEX idx_episodes_entity_refs ON episodes USING GIN(entity_refs);

-- Performance indexes
CREATE INDEX idx_episodes_document_id ON episodes(document_id);
CREATE INDEX idx_episodes_graphiti_synced ON episodes(graphiti_synced) WHERE graphiti_synced = FALSE;
```

### Useful Functions

#### search_episodes()

Semantic vector search on episodes:

```sql
-- Usage example
SELECT * FROM search_episodes(
    query_embedding := $embedding_vector,
    limit_count := 10,
    similarity_threshold := 0.7
);
```

#### hybrid_search()

Combines vector similarity and full-text search:

```sql
-- Combines vector and keyword search with weighted scoring
SELECT * FROM hybrid_search(
    query_text := 'crystal dwarves',
    query_embedding := $embedding,
    limit_count := 10,
    vector_weight := 0.7  -- 70% vector, 30% keyword
);
```

### Views

```sql
-- Active corrections (not rolled back)
CREATE VIEW active_corrections AS
SELECT correction_id, correction_type, action, confidence_score,
       relationship_id, source_node_name, target_node_name,
       applied_at
FROM relationship_corrections
WHERE NOT rolled_back
ORDER BY applied_at DESC;

-- Document statistics
CREATE VIEW document_stats AS
SELECT d.id, d.title, d.document_type,
       COUNT(DISTINCT e.id) as episode_count,
       AVG(length(e.text)) as avg_episode_length,
       MAX(e.created_at) as last_indexed
FROM lore_documents d
LEFT JOIN episodes e ON e.document_id = d.id
GROUP BY d.id, d.title, d.document_type;
```

---

## Neo4j Schema

### Core Design Principles

- **Node Labels**: Hierarchical (`:Deity:Entity`) for inheritance
- **Properties**: Core attributes on nodes, metadata in `attrs` map
- **Relationships**: Typed and directional with properties
- **Indexes**: Unique constraints on IDs, full-text on searchable fields

### Node Types

#### Base Entity Node

All entity types inherit from `:Entity`:

```cypher
(:Entity {
  uuid: String!           // Graphiti-generated UUID
  name: String!           
  name_embedding: List<Float>  // Name vector embedding
  summary: String
  summary_embedding: List<Float>
  created_at: DateTime!
  updated_at: DateTime!
})
```

#### Specific Entity Types

Graphiti creates specialized entity types based on lore content:

```cypher
// Divine beings
(:Deity:Entity)

// Named individuals  
(:Person:Entity)

// Organizations
(:Organization:Entity)

// Political/military groups
(:Faction:Entity)

// Geographic locations
(:Location:Entity)

// Species/ethnicities
(:Race:Entity)

// Monsters and beasts
(:Creature:Entity)

// Spells and magical systems
(:Magic:Entity)

// Magical items
(:Artifact:Entity)

// Historical occurrences
(:Event:Entity)

// Abstract ideas
(:Concept:Entity)

// Predictions and omens
(:Prophecy:Entity)

// Planes and dimensions
(:Realm:Entity)
```

#### Episodic Node

Links to PostgreSQL episodes:

```cypher
(:Episodic {
  uuid: String!
  stable_id: String!      // Maps to episodes.id in PostgreSQL
  content: String!
  created_at: DateTime!
  valid_at: DateTime!
  expired_at: DateTime
  embedding: List<Float>
})
```

### Relationship Types

#### Graphiti Standard Relationships

```cypher
// Entity mentions in episodes
(:Entity)-[:MENTIONS {created_at, fact_ids}]->(:Episodic)

// Semantic relationships between entities
(:Entity)-[:RELATES_TO {
  semantic_type: String,   // e.g., "Commands", "AlliedWith", "OpposedTo"
  fact: String,
  valid_at: DateTime,
  expired_at: DateTime,
  created_at: DateTime
}]->(:Entity)
```

#### Semantic Relationship Types

The `semantic_type` property on `RELATES_TO` edges includes:

| Semantic Type | Usage |
|--------------|--------|
| Commands | Authority relationships (Leaders → Organizations) |
| ServesUnder | Service relationships (Knights → Orders) |
| AlliedWith | Alliance relationships (Factions ↔ Factions) |
| OpposedTo | Conflict relationships (Good ↔ Evil) |
| Influences | Influence relationships (Deities → Mortals) |
| CreatedBy | Creation relationships (Artifacts ← Creators) |
| TransformedInto | Change relationships (Races → New Forms) |
| DescendedFrom | Heritage relationships (People ← Ancestors) |
| BoundTo | Binding relationships (Souls ↔ Artifacts) |
| Protects | Protection relationships (Orders → Locations) |
| Corrupts | Corruption relationships (Evil → Good) |
| TeachesTo | Knowledge relationships (Masters → Students) |
| Embodies | Representation relationships (Concepts ↔ Entities) |

### Constraints and Indexes

```cypher
// Unique constraints
CREATE CONSTRAINT entity_uuid IF NOT EXISTS
FOR (e:Entity) REQUIRE e.uuid IS UNIQUE;

CREATE CONSTRAINT episodic_uuid IF NOT EXISTS
FOR (ep:Episodic) REQUIRE ep.uuid IS UNIQUE;

// Performance indexes
CREATE INDEX entity_name IF NOT EXISTS
FOR (e:Entity) ON (e.name);

CREATE INDEX episodic_stable_id IF NOT EXISTS
FOR (ep:Episodic) ON (ep.stable_id);

// Full-text search
CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
FOR (e:Entity) ON EACH [e.name, e.summary];
```

---

## Schema Design Principles

### 1. Stable IDs for Cross-Database References

- PostgreSQL `episodes.id` maps to Neo4j `Episodic.stable_id`
- Use UUIDs consistently across both databases
- Never use internal database IDs for cross-references

### 2. Embedding Storage Strategy

- **PostgreSQL**: Store document/episode embeddings for retrieval
- **Neo4j**: Store entity name/summary embeddings for graph search
- Use consistent embedding model across both databases

### 3. Metadata Flexibility

- PostgreSQL: Use JSONB columns for extensible metadata
- Neo4j: Use `attrs` or `metadata` properties as maps
- Document metadata schema in application code

### 4. Confidence Tracking

- Track confidence scores for entity mentions
- Store evidence in JSONB for traceability
- Use confidence to filter low-quality data

### 5. Audit Trails

- All corrections include complete backup data
- Rollback capability without data loss
- Track who/when/why for all changes

---

## Query Patterns

### PostgreSQL Queries

#### Semantic Search

```sql
-- Find similar episodes by vector similarity
SELECT id, text, 1 - (embedding <=> $query_embedding) as similarity
FROM episodes
WHERE 1 - (embedding <=> $query_embedding) > 0.7
ORDER BY embedding <=> $query_embedding
LIMIT 10;
```

#### Full-Text Search

```sql
-- Full-text search on documents
SELECT id, title, ts_rank(search_vector, query) as rank
FROM lore_documents, plainto_tsquery('english', $query) query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 10;
```

#### Hybrid RAG Query

```sql
-- Combine vector and full-text with RRF scoring
WITH vector_results AS (
  SELECT id, 1 - (embedding <=> $query_embedding) as score
  FROM episodes
  ORDER BY embedding <=> $query_embedding
  LIMIT 20
),
fts_results AS (
  SELECT e.id, ts_rank(to_tsvector('english', e.text), query) as score
  FROM episodes e, plainto_tsquery('english', $query_text) query
  WHERE to_tsvector('english', e.text) @@ query
  LIMIT 20
)
-- Reciprocal Rank Fusion
SELECT COALESCE(v.id, f.id) as id,
       (COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + f.rank), 0)) as rrf_score
FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) as rank FROM vector_results) v
FULL OUTER JOIN (SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) as rank FROM fts_results) f
  ON v.id = f.id
ORDER BY rrf_score DESC
LIMIT 10;
```

### Neo4j Queries

#### Find Entity with Relationships

```cypher
MATCH (e:Entity {name: $name})
OPTIONAL MATCH (e)-[r:RELATES_TO]->(connected:Entity)
RETURN e.name, e.summary,
       collect({
         type: r.semantic_type,
         target: connected.name,
         fact: r.fact
       }) as relationships
```

#### Search Entities by Name

```cypher
CALL db.index.fulltext.queryNodes('entity_search', $query)
YIELD node, score
RETURN node.name, node.summary, score
ORDER BY score DESC
LIMIT 10
```

#### Find Related Entities (2-hop)

```cypher
MATCH (e:Entity {name: $name})-[r1:RELATES_TO]->(e2:Entity)
OPTIONAL MATCH (e2)-[r2:RELATES_TO]->(e3:Entity)
WHERE e3 <> e
RETURN e.name as source,
       collect(DISTINCT e2.name) as direct_connections,
       collect(DISTINCT e3.name) as indirect_connections
```

#### Get Episode Context

```cypher
MATCH (e:Entity {name: $name})-[:MENTIONS]->(ep:Episodic)
RETURN ep.stable_id, ep.content, ep.created_at
ORDER BY ep.created_at DESC
LIMIT 5
```

---

## Performance Optimizations

### PostgreSQL Performance

1. **Vector Index Tuning**
   ```sql
   -- Adjust lists parameter based on data size
   -- Rule of thumb: lists = sqrt(row_count)
   CREATE INDEX idx_episodes_embedding ON episodes
   USING ivfflat (embedding vector_cosine_ops)
   WITH (lists = 100);  -- Tune this value
   ```

2. **Partial Indexes**
   ```sql
   -- Index only unsynced episodes
   CREATE INDEX idx_episodes_unsynced ON episodes(graphiti_synced)
   WHERE graphiti_synced = FALSE;
   ```

3. **ANALYZE for Query Planning**
   ```sql
   -- Run after bulk inserts
   ANALYZE episodes;
   ANALYZE lore_documents;
   ```

### Neo4j Performance

1. **Indexed Properties**
   ```cypher
   // Add indexes on frequently queried properties
   CREATE INDEX entity_type IF NOT EXISTS
   FOR (e:Entity) ON (e.entity_type);
   ```

2. **Query Profiling**
   ```cypher
   // Use PROFILE to analyze query performance
   PROFILE
   MATCH (e:Entity)-[r:RELATES_TO]->(connected)
   WHERE e.name = $name
   RETURN e, r, connected
   ```

3. **Limit Relationship Traversals**
   ```cypher
   // Use depth limits to prevent expensive queries
   MATCH path = (e:Entity)-[:RELATES_TO*1..2]->(connected)
   WHERE e.name = $name
   RETURN path
   ```

---

## Maintenance

### Regular Maintenance Tasks

#### PostgreSQL

```sql
-- Vacuum and analyze (run weekly)
VACUUM ANALYZE episodes;
VACUUM ANALYZE lore_documents;
VACUUM ANALYZE validation_findings;

-- Reindex vector indexes (run monthly)
REINDEX INDEX idx_episodes_embedding;

-- Check index bloat
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### Neo4j

```cypher
// Check database statistics
CALL db.stats.retrieve('GRAPH COUNTS');

// Find orphaned nodes
MATCH (n)
WHERE NOT (n)--()
RETURN labels(n), count(n);

// Check index usage
CALL db.indexes() YIELD name, type, state, populationPercent;
```

### Backup Procedures

See [Deployment Guide](../guides/DEPLOYMENT_GUIDE.md) for complete backup and recovery procedures.

---

## Related Documentation

- [Architecture Overview](ARCHITECTURE.md)
- [Pipeline System](../systems/PIPELINE_SYSTEM.md)
- [API Reference](API_REFERENCE.md)
- [Developer Guide](../development/DEVELOPER_GUIDE.md)
