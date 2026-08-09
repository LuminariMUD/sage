# Pipeline System

**Version**: 0.7.30
**Status**: Production Ready
**Last Updated**: 2026-08-09

A fail-closed ingestion pipeline that processes Markdown files exclusively from
`lore_docs/canon` into the hybrid Graph RAG system. Drafts, meta documentation,
text files, PDFs, and reference material are outside the production corpus.

---

## Table of Contents

- [Quick Start](#quick-start)
- [System Overview](#system-overview)
- [Pipeline Architecture](#pipeline-architecture)
- [Data Flow](#data-flow)
- [Database Schema](#database-schema)
- [Processing Operations](#processing-operations)
- [Monitoring & Troubleshooting](#monitoring--troubleshooting)
- [Maintenance & Recovery](#maintenance--recovery)
- [Advanced Operations](#advanced-operations)

---

## Quick Start

```bash
# Process newly added canon documents through PostgreSQL, embeddings, and Neo4j.
# The exact confirmation is required because graph sync can call the configured
# provider and mutate durable graph state.
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC

# Resume interrupted processing
make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC

# For detailed output, add VERBOSE=1
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1
```

### Adding a new canon document

The current pipeline has a clean additive path for a brand-new Markdown file:

1. Add the file beneath `lore_docs/canon/`, normally in the matching category
   directory such as `characters/`, `factions/`, or `locations/`.
2. Run the confirmed full pipeline:

   ```bash
   make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
   ```

3. Verify the relational, embedding, and graph stages:

   ```bash
   make status
   make embedding-status
   make graph-sync-status
   ```

The loader skips unchanged files, episode creation selects unprocessed documents,
embedding generation selects episodes without vectors, and the durable graph worker
selects unsynchronized episodes. Re-running the command is therefore safe for the
additive case.

This guarantee does **not** extend to editing, shortening, renaming, or deleting an
existing canon file. The loader notices an edit, but the current episode and graph
state is not fully reconciled. See the
[incremental canon sync plan](../ongoing_projects/incremental_canon_sync_plan.md)
for the proposed full lifecycle.

---

## System Overview

The pipeline consists of three main stages:

1. **Document Loading** (`load_documents.py`)
   - Scans only `lore_docs/canon`
   - Rejects path and symlink escapes from that directory
   - Tracks changes via content hashing
   - Stores in PostgreSQL with metadata

2. **Episode Creation and Embeddings**
   - Splits newly loaded documents into semantic episodes
   - Generates vectors only for canon episodes missing embeddings
   - Enforces the active embedding profile and physical vector-space preflight

3. **Durable Graph Sync** (`sync_episodes_to_graphiti.py`)
   - Selects eligible canon episodes that have not been synchronized
   - Requires explicit operator confirmation before provider calls or graph writes
   - Uses Graphiti to extract entities and relationships into Neo4j
   - Records durable attempts and supports bounded retry/resume

### Architecture Diagram

```mermaid
graph TB
    A[Markdown Files<br/>lore_docs/canon only] --> B[load_documents.py]
    B --> C[PostgreSQL<br/>lore_documents table]
    C --> D[create_episodes_from_documents.py]
    D --> E[PostgreSQL<br/>episodes table]
    E --> F[generate_embeddings.py<br/>pgvector]
    E --> H[sync_episodes_to_graphiti.py]
    H --> I[Graphiti<br/>Entity Extraction]
    I --> J[Neo4j<br/>Knowledge Graph]
    F --> G[RAG API<br/>Search & Generation]
    J --> G
```

---

## Pipeline Architecture

### Key Features

#### Simplified Design

- **One corpus root**: Only resolved Markdown paths beneath `lore_docs/canon`
- **No priorities**: All canon documents are processed equally
- **Dynamic document types**: Based on directory structure (`world`, `cultures`, `factions`, etc.)

#### Robust Processing

- **Incremental additions**: New documents flow through only their missing stages;
  unchanged inputs are skipped
- **Restartable**: Use the confirmed `make resume` command to continue after interruption
- **Error recovery**: Failed documents can be retried on next run
- **Change detection**: Content hashing prevents unnecessary reloads, but edits,
  renames, and deletions are not yet fully reconciled downstream

#### Clean Output

- **Default mode**: Clean progress bars and summaries
- **Verbose mode**: Add `VERBOSE=1` for detailed debug output including LLM prompts
- **Rich UI**: Uses Rich library for beautiful terminal output

### Directory Structure

The pipeline expects this repository structure:

```
<repository>/lore_docs/
├── canon/              # Approved lore (empty initially)
│   ├── world/
│   ├── cultures/
│   ├── factions/
│   ├── characters/
│   ├── timeline/
│   └── locations/
├── drafts/             # Draft lore content
│   ├── world/
│   ├── cultures/
│   ├── factions/
│   ├── characters/
│   ├── timeline/
│   ├── locations/
│   └── uncategorized/
└── meta/               # Project metadata (skipped)
```

### Document Types

Documents are automatically categorized by directory:

| Directory        | Document Type |
| ---------------- | ------------- |
| `world/`         | worldbuilding |
| `cultures/`      | culture       |
| `factions/`      | faction       |
| `characters/`    | character     |
| `timeline/`      | chronicle     |
| `locations/`     | location      |
| `uncategorized/` | misc          |
| _(other)_        | lore          |

---

## Data Flow

### 1. Document Ingestion

- **Input**: Markdown files beneath `lore_docs/canon`
- **Process**: `load_documents.py` scans canon recursively and rejects path escapes
- **Output**: Documents stored in PostgreSQL `lore_documents` table
- **Change Detection**: SHA-256 content hashing prevents reloading unchanged files

### 2. Episode Creation

- **Input**: Newly loaded canon documents whose `processing_status` is not complete
- **Process**: `create_episodes_from_documents.py` applies semantic chunking
- **Output**: Ordered episode rows in PostgreSQL

### 3. Embedding Generation

- **Input**: Canon episode text missing an embedding
- **Process**: The explicitly configured application embedding profile after a
  clean profile/dimension/index preflight
- **Output**: Profile-specific vectors in the active PostgreSQL episode space
- **Safety**: A configured/stored/physical profile mismatch blocks before adapter
  construction or any provider request

### 4. Durable Graph Sync

- **Input**: Canon episodes with eligible durable graph-sync jobs
- **Process**: `sync_episodes_to_graphiti.py` uses the confirmed durable Graphiti worker
- **Output**: Entities and relationships in Neo4j knowledge graph

### 5. RAG Integration

- **Hybrid Search**: Combines vector similarity and graph traversal
- **Context Assembly**: Uses both document content and entity relationships
- **Response Generation**: LLM-powered answers with source attribution

### Content Hashing

Change detection uses SHA-256 hashing:

```python
def calculate_content_hash(self, content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()
```

For a new file, the hash is stored with the new document and every downstream
artifact is created normally. For an existing file, the hash comparison updates
the document row and legacy `graphiti_status`, but it does not currently invalidate
or retire all previously created episodes, embeddings, and graph facts. Do not
interpret the detected hash change as end-to-end reconciliation.

### Chunking Strategy

Large documents are split intelligently:

```python
# Token-based chunking with semantic overlap
chunk_size = min(450, token_count // 2 + 100)
overlap = max(60, int(chunk_size * 0.15))  # 15% overlap minimum
```

This ensures:

- Optimal LLM context usage
- Semantic continuity between chunks
- Efficient entity extraction

---

## Database Schema

### PostgreSQL (`lore_documents`)

```sql
CREATE TABLE lore_documents (
    id UUID PRIMARY KEY,
    stable_id TEXT UNIQUE,
    title TEXT,
    document_type TEXT,
    source_file TEXT UNIQUE,
    body_md TEXT,
    summary TEXT,
    canonical BOOLEAN,
    metadata JSONB,
    graphiti_status TEXT DEFAULT 'pending',
    graphiti_content_hash TEXT,
    graphiti_processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Neo4j Schema

Graphiti manages the Neo4j schema automatically with:

- **Entity nodes**: Extracted people, places, concepts, etc.
- **Relationship edges**: Semantic connections between entities
- **Episode nodes**: Links back to source document chunks
- **Community detection**: Hierarchical entity groupings

### Processing States

There is no single four-state document lifecycle for the complete pipeline. Each
stage has its own eligibility signal:

1. **Episode creation** uses `lore_documents.processing_status`; new documents are
   eligible until marked `completed`.
2. **Embedding generation** selects active canon episodes whose `embedding` is
   `NULL`.
3. **Durable graph sync** uses authoritative `graph_sync_jobs` states:
   `pending`, `leased`, `retry_wait`, `quarantined`, and `synced`.
4. `lore_documents.graphiti_status` is legacy, while `episodes.graphiti_synced` is
   a compatibility projection; neither is the durable graph job authority.

The confirmed `make resume` command runs episode creation, embedding generation,
and durable graph sync for already loaded documents; it does not scan the
filesystem. Use the full `pipeline-canon` command after adding a new file.

### Entity Types

The system recognizes 13 entity types optimized for fantasy lore:

| Type         | Description                | Examples              |
| ------------ | -------------------------- | --------------------- |
| Deity        | Gods and divine beings     | Paladine, Takhisis    |
| Person       | Named individuals          | Sturm Brightblade     |
| Organization | Groups and orders          | Knights of Solamnia   |
| Race         | Species and ethnicities    | Elves, Dwarves        |
| Faction      | Political/military groups  | Dragonarmies          |
| Location     | Places and regions         | Krynn, Palanthas      |
| Creature     | Monsters and beasts        | Dragons, Draconians   |
| Magic        | Spells and magical systems | Wizardry, Clerical    |
| Artifact     | Magical items              | Dragonlances          |
| Event        | Historical occurrences     | War of the Lance      |
| Concept      | Abstract ideas             | Honor, Kingship       |
| Prophecy     | Predictions and omens      | Dragonlance prophecy  |
| Realm        | Planes and dimensions      | Abyss, Mount Celestia |

### Relationship Types

14 semantic relationship types capture fantasy lore connections:

| Type            | Description                  | Usage                   |
| --------------- | ---------------------------- | ----------------------- |
| Commands        | Authority relationships      | Leaders → Organizations |
| ServesUnder     | Service relationships        | Knights → Orders        |
| AlliedWith      | Alliance relationships       | Factions ↔ Factions     |
| OpposedTo       | Conflict relationships       | Good ↔ Evil             |
| Influences      | Influence relationships      | Deities → Mortals       |
| CreatedBy       | Creation relationships       | Artifacts ← Creators    |
| TransformedInto | Change relationships         | Races → New Forms       |
| DescendedFrom   | Heritage relationships       | People ← Ancestors      |
| BoundTo         | Binding relationships        | Souls ↔ Artifacts       |
| Protects        | Protection relationships     | Orders → Locations      |
| Corrupts        | Corruption relationships     | Evil → Good             |
| TeachesTo       | Knowledge relationships      | Masters → Students      |
| Embodies        | Representation relationships | Concepts ↔ Entities     |

---

## Processing Operations

### Basic Pipeline Operations

```bash
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
# Process canon through all stages (recommended for new documents)

make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
# Continue interrupted episode, embedding, and graph processing
```

Both commands reach durable graph sync and therefore require the exact confirmation
token. They may call the configured LLM provider and write to Neo4j.

### Document Loading Only

```bash
make load-canon        # Load canon documents to PostgreSQL
```

`load-draft`, `load-all`, `pipeline-draft`, and `pipeline-all` are retained as
explicit failure targets so stale automation cannot widen the corpus.

### Maintenance Operations

```bash
make status             # Overall service and processing status
make embedding-status   # Episode embedding coverage
make graph-sync-status  # Durable graph queue/status
make graph-rebuild-plan # Read-only plan for a controlled graph rebuild
```

The legacy `clear-graph`, `reset-all`, and `reset-sync` targets are retired and
fail closed. Use the backup-gated graph rebuild workflow described below when a
whole-graph replacement is actually required.

### Verbose Mode

Add `VERBOSE=1` to any command for detailed output:

```bash
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1
make load-canon VERBOSE=1
make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1
```

#### Verbose Output Includes:

- LLM prompt/response details
- Entity extraction debugging
- Relationship mapping information
- File processing details
- Graph query results
- Error stack traces

---

## Monitoring & Troubleshooting

### Status Monitoring

Check system status:

```bash
make status
```

This shows:

- Document counts by status (pending, completed, failed)
- Neo4j relationship statistics
- Processing errors and warnings

Monitor logs in real-time:

```bash
make logs
```

View container status:

```bash
docker compose -p luminari-sage ps
```

### System Status Output

The `make status` command shows:

```
Document Processing Status:
  Pending: 15
  Completed: 85
  Failed: 3
  Total: 103

Neo4j Statistics:
  Entities: 1,247
  Relationships: 3,891
  Episodes: 892

Recent Errors: 2
```

### Common Issues

#### No Documents Found

```
Found 0 markdown files to process
```

**Causes:**

- `lore_docs/canon` does not exist
- No `.md` files exist under `lore_docs/canon`
- The canon-only bind mount is missing

**Solutions:**

```bash
# Check directory structure
ls -la /home/luminari/lore/

# Verify canon files exist
find /home/luminari/lore/lore_docs/canon -name "*.md" | head -10
```

#### Database Connection Errors

```
Failed to connect to PostgreSQL/Neo4j
```

**Solutions:**

```bash
# Check services are running
docker compose -p luminari-sage ps

# Restart services
make restart

# Check container logs
docker compose -p luminari-sage logs postgres
docker compose -p luminari-sage logs neo4j
```

#### OpenAI API Issues

```
OpenAI API key not found / Rate limit exceeded
```

**Solutions:**

```bash
# Check API key is set
docker exec luminari-sage-api-1 python -c \
  "import os; print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING')"

# If missing, add to docker-compose.yml environment
# Wait for rate limits to reset (usually 1 minute)
```

#### Permission Errors

```
Permission denied accessing files
```

**Solutions:**

```bash
# Check file permissions
ls -la /home/luminari/lore/

# Fix ownership if needed
sudo chown -R $USER:$USER /home/luminari/lore/

# Check Docker volume mounts
docker inspect luminari-sage-api-1 | grep Mounts -A 10
```

### Error Recovery Strategies

#### Partial Processing Failures

When some documents fail but others succeed:

1. Check which documents failed:

   ```bash
   make status
   # Look for documents with 'failed' status
   ```

2. Review error details in logs:

   ```bash
   make logs | grep -A 5 -B 5 "ERROR\|Failed"
   ```

3. Try processing again (often transient issues):

   ```bash
   make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
   ```

4. For persistent failures, try verbose mode:
   ```bash
   make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1
   ```

#### LLM Processing Issues

When Graphiti entity extraction fails:

1. Check for API rate limits:
   - Wait 60 seconds and try again
   - Consider reducing batch size

2. Check for content issues:
   - Very large documents may timeout
   - Malformed markdown may cause issues

3. Inspect the durable graph state before retrying:

   ```bash
   make graph-sync-status
   make graph-sync-run-summary
   ```

Do not repair Graphiti failures by manually changing legacy document flags. The
durable worker owns job state, attempts, retries, and quarantine evidence.

---

## Maintenance & Recovery

### Recovery Operations

#### Resume After Interruption

If the pipeline is interrupted (Ctrl+C, system restart, etc.):

```bash
make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
```

This will:

- Create episodes for eligible unprocessed canon documents
- Generate embeddings for canon episodes missing vectors
- Continue eligible durable graph jobs
- Skip work whose stage is already complete

#### Controlled Graph Rebuild

`make rebuild` is a backup-gated replacement of the durable Neo4j graph. It is not
a general document/embedding reset and should not be routine maintenance. First
create and verify a current combined backup, then provide all three exact gates:

```bash
make backup-provider-upgrade \
  BACKUP_REFERENCE=backups/provider-upgrade-<timestamp>

make rebuild \
  BACKUP_REFERENCE=backups/provider-upgrade-<timestamp> \
  CONFIRM_GRAPH_REBUILD=PREPARE_DURABLE_GRAPH_REBUILD \
  CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC \
  CONFIRM_GRAPH_REBUILD_FINALIZE=FINALIZE_DURABLE_GRAPH_REBUILD
```

For the auditable step-by-step form, use `graph-rebuild-plan`,
`graph-rebuild-prepare`, confirmed `sync-to-graphiti`, and
`graph-rebuild-finalize`. The legacy direct graph/reset targets fail closed.

Clear and regenerate embeddings only when the active profile remains unchanged:

```bash
make reset-embeddings
make embedding-preflight
make generate-embeddings
```

Clearing vectors does not change the active profile identity. Switching provider,
model, revision, implementation, or dimensions requires a shadow space and the
documented migration/cutover workflow; do not overwrite the active space.

### Regular Maintenance

**Daily** (if actively developing):

- Run `make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC` after adding
  new canon files
- Check `make status` for any failures
- Treat edits, renames, and deletions as unsupported incremental operations until
  the reconciliation project is implemented

**Weekly**:

- Review `make graph-sync-status` and `make embedding-status`
- Review logs for recurring errors: `make logs`

**Monthly**:

- Run read-only graph and embedding audits appropriate to the deployment
- Rebuild only for a separately justified, backup-backed migration or repair

### Performance Optimization

There is no `pipeline-bulk` target. Episode embedding already uses configured
batches; graph ingestion remains the confirmed durable worker.

```bash
# Process the production corpus
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
```

**For debugging:**

```bash
# Use verbose mode
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1

# Process documents individually
make load-canon
make create-episodes
make embedding-preflight
make generate-embeddings
make sync-to-graphiti CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC VERBOSE=1
```

### Performance Monitoring

Monitor processing speed:

```bash
# Time a full pipeline run
time make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC

# Monitor resource usage
docker stats
```

Track progress in real-time:

```bash
# In one terminal
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC

# In another terminal
watch -n 5 "make status"
```

---

## Advanced Operations

### Performance Considerations

#### Incremental Processing

- Cleanly processes brand-new documents and skips unchanged documents
- Maintains per-stage processing state in PostgreSQL
- Supports interruption and confirmed resume
- Does not yet fully reconcile edits, renames, or deletions of existing files

#### Parallel Processing

- Document loading: Sequential (file I/O bound)
- Entity extraction: Sequential (LLM rate limited)
- Embedding generation: Batch processing when possible

#### Memory Management

- Documents processed one at a time
- Large documents chunked to stay within context limits
- Graph connections created incrementally

### Error Handling

#### Document Level

- Individual document failures don't stop pipeline
- Failed documents marked with error status
- Detailed error logging for debugging

#### System Level

- Database connection retries
- LLM API timeout handling
- Graceful shutdown on interruption

#### Recovery

- `make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC` continues eligible work
  from the last successful stage
- `make rebuild` is a separately confirmed, backup-gated whole-graph operation
- Status tracking enables targeted troubleshooting

### Manual Database Operations

Connect to PostgreSQL:

```bash
docker exec -it luminari-sage-postgres-1 psql -U luminari -d luminari_sage
```

Connect to Neo4j:

```bash
# cypher-shell prompts for credentials interactively
docker exec -it luminari-sage-neo4j-1 cypher-shell
```

### Custom Processing

Process specific documents:

```python
# Custom script example
import asyncio
from scripts.load_documents import DocumentLoader

async def main():
    loader = DocumentLoader("/home/luminari/lore", "canon", verbose=True)
    # Custom processing logic here

if __name__ == "__main__":
    asyncio.run(main())
```

### Backup and Recovery

Backup data:

```bash
# Backup PostgreSQL
docker exec luminari-sage-postgres-1 pg_dump -U luminari luminari_sage > backup.sql

# Backup Neo4j
docker exec luminari-sage-neo4j-1 neo4j-admin database dump neo4j --to-path=/tmp/
docker cp luminari-sage-neo4j-1:/tmp/neo4j.dump ./neo4j-backup.dump
```

Restore data:

```bash
# Restore PostgreSQL
cat backup.sql | docker exec -i luminari-sage-postgres-1 psql -U luminari luminari_sage

# Restore Neo4j (requires stopping service)
docker compose -p luminari-sage stop neo4j
docker exec luminari-sage-neo4j-1 neo4j-admin database load neo4j --from-path=/tmp/
docker compose -p luminari-sage start neo4j
```

---

## Configuration

Key environment variables:

- Provider credentials: Required only for the configured remote embedding and
  Graphiti providers; local providers use their corresponding service settings
- `NEO4J_URI`: Neo4j connection string
- `NEO4J_USER/NEO4J_PASSWORD`: Neo4j authentication
- `POSTGRES_*`: PostgreSQL connection settings

---

## Extensibility

The architecture supports easy extension:

- **New entity types**: Add to `src/graphiti/entity_types.py`
- **New relationships**: Add to `src/graphiti/edge_types.py`
- **Custom processing**: Extend base classes
- **New sources**: Add directory scanning logic

---

## Security

Security considerations:

- API keys managed via environment variables
- Database connections use authentication
- No sensitive data logged in normal mode
- Content hashing prevents data corruption

---

## Integration

The pipeline integrates with:

- **MCP Server**: Provides `/sage/mcp` endpoint for Claude integration
- **API Server**: Provides `/sage/api` endpoints for search and RAG
- **Apache Reverse Proxy**: Routes requests to appropriate services

---

## Related Documentation

- [Architecture Overview](../reference/ARCHITECTURE.md)
- [API Reference](../reference/API_REFERENCE.md)
- [Developer Guide](../development/DEVELOPER_GUIDE.md)
- [Agent System](AGENT_SYSTEM.md)
- [Validation System](VALIDATION_SYSTEM.md)
