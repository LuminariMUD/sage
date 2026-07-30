# Luminari Sage - Work Log

## 2025-12-31: Docker Configuration & Data Pipeline

### Docker Compose Updates

**Ollama Service Optimizations:**
- Added `OLLAMA_LOAD_TIMEOUT: "10m"` (was default 5m)
- Added `OLLAMA_KEEP_ALIVE: "10m"` (keeps model in VRAM longer)
- Changed `OLLAMA_MAX_CONTEXT` to `OLLAMA_NUM_CTX: "8192"` (correct env var name, increased from 4096)
- Changed `OLLAMA_FLASH_ATTENTION` from `"1"` to `"true"` (proper boolean format)

**API Service:**
- Updated `OLLAMA_MAX_CONTEXT_TOKENS` default from 4096 to 8192
- Added auth environment variables: `DISABLE_AUTH`, `SAGE_API_KEY`, `SAGE_MCP_KEY`, `SAGE_MCP_BACKEND_KEY`
- Added `OPENAI_API_KEY` pass-through (required for Graphiti reranker)

**General:**
- Removed obsolete `version: '3.8'` from docker-compose.yml
- Changed `POSTGRES_PORT` from 5432 to 5433 in .env (port conflict resolution)

### Docker Cleanup
- Removed 5 dangling images
- Removed 58 dangling volumes
- Cleared 12.54GB of build cache

### Database Schema Fixes

**Missing columns added to `lore_documents` table:**
- `graphiti_content_hash VARCHAR(64)`
- `graphiti_status VARCHAR(20) DEFAULT 'pending'`

**Missing enum values added to `document_type`:**
- culture, location, faction, character, timeline, event, item, lore, world, other

**Embedding dimension fix:**
- Changed `episodes.embedding` from `vector(384)` to `vector(768)` to match nomic-embed-text model

### API Bug Fix
- Fixed metadata parsing in `/api/v1/lore/search` endpoint
- Metadata was being returned as JSON string instead of dict from PostgreSQL
- Added JSON parsing fallback in `src/api/main.py:752`

### Ollama Model Downloads
- Pulled `nomic-embed-text` model (274MB) for embeddings
- Pulled `qwen2.5:7b` model (4.7GB) for chat/creative tasks

### Data Pipeline Execution - COMPLETED

| Step | Status | Details |
|------|--------|---------|
| 1. Load Canon Documents | COMPLETED | 13 markdown files loaded into PostgreSQL |
| 2. Create Episodes | COMPLETED | 611 semantic chunks created (200-500 tokens each) |
| 3. Generate Embeddings | COMPLETED | 611 episodes embedded with nomic-embed-text (768 dims) |
| 4. Sync to Neo4j | PENDING | Ready to run - uses local Ollama models (deepseek-r1:8b + nomic-embed-text) |

### Current System Status

**Containers:**
| Container | Status | Port |
|-----------|--------|------|
| luminari-api | healthy | 8003 |
| luminari-neo4j | healthy | 7474, 7687 |
| luminari-ollama | healthy | 11434 |
| luminari-postgres | healthy | 5433 |

**Ollama Models:**
- `qwen2.5:7b` (4.7GB) - chat/creative model
- `deepseek-r1:8b` (5.2GB) - reasoning model
- `nomic-embed-text` (274MB) - embedding model

**Database Content:**
- PostgreSQL: 13 documents, 611 episodes with embeddings
- Neo4j: 0 nodes (Graphiti sync not run)

### API Endpoints Tested - WORKING

1. **Ping:** `GET /ping` - OK
2. **Health:** `GET /api/v1/health` - All services healthy
3. **Lore Search:** `GET /api/v1/lore/search?query=crystal+dwarves` - Returns results
4. **RAG Query:** `POST /api/v1/rag/query` - Returns relevant chunks with similarity scores

### Graphiti/Neo4j Sync Investigation (2025-12-31)

**Problem Identified:**
- Graphiti v0.25.0 uses `OpenAIClient` which calls `client.responses.parse` (OpenAI's new Responses API)
- Ollama only supports the standard `chat.completions` API - returns 404 for Responses API

**Fix Applied:**
- Modified `src/graphiti/ollama_config.py` to use `OpenAIGenericClient` instead of `OpenAIClient`
- `OpenAIGenericClient` uses `chat.completions.create` which Ollama supports
- File must be copied to container after rebuild: `docker cp src/graphiti/ollama_config.py luminari-api:/app/src/graphiti/`

**Test Results:**
- Entity extraction now works with local Ollama (`deepseek-r1:8b`)
- Successfully extracted entities: "The Black Bitch", "Salandrian Navy", "Merchant guilds", etc.
- However, processing is **very slow** with local 8B model
- First episode did not complete within 5-minute test window

**Timing Estimate (Conservative):**
- Per episode: 2-5+ minutes (entity extraction + relationship extraction + embeddings)
- Total for 611 episodes: **20-50+ hours** with local models
- Recommend running overnight or considering smaller model/OpenAI for speed

**Current Status:**
- Episodes processed: 0/611
- Neo4j nodes: 0
- Fix is functional but not yet persisted in Docker image

### Known Issues / TODO

1. **Graphiti Sync - FUNCTIONAL BUT SLOW**
   - Fix applied: use `OpenAIGenericClient` for Ollama compatibility
   - Rebuild container to persist fix: `docker compose build api`
   - Run sync: `make sync-to-graphiti` (expect 20-50+ hours)

2. **Auth Disabled for Testing**
   - `DISABLE_AUTH=true` currently set in `.env`
   - Set to `false` and configure `SAGE_API_KEY` for production

### Files Modified
- `docker-compose.yml` - Ollama env vars, API env vars, removed version
- `.env` - POSTGRES_PORT, DISABLE_AUTH
- `src/api/main.py` - metadata parsing fix (line 752)
- `src/graphiti/ollama_config.py` - Changed to `OpenAIGenericClient` for Ollama compatibility
- PostgreSQL schema - graphiti columns, enum values, embedding dimension
