# Frequently Asked Questions (FAQ)

**Version**: 0.7.5
**Status**: Production Ready
**Last Updated**: 2025-11-12

Answers to common questions about Luminari Sage.

---

## Table of Contents

- [General Questions](#general-questions)
- [Getting Started](#getting-started)
- [Using the API](#using-the-api)
- [MCP Integration](#mcp-integration)
- [Data & Pipeline](#data--pipeline)
- [Agents & AI](#agents--ai)
- [Validation & Corrections](#validation--corrections)
- [Performance & Scaling](#performance--scaling)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## General Questions

### What is Luminari Sage?

Luminari Sage is an intelligent lore management system for LuminariMUD. It combines:

- **Neo4j** (graph database) for entity relationships
- **PostgreSQL** with **pgvector** for document storage and embeddings
- **AI agents** for search, validation, and creative assistance
- **Graphiti** for knowledge graph construction
- **Hybrid RAG** for intelligent retrieval

It enables semantic search, lore validation, quest planning, and story development based on canonical lore.

### What makes Luminari Sage different from a regular search system?

Luminari Sage uses **Hybrid RAG** (Retrieval-Augmented Generation):

1. **Vector Search**: Finds semantically similar content using embeddings
2. **Full-Text Search**: Matches keywords and phrases
3. **Graph Traversal**: Explores entity relationships and connections
4. **Reciprocal Rank Fusion**: Combines all results intelligently

This provides much better context understanding than keyword search alone.

### Is Luminari Sage production-ready?

Yes! Version 0.7.0 is deployed in production at `luminarimud.com:8003`. It includes:

- ✅ 35+ API endpoints
- ✅ Complete validation and correction systems
- ✅ LangChain ReAct agents
- ✅ MCP server for Claude Desktop
- ✅ Authentication and security
- ✅ Comprehensive testing

### What's the license?

License details are still being determined. Contact the LuminariMUD team for current status.

### Can I use this for my own MUD or game?

The architecture is designed for LuminariMUD specifically, but the patterns and approaches can be adapted. The codebase demonstrates:

- Graph-based lore management
- Hybrid RAG implementation
- AI agent orchestration
- Validation and correction systems

Contact the team if you're interested in adapting it.

---

## Getting Started

### How do I install Luminari Sage?

**Quick setup:**

```bash
# Clone repository
git clone https://github.com/LuminariMUD/sage.git
cd sage

# Configure environment
cp .env.example .env
chmod 600 .env
# Edit .env with your OpenAI API key and passwords

# Start with Docker
docker compose up -d

# Run data pipeline
make semantic-pipeline

# Test
curl http://localhost:8003/ping
```

See [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

### What are the system requirements?

**Minimum:**

- Docker and Docker Compose
- 8GB RAM
- 20GB disk space
- OpenAI API key

**Recommended:**

- 16GB+ RAM for production
- SSD storage
- Linux or macOS (Windows via WSL2)

### Do I need an OpenAI API key?

Yes, for:

- Generating embeddings (vector search)
- AI agent responses
- Entity extraction via Graphiti

**Cost estimates:**

- Initial pipeline: $2-5 (one-time)
- Ongoing usage: ~$50/month with moderate use

**Alternative:** Use local embedding models by setting `USE_OPENAI_EMBEDDINGS=false` in `.env`.

### How long does setup take?

- **Docker setup**: 5-10 minutes
- **Data pipeline**: 30-60 minutes (depending on content volume)
- **Testing**: 5 minutes

Total: ~1 hour for complete setup.

---

## Using the API

### What port does the API use?

**Port 8003** (not 8000). Access at:

- Local: `http://localhost:8003`
- Production: `http://luminarimud.com:8003`

### How do I authenticate?

Use API keys with the `X-API-Key` header:

```bash
./scripts/curl_with_sage_key.sh \
  http://localhost:8003/api/v1/entities/search?query=dwarves
```

Three key types:

- `BACKEND_API_KEY`: Full backend access
- `MCP_OPERATIONS_KEY`: MCP server operations
- `MCP_BACKEND_ACCESS_KEY`: MCP backend access

See [API_REFERENCE.md](../reference/API_REFERENCE.md) for details.

### Can I disable authentication for development?

Yes, set in `.env`:

```bash
DISABLE_AUTH=true
```

**Warning:** Never disable in production!

### What API endpoints are available?

35+ endpoints in 9 categories:

- Health & Status
- Entity Management
- Lore Search
- RAG Queries
- Validation
- Corrections
- Chat (Streaming)
- Debug
- Statistics

See [API_REFERENCE.md](../reference/API_REFERENCE.md) for complete list.

### How do I search for lore?

**Simple search:**

```bash
curl "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves"
```

**RAG query (AI-powered):**

```bash
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the crystal dwarves?", "limit": 5}'
```

**Entity search:**

```bash
curl "http://localhost:8003/api/v1/entities/search?query=dwarf"
```

### Is there a web interface?

Not currently. Available interfaces:

- REST API (primary)
- MCP server (for Claude Desktop)
- Postman collections (for testing)

A web interface is on the roadmap.

---

## MCP Integration

### What is MCP?

**MCP (Model Context Protocol)** is Anthropic's standard for connecting AI assistants to external tools and data. It allows Claude Desktop to use Luminari Sage directly.

### How do I use Luminari Sage with Claude Desktop?

1. **Configure Claude Desktop** (`claude_desktop_config.json`):

   ```json
   {
     "mcpServers": {
       "luminari-sage": {
         "command": "docker",
         "args": [
           "exec",
           "-i",
           "luminari-api",
           "python",
           "-m",
           "src.mcp.server"
         ]
       }
     }
   }
   ```

2. **Restart Claude Desktop**

3. **Test**: Ask Claude "Search Luminari lore for crystal dwarves"

See [README-MCP.md](README-MCP.md) for complete setup.

### What MCP tools are available?

- `hybrid_rag_search`: Search lore with context
- `search_entities`: Find entities in graph
- `get_entity_details`: Get entity information
- `validate_content`: Check lore consistency
- `get_relationships`: Explore entity connections

### Can I use MCP without Docker?

Yes, but you need to run the API locally:

```json
{
  "command": "python",
  "args": ["-m", "src.mcp.server"],
  "env": {
    "PYTHONPATH": "/path/to/lore"
  }
}
```

---

## Data & Pipeline

### Where does the lore data come from?

Markdown files in `lore_docs/`:

- `canon/`: Canonical lore (83 files across 11 directories)
- `draft/`: Work-in-progress content
- Converted from Office documents and original markdown

### What does the data pipeline do?

The pipeline processes markdown → knowledge graph:

1. **Load documents** → PostgreSQL `lore_documents` table
2. **Create episodes** → Semantic chunks (200-500 tokens) in `episodes` table
3. **Generate embeddings** → Vector embeddings for semantic search
4. **Sync to Graphiti** → Extract entities and relationships to Neo4j

Run with: `make semantic-pipeline`

### How long does the pipeline take?

- **Load documents**: 1-2 minutes
- **Create episodes**: 5-10 minutes
- **Generate embeddings**: 15-30 minutes
- **Sync to Graphiti**: 10-20 minutes

**Total**: 30-60 minutes

### Can I run the pipeline on just some documents?

Yes:

```bash
make load-canon          # Just canonical docs
# Or manually specify paths
docker exec -it luminari-api python src/scripts/load_documents.py --path lore_docs/canon/gods/
```

### What if the pipeline fails partway through?

The pipeline is **idempotent** with processing flags. You can resume:

```bash
make resume  # Continues from where it stopped
```

Or clear and restart:

```bash
make reset-all
make semantic-pipeline
```

### How do I add new lore documents?

1. **Add markdown file** to `lore_docs/canon/` or `lore_docs/draft/`
2. **Run pipeline**:
   ```bash
   make load-canon
   make create-episodes
   make generate-embeddings
   make sync-to-graphiti
   ```

The system automatically processes new files.

---

## Agents & AI

### What AI agents are available?

**LangChain Agents** (modern):

- **Direct Answer Agent**: Factual lore questions
- **Quest Planner**: Generate structured quests
- **Story Developer**: Create narrative content
- **Relationship Validator**: Check lore consistency

**PydanticAI Agents** (legacy):

- Legacy streaming chat agent

See [AGENT_SYSTEM.md](../systems/AGENT_SYSTEM.md) for details.

### How does the agent system choose which agent to use?

The **router** classifies queries by intent:

- Factual questions → Direct Answer Agent
- Quest requests → Quest Workflow
- Story/creative → Story Workflow
- Validation → Relationship Validator

### Can I use the agents via API?

Yes:

```bash
# Streaming chat
curl -X POST http://localhost:8003/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about the crystal dwarves", "stream": true}'

# RAG query
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the crystal dwarves?", "limit": 5}'
```

### Do agents remember conversation history?

Yes, conversations are stored in PostgreSQL `conversations` and `conversation_turns` tables.

Cleanup old sessions:

```bash
curl -X POST http://localhost:8003/api/v1/chat/cleanup
```

### How accurate are the agents?

**Direct Answer Agent**: ~95% relevance with proper data
**Story Developer**: Creative content grounded in lore
**Quest Planner**: Structured output with validation

Accuracy depends on:

- Quality of lore data
- Completeness of knowledge graph
- Proper embeddings generation

---

## Validation & Corrections

### What does the validation system do?

The **Relationship Validator** checks lore consistency with 6 validation types:

1. **Structural**: Basic relationship integrity
2. **Semantic**: Meaning and context
3. **Type-specific**: Rules per relationship type
4. **Cross-references**: Multi-relationship patterns
5. **Temporal**: Time-based consistency
6. **Canonical**: Matches established lore

Plus **LLM enhancement** for deep semantic analysis.

See [VALIDATION_SYSTEM.md](../systems/VALIDATION_SYSTEM.md).

### How do I validate content?

**Validate text:**

```bash
curl -X POST http://localhost:8003/api/v1/validate \
  -H "Content-Type: application/json" \
  -d '{"content": "The crystal dwarves worship Ao"}'
```

**Validate relationships:**

```bash
curl -X POST http://localhost:8003/api/v1/validate/relationships
```

### What are "findings"?

**Findings** are validation issues stored in the database:

- Detected inconsistencies
- Confidence scores
- Suggested corrections
- Review status

View findings:

```bash
curl http://localhost:8003/api/v1/validate/findings/unreviewed
```

### How does the correction system work?

The **Correction System** can automatically fix certain issues:

- **Deduplication**: Merge duplicate entities
- **Semantic standardization**: Align similar names

All corrections are:

- Reversible (with rollback)
- Tracked (audit trail)
- Safe (preview before applying)

See [CORRECTION_SYSTEM.md](../systems/CORRECTION_SYSTEM.md).

### Can I rollback corrections?

Yes, all corrections are reversible:

```bash
# Preview rollback
curl http://localhost:8003/api/v1/corrections/batch/{batch_id}/preview

# Rollback single correction
curl -X POST http://localhost:8003/api/v1/corrections/{correction_id}/rollback

# Rollback entire batch
curl -X POST http://localhost:8003/api/v1/corrections/batch/{batch_id}/rollback
```

### Are corrections applied automatically?

No, corrections require **explicit approval**. The system:

1. Detects issues
2. Suggests corrections
3. Waits for user approval
4. Applies if approved
5. Can rollback if needed

---

## Performance & Scaling

### How fast are queries?

**Typical response times:**

- Health check: <10ms
- Entity search: 100-300ms
- Lore search: 200-500ms
- RAG query: 1-3 seconds
- AI agent (streaming): 3-10 seconds

### What affects performance?

**Database:**

- Index quality (especially pgvector)
- Query complexity
- Data volume

**AI:**

- OpenAI API latency
- Model choice (GPT-4 vs GPT-3.5)
- Context size

**System:**

- Available RAM
- CPU cores
- Network latency

### How can I improve performance?

1. **Add indexes:**

   ```sql
   CREATE INDEX idx_episodes_embedding ON episodes USING ivfflat (embedding vector_cosine_ops);
   ```

2. **Tune pgvector:**
   - Adjust `ivfflat` lists
   - Use `hnsw` for better accuracy

3. **Reduce query limits:**
   - Fetch fewer results initially
   - Pagination for large sets

4. **Use faster models:**
   - GPT-3.5-turbo instead of GPT-4
   - Local embeddings instead of OpenAI

5. **Cache results:**
   - Implement Redis caching
   - Cache common queries

See [DEVELOPER_GUIDE.md](../development/DEVELOPER_GUIDE.md) for profiling.

### How does it scale?

**Current capacity:**

- 83 documents → ~10,000 episodes
- 1000+ entities
- 5000+ relationships
- Handles 50+ concurrent queries

**Scaling strategies:**

- Horizontal: Add API replicas
- Vertical: Increase database resources
- Caching: Redis layer
- CDN: Static assets

---

## Development

### How do I contribute?

1. Read [CONTRIBUTING.md](../development/CONTRIBUTING.md)
2. Fork repository
3. Create feature branch
4. Make changes with tests
5. Submit pull request

### What's the code structure?

```
src/
├── api/              # FastAPI application
├── agents/           # AI agents (PydanticAI + LangChain)
├── db/               # Database connections
├── graphiti/         # Graphiti integration
├── scripts/          # Data pipeline scripts
└── auth/             # Authentication middleware
```

See [DEVELOPER_GUIDE.md](../development/DEVELOPER_GUIDE.md).

### How do I run tests?

```bash
# All tests
pytest

# Unit tests only (fast)
pytest -m unit

# Integration tests (requires running services)
pytest -m integration

# With coverage
pytest --cov=src tests/
```

See [TESTING.md](../development/TESTING.md).

### How do I debug issues?

**Enable debug logging:**

```bash
# In .env
LOG_LEVEL=DEBUG
docker compose restart api
```

**Check logs:**

```bash
docker compose logs -f api
```

**Interactive debugging:**

```bash
docker exec -it luminari-api bash
python
>>> from src.db import get_postgres_db
>>> # test code here
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.

### What coding standards do you follow?

- **Python**: PEP 8, Black formatter
- **Type hints**: Required for all functions
- **Async/await**: For all I/O operations
- **Tests**: Required for new features
- **Documentation**: Docstrings for public APIs

See [CONTRIBUTING.md](../development/CONTRIBUTING.md).

---

## Deployment

### How do I deploy to production?

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for complete instructions.

**Quick steps:**

1. Configure the required GitHub Actions deployment secrets
2. Pin the production SSH host identity
3. Run the manual `Deploy Luminari Sage` workflow from `main`
4. Verify the health check and security scan
5. Run the data pipeline if required

### What environment variables are required?

**Required:**

- `OPENAI_API_KEY`: OpenAI API access
- `POSTGRES_PASSWORD`: Database password
- `NEO4J_PASSWORD`: Neo4j password
- `SAGE_API_KEY`: Backend API key

**Optional:**

- `DISABLE_AUTH`: Disable authentication (dev only)
- `LOG_LEVEL`: Logging verbosity
- `USE_OPENAI_EMBEDDINGS`: Use OpenAI vs local embeddings

See [DEPLOYMENT_CONFIG.md](../reference/DEPLOYMENT_CONFIG.md).

### How do I backup the system?

**PostgreSQL:**

```bash
docker exec luminari-postgres pg_dump -U luminari luminari_lore > backup.sql
```

**Neo4j:**

```bash
docker exec luminari-neo4j neo4j-admin dump --to=/tmp/neo4j-backup.dump
docker cp luminari-neo4j:/tmp/neo4j-backup.dump ./neo4j-backup.dump
```

**Restore:**
See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for restore procedures.

### How do I monitor the system?

**Health check:**

```bash
curl http://localhost:8003/api/v1/health
```

**Statistics:**

```bash
curl http://localhost:8003/api/v1/stats
```

**System status:**

```bash
make status
```

**Monitoring tools:**

- Docker stats: `docker stats`
- Log aggregation: `docker compose logs -f`
- Neo4j browser: http://localhost:7474

---

## Troubleshooting

### Where can I find solutions to common problems?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed solutions to:

- Database connection issues
- Docker problems
- API errors
- Pipeline failures
- Authentication issues
- Performance problems
- Neo4j issues
- MCP connection problems
- Agent issues
- Testing failures

### How do I get help?

1. **Check documentation:**
   - [Troubleshooting Guide](TROUBLESHOOTING.md)
   - [API Reference](../reference/API_REFERENCE.md)
   - [Developer Guide](../development/DEVELOPER_GUIDE.md)

2. **Search GitHub issues:**
   - Look for similar problems
   - Check closed issues

3. **Create GitHub issue:**
   - Include error messages
   - Provide steps to reproduce
   - Share relevant logs

4. **Community:**
   - LuminariMUD Discord
   - Project contributors

### Where are the logs?

**API logs:**

```bash
docker compose logs -f api
```

**PostgreSQL logs:**

```bash
docker compose logs -f postgres
```

**Neo4j logs:**

```bash
docker compose logs -f neo4j
```

**All logs:**

```bash
docker compose logs -f
```

### How do I report a bug?

1. **Check if it's already reported** in GitHub issues
2. **Reproduce the issue** with minimal steps
3. **Gather information:**
   - Error messages
   - Log excerpts
   - System info (OS, Docker version)
   - Configuration (sanitized .env)
4. **Create GitHub issue** with template
5. **Provide examples** if possible

---

## Additional Resources

### Documentation

- **[Documentation Guide](../DOCUMENTATION.md)** - Complete documentation hub
- **[Quickstart](QUICKSTART.md)** - Get started in 10 minutes
- **[API Reference](../reference/API_REFERENCE.md)** - Complete API documentation
- **[Architecture](../reference/ARCHITECTURE.md)** - System design
- **[User Guide](USER_GUIDE.md)** - Complete user guide

### Examples

- **[Postman Collections](../demos/Postman_Collections_Guide.md)** - API testing
- **[GraphRAG Demo](../demos/GraphRAG_Demo_Guide.md)** - Hybrid RAG demonstration

### Project Meta

- **[Changelog](../meta/CHANGELOG.md)** - Version history
- **[TODO](../meta/TODO.md)** - Current tasks and roadmap
- **[Project README](../../README.md)** - Vision and overview

---

## Still Have Questions?

If your question isn't answered here:

1. Check the [Documentation Guide](../DOCUMENTATION.md)
2. Search through documentation
3. Review [CLAUDE.md](../../CLAUDE.md) in project root
4. Ask in LuminariMUD Discord
5. Create a GitHub issue

We're continuously improving documentation based on user feedback!

---

**Last Updated**: 2025-11-12
**Version**: 0.7.5
**Status**: Production Ready
