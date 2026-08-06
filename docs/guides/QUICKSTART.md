# Luminari Sage Quick Start Guide

**Last Updated**: November 12, 2025
**Version**: 0.7.3
**Status**: Production Ready

## Prerequisites

### Required

- **Docker** and **Docker Compose** v2.0+ (recommended for easiest setup)
- **Git** for cloning the repository
- **OpenAI API Key** for embeddings and LLM operations

### Manual Installation (Alternative)

If not using Docker:

- Python 3.11+ (containers run 3.13)
- PostgreSQL 15+ with pgvector extension
- Neo4j 5.x Community Edition
- Make (optional but recommended)

## Quick Start with Docker (Recommended)

### 1. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/LuminariMUD/sage.git
cd sage

# Copy environment template
cp .env.example .env
chmod 600 .env

# Edit .env with your OpenAI API key
nano .env
# Required: Set OPENAI_API_KEY=sk-your-key-here
# Optional: Set database passwords (auto-generated if not set)
```

### 2. Start All Services

```bash
# Start PostgreSQL, Neo4j, and API server
docker compose up -d

# Check service status
docker compose ps

# View logs (optional)
docker compose logs -f api
```

### 3. Run Data Pipeline

The data pipeline loads and processes lore documents into the knowledge graph:

```bash
# Complete pipeline (recommended for first run)
make semantic-pipeline

# This runs four steps:
# 1. Load canonical lore documents into PostgreSQL
# 2. Create semantic episodes (chunks) from documents
# 3. Generate vector embeddings for episodes
# 4. Extract entities and relationships to Neo4j via Graphiti
```

**Note**: The pipeline takes 10-30 minutes depending on hardware and document count. It's resource-intensive and runs separately from API deployment.

### 4. Verify Installation

```bash
# Check API health
curl http://localhost:8003/ping
curl http://localhost:8003/api/v1/health

# Check system status
make status
```

The API will be available at:

- **API**: http://localhost:8003
- **Neo4j Browser**: http://localhost:7474 (username: neo4j, password: from .env)
- **PostgreSQL**: localhost:5432 (credentials from .env)

**Note**: Interactive API docs (`/docs`, `/redoc`) are not currently implemented. Use [API_REFERENCE.md](./API_REFERENCE.md) for endpoint documentation.

## Testing the System

### Without Authentication (Public Endpoints)

```bash
# Health check
curl http://localhost:8003/api/v1/health

# Simple ping
curl http://localhost:8003/ping
```

### With Authentication (Protected Endpoints)

Most endpoints require an API key. Use the repository helper so the key is
loaded from `.env` without being printed or placed in curl's process arguments:

```bash
# Search entities
./scripts/curl_with_sage_key.sh \
  "http://localhost:8003/api/v1/entities/search?query=crystal+dwarves&limit=5"

# Search lore documents
./scripts/curl_with_sage_key.sh \
  "http://localhost:8003/api/v1/lore/search?query=knights&limit=5"

# RAG query (hybrid vector + graph + FTS)
./scripts/curl_with_sage_key.sh \
  -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the crystal dwarves?", "limit": 5}'

# Get system statistics
./scripts/curl_with_sage_key.sh \
  http://localhost:8003/api/v1/stats
```

### Authentication Key Types

The system supports three API key types (all in `.env`):

- **SAGE_API_KEY**: General backend API access
- **SAGE_MCP_KEY**: MCP operations access
- **SAGE_MCP_BACKEND_KEY**: MCP backend operations

For local development, you can disable authentication:

```bash
export DISABLE_AUTH=true
```

## Project Structure

```
luminari-sage/
├── scripts/              # Data processing scripts
│   ├── load_documents.py    # Load markdown files
│   ├── extract_entities.py  # Extract entities with Graphiti
│   └── generate_chunks.py   # Create embeddings
├── src/
│   ├── api/             # FastAPI application
│   │   └── main.py         # Complete API endpoints
│   ├── db/              # Database connections
│   │   ├── postgres.py     # PostgreSQL with pgvector
│   │   └── neo4j_db.py     # Neo4j manager
│   └── graphiti/        # Knowledge graph
│       ├── __init__.py     # Graphiti integration
│       └── entity_extractor.py  # Pattern extraction
├── schemas/             # Database schemas
│   ├── postgresql_schema.sql
│   └── neo4j_schema.cypher
├── docker-compose.yml   # Service orchestration
├── Makefile            # Common commands
├── TODO.md             # Current tasks
├── CHANGELOG.md        # Version history
└── .env                # Configuration
```

## Using MCP Server (Claude Desktop Integration)

Luminari Sage includes an MCP (Model Context Protocol) server for Claude Desktop integration.

### 1. Configure Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "luminari-sage": {
      "command": "docker",
      "args": ["exec", "-i", "luminari-api", "python", "-m", "src.mcp.server"],
      "env": {
        "SAGE_MCP_KEY": "your-mcp-key-from-env"
      }
    }
  }
}
```

