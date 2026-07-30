# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Luminari Sage is a graph-based lore management system for LuminariMUD. It combines Neo4j (knowledge graph), PostgreSQL with pgvector (documents + embeddings), and AI agents to enable intelligent search, validation, and creative writing assistance for game lore.

**Stack**: Python 3.11+, FastAPI, Neo4j, PostgreSQL/pgvector, Graphiti, PydanticAI, LangChain

## Development Commands

### Docker Operations
```bash
# Start all services (PostgreSQL, Neo4j, API)
docker compose up -d

# View logs
docker compose logs -f api

# Access API container shell
docker exec -it luminari-api bash

# Restart services
docker compose restart
```

### Data Pipeline (Makefile)
The data pipeline processes markdown lore documents into a queryable knowledge graph:

```bash
# Complete pipeline (recommended)
make semantic-pipeline        # Load canon docs → create episodes → embeddings → sync to Neo4j

# Individual steps
make load-canon              # Load canonical lore into PostgreSQL
make create-episodes         # Create semantic chunks (200-500 tokens)
make generate-embeddings     # Generate vector embeddings
make sync-to-graphiti        # Extract entities/relationships to Neo4j via Graphiti

# Reset operations
make clear-all              # Clear all processed data
make reset-all              # Reset processing flags
make rebuild                # Full rebuild from scratch

# Monitoring
make status                 # System health and statistics
```

**Important**: The data pipeline is resource-intensive and separate from API deployment. Run it after deploying services.

### Testing
```bash
# Run all tests
pytest

# Run specific test markers
pytest -m unit              # Fast unit tests only
pytest -m integration       # Integration tests (requires running services)
pytest -m data_dependent    # Tests requiring loaded data

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_api_integration.py -v
```

### API Operations
```bash
# API runs on port 8003 inside container
curl http://localhost:8003/ping

# Health check
curl http://localhost:8003/api/v1/health

# Search lore
curl "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves"

# RAG query
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the crystal dwarves?", "limit": 5}'
```

## Architecture

### High-Level Data Flow
```
Markdown Lore Files
    ↓
[load_documents.py] → PostgreSQL lore_documents table
    ↓
[create_episodes_from_documents.py] → PostgreSQL episodes table (semantic chunks)
    ↓
[generate_embeddings.py] → Add vector embeddings to episodes
    ↓
[extract_entities.py] → Neo4j graph via Graphiti (entities + relationships)
    ↓
FastAPI serves hybrid RAG: PostgreSQL vectors + Neo4j graph
```

### Key Architectural Concepts

**1. Hybrid RAG (Retrieval-Augmented Generation)**
- **Vector Search**: PostgreSQL pgvector finds semantically similar episode chunks
- **Full-Text Search**: PostgreSQL FTS for keyword matching
- **Reciprocal Rank Fusion**: Combines both result sets with RRF scoring
- **Graph Enhancement**: Neo4j Graphiti provides entity context and relationship facts
- **Implementation**: `src/api/main.py::rag_query()` endpoint

**2. Semantic Chunking Pipeline**
- Documents split into "episodes" (semantic chunks) of 200-500 tokens
- Overlap strategy: 25% with complete sentences only
- Uses tiktoken for consistent token counting
- Complexity-aware sizing (simple text → smaller chunks, complex → larger)
- Episodes stored with stable_id for Neo4j cross-referencing

**3. Graphiti Knowledge Graph**
- Graphiti automatically extracts entities and relationships from episodes
- Creates Neo4j nodes: Entity types (Character, Location, Faction, etc.)
- Creates Neo4j edges: Relationship types with semantic properties
- Each episode becomes an Episodic node in Neo4j
- Episodic.stable_id maps to PostgreSQL episodes.id

**4. Dual Agent Systems**
The codebase has TWO chat agent implementations:

- **Legacy PydanticAI** (`src/agents/lore_chat_agent_*.py`): Original streaming agent
- **LangChain ReAct** (`src/agents/langchain/`): Modern agentic workflow with tools
  - Uses LangGraph for stateful orchestration
  - Router → Retrieval → Direct Answer / Quest Workflow / Story Workflow
  - State manager for conversation continuity
  - Unified creative chain with ReAct loop