### 2. Available MCP Tools

Once configured, Claude Desktop can use these tools:

- **search_lore**: Semantic search across lore documents
- **get_entity**: Retrieve detailed entity information
- **validate_content**: Check lore consistency
- **query_graph**: Query the knowledge graph

See [README-MCP.md](./README-MCP.md) for complete MCP documentation.

## Common Issues

### Services Won't Start

```bash
# Check Docker is running
docker ps

# Check logs for errors
docker compose logs

# Restart all services
docker compose restart
```

### Database Connection Errors

```bash
# Verify environment variables
python3 scripts/check_secret_config.py POSTGRES_PASSWORD NEO4J_PASSWORD

# Check database health
docker compose exec postgres pg_isready
docker compose exec neo4j cypher-shell "RETURN 1"
```

### Pipeline Fails During Processing

```bash
# Check available disk space
df -h

# Check memory usage
docker stats

# Resume pipeline from last successful step
make resume

# Clear and restart pipeline
make clear-all
make semantic-pipeline
```

### Out of Memory During Embeddings

```bash
# Reduce batch size in .env
echo "EMBEDDING_BATCH_SIZE=16" >> .env

# Restart API
docker compose restart api

# Re-run embeddings
make generate-embeddings
```

### API Key Issues

```bash
# Enter a password-manager-generated value without echoing it
read -r -s -p "New backend key: " NEW_KEY
echo
export NEW_KEY
python3 - <<'PY'
import os
from dotenv import set_key

set_key(".env", "SAGE_API_KEY", os.environ["NEW_KEY"], quote_mode="always")
PY
unset NEW_KEY

# Restart API
docker compose restart api
```

## Data Pipeline Details

### Individual Pipeline Steps

```bash
# Step 1: Load canonical lore documents
make load-canon
# Loads markdown files from lore_docs/ into PostgreSQL

# Step 2: Create semantic episodes
make create-episodes
# Chunks documents into 200-500 token episodes with overlap

# Step 3: Generate embeddings
make generate-embeddings
# Creates vector embeddings using sentence-transformers or OpenAI

# Step 4: Sync to knowledge graph
make sync-to-graphiti
# Extracts entities and relationships to Neo4j via Graphiti
```

### Pipeline Management

```bash
# Check pipeline status
make status

# Resume interrupted pipeline
make resume

# Reset processing flags (keeps data)
make reset-all

# Clear all processed data
make clear-all

# Full rebuild from scratch
make rebuild
```

### Pipeline Notes

- **Idempotent**: Safe to re-run; skips already-processed items
- **Resource-Intensive**: Uses significant CPU/memory for embeddings
- **Time Required**: 10-30 minutes for full corpus
- **Separate from Deployment**: Run after services are up

## Next Steps

1. **Explore Endpoints**: Check [API_REFERENCE.md](./API_REFERENCE.md) for all available endpoints
2. **Query Entities**: Search for deities, locations, factions, and artifacts
3. **Try RAG Queries**: Ask natural language questions about the lore
4. **Test Validation**: Validate new lore against existing knowledge
5. **Use MCP Tools**: Integrate with Claude Desktop for AI-assisted queries
6. **Review Statistics**: Monitor system usage at `/api/v1/stats`

## Additional Resources

- [API Reference](./API_REFERENCE.md) - Complete endpoint documentation
- [Deployment Guide](./DEPLOYMENT_GUIDE.md) - Production deployment
- [Developer Guide](./DEVELOPER_GUIDE.md) - Development environment setup
- [Architecture](./ARCHITECTURE.md) - System design and data flow
- [Changelog](./CHANGELOG.md) - Version history and updates
- [TODO List](./TODO.md) - Current development tasks

## Getting Help

### Documentation

- Main README: [README.md](./README.md)
- MCP Setup: [README-MCP.md](./README-MCP.md)
- Agent System: [AGENT_SYSTEM.md](./AGENT_SYSTEM.md)

### Logs and Debugging

```bash
# View all logs
docker compose logs

# Follow API logs
docker compose logs -f api

# Check specific service
docker compose logs postgres
docker compose logs neo4j

# Debug mode
export DEBUG=true
export LOG_LEVEL=DEBUG
docker compose restart api
```

### Common Commands

```bash
# Restart everything
docker compose restart

# Stop all services
docker compose down

# Stop and remove volumes (DELETES DATA)
docker compose down -v

# Rebuild containers
docker compose build --no-cache

# Shell access
docker compose exec api bash
docker compose exec postgres psql -U sage sage_db
```