**5. Database Connection Pattern**
```python
# IMPORTANT: Use singleton pattern for database connections
from src.db import get_postgres_db, get_neo4j_db

# In async functions
postgres_db = await get_postgres_db()  # Returns global pool
neo4j_db = await get_neo4j_db()        # Returns global driver

# Never close in endpoints - connections are managed globally
# Closing happens in app lifespan shutdown
```

## Project Structure

```
src/
├── api/              # FastAPI application
│   └── main.py      # All API endpoints, Pydantic models, hybrid RAG
├── db/              # Database connection singletons
│   ├── postgres.py  # AsyncPG connection pool
│   └── neo4j_db.py  # Neo4j driver singleton
├── agents/
│   ├── langchain/   # Modern LangChain ReAct agent system
│   │   ├── chains/  # Retrieval, direct answer, unified creative
│   │   ├── tools/   # Hybrid RAG tool, focused tools
│   │   ├── legacy_service.py    # Main LangChain entry point
│   │   ├── quest_workflow.py    # Quest planning workflow
│   │   └── story_workflow.py    # Story development workflow
│   ├── lore_chat_agent_*.py     # Legacy PydanticAI agents
│   ├── relationship_validator.py # Graph consistency validation
│   └── conversation_storage.py   # Chat persistence
├── graphiti/        # Graphiti integration
│   ├── entity_types.py  # Pydantic models for entity types
│   └── edge_types.py    # Pydantic models for relationship types
├── scripts/         # Data pipeline scripts
│   ├── load_documents.py             # Step 1: Load markdown → PostgreSQL
│   ├── create_episodes_from_documents.py  # Step 2: Semantic chunking
│   ├── generate_embeddings.py        # Step 3: Vector embeddings
│   └── extract_entities.py           # Step 4: Graphiti → Neo4j
└── auth/            # API key authentication middleware

schemas/             # SQL and Cypher schemas
tests/              # Pytest test suites
lore_docs/          # Markdown lore documents (mounted read-only)
```

## Common Development Patterns

### Adding a New API Endpoint
1. Define Pydantic request/response models in `src/api/main.py`
2. Add endpoint function with FastAPI decorators
3. Use `await get_postgres_db()` / `await get_neo4j_db()` for connections
4. Never manually close database connections in endpoints
5. Return Pydantic model instances for automatic validation

### Working with the Knowledge Graph
```python
# Query Neo4j for entities
neo4j_db = await get_neo4j_db()
results = await neo4j_db.execute_query("""
    MATCH (n:Entity {name: $name})
    RETURN n
""", {"name": "Crystal Dwarves"})

# Query PostgreSQL for vector search
postgres_db = await get_postgres_db()
results = await postgres_db.fetch("""
    SELECT text, 1 - (embedding <=> $1::vector) as similarity
    FROM episodes
    WHERE 1 - (embedding <=> $1::vector) > 0.7
    ORDER BY embedding <=> $1::vector
    LIMIT 10
""", embedding_vector)
```

### Extending Entity Types
1. Add Pydantic model to `src/graphiti/entity_types.py`
2. Register in `ENTITY_TYPES` dict
3. Graphiti will automatically extract entities of this type
4. Update Neo4j schema if needed (`schemas/neo4j_schema.cypher`)

### Adding a New LangChain Tool
1. Create tool in `src/agents/langchain/tools/`
2. Inherit from `BaseTool` or use `@tool` decorator
3. Register in focused_tools.py or chain configuration
4. Tool will be available to ReAct agent automatically

## Code Standards

### Python Style
- **Formatting**: Use `black` for code formatting, `isort` for import sorting
- **Type Checking**: Use `mypy` for static type analysis - type hints required for all functions
- **Imports**: Order: Standard library → Third party → Local (alphabetical within groups)
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes
- **Docstrings**: Google style with Args, Returns, Raises sections

### FastAPI Patterns
- All endpoints must use `async`/`await`
- Use dependency injection with `Depends()` for database connections and auth
- Pydantic models for request/response validation
- Error handling: Raise `HTTPException` with appropriate status codes
- Never manually manage database connections in endpoints

### Database Queries
- **Always use parameterized queries** - never string concatenation
- Neo4j: Use `src/db/neo4j_db.py` wrapper with transaction support
- PostgreSQL: Use asyncpg connection pool via `src/db/postgres.py`
- Example:
  ```python
  # GOOD
  await db.fetch("SELECT * FROM table WHERE id = $1", user_id)

  # BAD - SQL injection risk
  await db.fetch(f"SELECT * FROM table WHERE id = {user_id}")
  ```

### PydanticAI Agent Development
- Follow `src/agents/lore_chat_agent.py` template structure
- Tools use `@agent.tool` decorator with `RunContext` parameter
- System prompts should be detailed and lore-specific
- Output types: Use `StructuredResponse` or `StreamingResponse`

### Error Handling & Logging
- Use Python `logging` module with structured output
- Custom exceptions defined in `src/auth/exceptions.py` and `src/agents/`
- Graceful degradation: Provide fallbacks when optional services fail
- Always validate inputs with Pydantic before processing

### Git Workflow
- Branch naming: `feat/feature-name` or `fix/bug-description`
- Commit messages: Use conventional commits format
  - `feat: add semantic chunking pipeline`
  - `fix: resolve entity deduplication in Neo4j`
  - `docs: update API documentation`
- Never commit `.env` files - use `.env.example` as template

## Important Notes

### Data Pipeline Execution
- **Run inside container**: All pipeline scripts use `docker exec luminari-api python src/scripts/...`
- **Order matters**: load → episodes → embeddings → sync (use Makefile targets)
- **Idempotent**: Scripts track processing status in PostgreSQL flags
- **Resume capability**: `make resume` continues interrupted pipeline

### Environment Variables
Key environment variables (see `.env` or `docker-compose.yml`):
- `POSTGRES_*`: PostgreSQL connection settings
- `NEO4J_*`: Neo4j connection and credentials
- `OPENAI_API_KEY`: Required for embeddings and LLM operations
- `LORE_DIR`: Path to lore documents (`/app/lore_docs` in container)
- `API_PORT`: API server port (8003)

### Embedding Model
- Default: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- OpenAI alternative: Set `USE_OPENAI_EMBEDDINGS=true` (1536 dimensions)
- Model loads on first use for faster startup
- Dimension must match pgvector schema

### Testing Best Practices
- Mark integration tests with `@pytest.mark.integration`
- Mark data-dependent tests with `@pytest.mark.data_dependent`
- Use `--asyncio-mode=auto` for async tests (configured in pytest.ini)
- Mock external services (OpenAI, Neo4j) in unit tests

### LangChain Agent Routes
The modern agent system (`src/agents/langchain/legacy_service.py`) routes queries:
- **Direct Answer**: Factual lore questions → Retrieval + answer
- **Quest Workflow**: Quest planning requests → Multi-step quest generation
- **Story Workflow**: Story/creative requests → Narrative development with reasoning

Each route uses the same underlying hybrid RAG but applies different generation strategies.

### Authentication
- Middleware in `src/auth/` validates API keys
- Multiple key types: BACKEND_API, MCP_OPERATIONS, MCP_BACKEND_ACCESS
- Certain paths excluded from auth (e.g., `/ping`, `/docs`)
- Set `DISABLE_AUTH=true` for local development

## Common Gotchas

1. **Don't close database connections in endpoints** - They're managed globally
2. **Pipeline order matters** - Follow the semantic-pipeline sequence
3. **stable_id vs uuid** - PostgreSQL episodes.id = Neo4j Episodic.stable_id (NOT Entity.uuid)
4. **Embedding dimensions** - Must match between model and pgvector schema
5. **Docker exec for scripts** - All Makefile targets run inside container
6. **Graphiti episodes** - Episodes feed Graphiti, which creates Entity and Edge nodes
7. **Agent selection** - Query parameter or metadata determines legacy vs langchain agent
