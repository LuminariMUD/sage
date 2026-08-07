# Luminari Sage Developer Guide

**Last Updated**: November 12, 2025
**Version**: 0.7.14
**Audience**: Developers, Contributors

## Overview

This guide covers development environment setup, coding patterns, testing, and debugging for Luminari Sage. Whether you're adding features, fixing bugs, or extending the system, this guide will help you work effectively with the codebase.

## Development Environment Setup

### Prerequisites

- Python 3.11+ (containers run 3.13)
- Node.js 18+ (for frontend development)
- Docker & Docker Compose
- Git
- VS Code or PyCharm (recommended IDEs)

### Initial Setup

#### 1. Clone and Setup Repository

```bash
# Clone repository
git clone https://github.com/LuminariMUD/sage.git
cd sage

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-core.txt
pip install -r requirements-dev.txt  # Development tools

# Install pre-commit hooks
pre-commit install
```

#### 2. Environment Configuration

```bash
# Copy example environment
cp .env.example .env.development
chmod 600 .env.development

# Configure for development
cat >> .env.development << EOF
DEBUG=true
LOG_LEVEL=DEBUG
RELOAD=true
OPENAI_API_KEY=
EOF

# Use development environment
export ENV_FILE=.env.development
```

#### 3. Local Services Setup

```bash
# Start development databases
docker compose -f docker-compose.dev.yml up -d postgres neo4j

# Wait for services
sleep 10

# Initialize databases
python scripts/init_database.py
python scripts/init_neo4j.py
```

#### 4. Run Development Server

```bash
# With auto-reload
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8003

# Or use the Makefile
make dev
```

## Project Structure

```
luminari-sage/
├── src/
│   ├── api/                 # FastAPI application
│   │   ├── main.py          # Main application file
│   │   └── routes/          # API route handlers
│   ├── agents/              # AI agents
│   │   ├── langchain/       # LangChain agents
│   │   │   ├── chains/      # Individual chains
│   │   │   ├── tools/       # Agent tools
│   │   │   └── util/        # Utilities
│   │   └── pydantic_ai/     # PydanticAI agents
│   ├── db/                  # Database connections
│   │   ├── postgres.py      # PostgreSQL client
│   │   └── neo4j_db.py      # Neo4j client
│   ├── auth/                # Authentication
│   └── graphiti/            # Graphiti integration
├── scripts/                 # Data pipeline scripts
├── tests/                   # Test suites
├── docs/                    # Documentation
├── web/                     # Web interface
└── docker/                  # Docker configurations
```

## Code Style Guide

### Python Style

We follow PEP 8 with some modifications:

- Line length: 100 characters
- Use type hints for all functions
- Docstrings for all public functions

```python
from typing import Dict, List, Optional

async def process_query(
    query: str,
    limit: int = 10,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process a user query and return results.

    Args:
        query: The search query
        limit: Maximum results to return
        metadata: Optional metadata

    Returns:
        Dictionary containing search results

    Raises:
        ValueError: If query is empty
    """
    if not query:
        raise ValueError("Query cannot be empty")

    # Implementation
    return {"results": []}
```

### Async/Await Pattern

Use async/await consistently:

```python
# Good
async def get_data():
    result = await database.fetch("SELECT ...")
    return result

# Bad - mixing sync and async
def get_data():
    result = asyncio.run(database.fetch("SELECT ..."))
    return result
```

### Error Handling

Always use specific exceptions:

```python
# Good
try:
    result = await process_data(input)
except ValidationError as e:
    logger.error(f"Validation failed: {e}")
    raise HTTPException(status_code=400, detail=str(e))
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise HTTPException(status_code=503, detail="Service unavailable")

# Bad
try:
    result = await process_data(input)
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

## System-Specific Development

### Working with the Validation System

The validation system (`src/agents/relationship_validator.py`) checks lore consistency and stores findings for review.

#### Architecture

- **Validator**: `RelationshipValidator` class performs validation checks
- **Findings Storage**: PostgreSQL `validation_findings` table
- **Review Workflow**: Findings marked as reviewed to prevent re-reporting
- **Statistics**: Track validation pass/fail rates

#### Adding New Validation Rules

```python
# src/agents/relationship_validator.py
from typing import List, Dict, Any

class RelationshipValidator:
    async def validate_custom_rule(
        self,
        entity_id: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Add a custom validation rule.

        Returns:
            List of findings (issues found)
        """
        findings = []

        # Example: Check if deity has alignment
        if context.get("entity_type") == "Deity":
            if not context.get("alignment"):
                findings.append({
                    "severity": "warning",
                    "category": "missing_attribute",
                    "message": "Deity missing alignment attribute",
                    "entity_id": entity_id
                })

        return findings
```

#### Testing Validation

```python
# tests/test_validation.py
import pytest
from src.agents.relationship_validator import RelationshipValidator

@pytest.mark.asyncio
async def test_custom_validation():
    validator = RelationshipValidator()

    context = {
        "entity_type": "Deity",
        "name": "Tyr",
        # Missing alignment
    }

    findings = await validator.validate_custom_rule("test-id", context)

    assert len(findings) > 0
    assert findings[0]["category"] == "missing_attribute"
```

### Working with the Correction System

The correction system manages batch corrections with rollback capabilities.

#### Architecture

- **Correction Records**: PostgreSQL `corrections` table tracks all changes
- **Batch Operations**: Group related corrections for atomic rollback
- **Audit Trail**: Complete history of what changed and why
- **Rollback**: Revert corrections individually or by batch

#### Implementing Corrections

```python
# src/agents/correction_manager.py (example)
from uuid import uuid4
from datetime import datetime

async def apply_correction(
    postgres_db,
    entity_id: str,
    field: str,
    old_value: str,
    new_value: str,
    reason: str,
    batch_id: str = None
):
    """Apply a correction and record it."""

    if not batch_id:
        batch_id = str(uuid4())

    correction_id = str(uuid4())

    # Apply the change (example: update Neo4j)
    await neo4j_db.execute_query("""
        MATCH (e:Entity {uuid: $entity_id})
        SET e[$field] = $new_value
    """, {"entity_id": entity_id, "field": field, "new_value": new_value})

    # Record the correction
    await postgres_db.execute("""
        INSERT INTO corrections (
            id, batch_id, entity_id, field, old_value, new_value,
            reason, applied_at, applied_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """, correction_id, batch_id, entity_id, field, old_value,
         new_value, reason, datetime.utcnow(), "system")

    return correction_id, batch_id
```

#### Testing Corrections

```python
@pytest.mark.integration
async def test_correction_rollback():
    # Apply correction
    correction_id, batch_id = await apply_correction(
        postgres_db,
        entity_id="test-entity",
        field="name",
        old_value="Old Name",
        new_value="New Name",
        reason="Test correction"
    )

    # Verify change applied
    entity = await get_entity("test-entity")
    assert entity["name"] == "New Name"

    # Rollback
    await rollback_batch(postgres_db, batch_id)

    # Verify rollback
    entity = await get_entity("test-entity")
    assert entity["name"] == "Old Name"
```

### Working with the Hybrid RAG System

The RAG system combines three search strategies.

#### Components

1. **Vector Search**: PostgreSQL pgvector for semantic similarity
2. **Full-Text Search**: PostgreSQL FTS for keyword matching
3. **Graph Enhancement**: Neo4j for entity relationships
4. **Reciprocal Rank Fusion**: Combines results with RRF scoring

#### Example RAG Query

```python
# src/api/main.py (simplified)
async def rag_query(query: str, limit: int = 10):
    # 1. Generate query embedding
    embedding = await generate_embedding(query)

    # 2. Vector search
    vector_results = await postgres_db.fetch("""
        SELECT id, text, 1 - (embedding <=> $1::vector) as similarity
        FROM episodes
        WHERE 1 - (embedding <=> $1::vector) > 0.7
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """, embedding, limit)

    # 3. Full-text search
    fts_results = await postgres_db.fetch("""
        SELECT id, text, ts_rank(fts_vector, plainto_tsquery($1)) as rank
        FROM episodes
        WHERE fts_vector @@ plainto_tsquery($1)
        ORDER BY rank DESC
        LIMIT $2
    """, query, limit)

    # 4. Reciprocal Rank Fusion
    combined = reciprocal_rank_fusion([vector_results, fts_results])

    # 5. Enhance with graph context
    for result in combined:
        entities = await get_related_entities(result["id"])
        result["entities"] = entities

    return combined
```

## Adding New Features

### Creating a New LangChain Agent

#### 1. Define Agent Class

```python
# src/agents/langchain/chains/my_agent.py
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import Dict, Any

class MyAgent(Runnable):
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant."),
            ("human", "{query}")
        ])

    def invoke(self, input: Dict[str, Any], config: Dict | None = None) -> Dict[str, Any]:
        query = input.get("query", "")
        previous_context = input.get("previous_context", "")

        # Add context handling
        if previous_context:
            query = f"Context: {previous_context}\n\nQuery: {query}"

        # Process with LLM
        formatted_prompt = self.prompt.format_prompt(query=query)
        response = self.llm.invoke(formatted_prompt.to_messages())

        return {
            "answer": response.content,
            "metadata": {"agent": "my_agent"}
        }
```

#### 2. Register with Service

```python
# src/agents/langchain/service.py
from .chains.my_agent import MyAgent

class LangChainChatService:
    def __init__(self):
        # ... existing agents
        self.my_agent = MyAgent()
```

#### 3. Add Classification

```python
# src/agents/langchain/util/classifier.py
# Add to Route type
Route = Literal[..., "my_agent_route"]

# Add patterns
MY_AGENT_PATTERNS = re.compile(r"\b(pattern1|pattern2)\b", re.I)

# Update classification logic
if MY_AGENT_PATTERNS.search(text):
    return ("my_agent_route", 0.8)
```

#### 4. Write Tests

```python
# tests/test_my_agent.py
import pytest
from src.agents.langchain.chains.my_agent import MyAgent

@pytest.mark.asyncio
async def test_my_agent():
    agent = MyAgent()
    result = agent.invoke({"query": "Test query"})

    assert "answer" in result
    assert result["metadata"]["agent"] == "my_agent"
```

### Adding API Endpoints

#### 1. Create Route Handler

```python
# src/api/routes/my_feature.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/my-feature", tags=["my-feature"])

class MyRequest(BaseModel):
    data: str

class MyResponse(BaseModel):
    result: str

@router.post("/process", response_model=MyResponse)
async def process_data(request: MyRequest):
    try:
        # Process request
        result = await do_processing(request.data)
        return MyResponse(result=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### 2. Register Router

```python
# src/api/main.py
from src.api.routes import my_feature

app.include_router(my_feature.router)
```

#### 3. Add Tests

```python
# tests/test_api_my_feature.py
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_process_data():
    response = client.post(
        "/api/v1/my-feature/process",
        json={"data": "test"},
        headers={"X-API-Key": "unit-test-key"}
    )
    assert response.status_code == 200
    assert "result" in response.json()
```

## Testing

### Test Structure

```
tests/
├── unit/              # Unit tests
│   ├── test_agents.py
│   └── test_utils.py
├── integration/       # Integration tests
│   ├── test_api.py
│   └── test_database.py
├── e2e/              # End-to-end tests
│   └── test_chat_flow.py
└── fixtures/         # Test data
    └── sample_data.json
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_agents.py

# Run with verbose output
pytest -v

# Run only marked tests
pytest -m "not slow"
```

### Writing Tests

#### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
from src.agents.langchain.chains.quest_planner import QuestPlannerChain

class TestQuestPlanner:
    @pytest.fixture
    def planner(self):
        return QuestPlannerChain()

    def test_plan_generation(self, planner):
        input_data = {
            "query": "Create a quest about dragons",
            "context_blocks": ["Dragon lore context"]
        }

        with patch.object(planner.llm, 'invoke') as mock_llm:
            mock_llm.return_value.content = json.dumps({
                "title": "Dragon Quest",
                "objective": "Defeat the dragon",
                "phases": []
            })

            result = planner.invoke(input_data)

            assert "plan" in result
            assert result["plan"]["title"] == "Dragon Quest"
```

#### Integration Test Example

```python
import pytest
from src.db.postgres import get_postgres_db

@pytest.mark.asyncio
async def test_database_connection():
    db = await get_postgres_db()

    # Test query
    result = await db.fetchrow("SELECT 1 as num")
    assert result["num"] == 1

    # Cleanup
    await db.close()
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from typing import Dict, Any

@pytest.fixture
def sample_context() -> List[str]:
    return [
        "The Crystal Dwarves are silicon-based beings.",
        "They emerged during the Age of Crystal."
    ]

@pytest.fixture
async def test_db():
    # Setup test database
    db = await create_test_database()
    yield db
    # Teardown
    await cleanup_test_database(db)
```

## Debugging

### Debug Configuration (VS Code)

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "src.api.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8003"
      ],
      "env": {
        "DEBUG": "true",
        "LOG_LEVEL": "DEBUG",
        "DISABLE_AUTH": "true"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "Debug Data Pipeline Script",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "env": {
        "DEBUG": "true",
        "LOG_LEVEL": "DEBUG"
      }
    },
    {
      "name": "Debug Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}", "-v", "-s"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Logging Best Practices

```python
import logging
from typing import Optional

# Use module-level logger
logger = logging.getLogger(__name__)

def process_entity(entity_id: str, data: dict) -> Optional[dict]:
    """Process an entity with comprehensive logging."""

    # Debug: Detailed info for development
    logger.debug(f"Processing entity {entity_id} with {len(data)} fields")

    # Info: Important business logic events
    logger.info(f"Starting entity processing: {entity_id}")

    try:
        # Process data
        result = transform_data(data)

        # Success logging
        logger.info(f"Entity {entity_id} processed successfully")
        return result

    except ValidationError as e:
        # Warning: Recoverable errors
        logger.warning(f"Validation failed for {entity_id}: {e}")
        return None

    except Exception as e:
        # Error: Unexpected failures with full traceback
        logger.error(
            f"Failed to process entity {entity_id}",
            exc_info=True,
            extra={"entity_id": entity_id, "data_keys": list(data.keys())}
        )
        raise
```

### Debugging Database Queries

```python
# Debug PostgreSQL queries
async def debug_query():
    postgres_db = await get_postgres_db()

    # Enable query logging
    await postgres_db.execute("SET log_statement = 'all'")

    # Run query with timing
    import time
    start = time.time()
    results = await postgres_db.fetch("SELECT * FROM episodes WHERE ...")
    duration = time.time() - start

    logger.debug(f"Query returned {len(results)} rows in {duration:.3f}s")
    return results

# Debug Neo4j queries
async def debug_neo4j_query():
    neo4j_db = await get_neo4j_db()

    query = """
    MATCH (e:Entity {uuid: $entity_id})
    OPTIONAL MATCH (e)-[r]->(related)
    RETURN e, r, related
    """

    # Log query before execution
    logger.debug(f"Executing Neo4j query: {query}")

    results = await neo4j_db.execute_query(
        query,
        {"entity_id": "test-id"}
    )

    logger.debug(f"Neo4j returned {len(results.records)} records")
    return results
```

### Debugging LangChain Agents

```python
# Enable LangChain debugging
import os
os.environ["LANGCHAIN_VERBOSE"] = "true"
os.environ["LANGCHAIN_DEBUG"] = "true"

# Add callbacks for detailed tracing
from langchain.callbacks import StdOutCallbackHandler

chain = MyChain()
result = chain.invoke(
    {"query": "test query"},
    config={"callbacks": [StdOutCallbackHandler()]}
)
```

### Performance Profiling

```python
import cProfile
import pstats
from io import StringIO
import time
from functools import wraps

def profile_function(func):
    """Decorator to profile a function."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()

        result = func(*args, **kwargs)

        pr.disable()
        s = StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats(20)

        logger.info(f"Profile results for {func.__name__}:\n{s.getvalue()}")
        return result

    return wrapper

# Usage
@profile_function
def expensive_operation():
    # Your code here
    pass

# Or manually:
def profile_section():
    import cProfile

    pr = cProfile.Profile()
    pr.enable()

    # Code to profile
    result = expensive_operation()

    pr.disable()
    pr.print_stats(sort='cumulative')

    return result
```

### Debugging Docker Services

```bash
# View live logs
docker compose logs -f api

# Check specific service logs
docker compose logs --tail=100 postgres
docker compose logs --tail=100 neo4j

# Execute commands in container
docker compose exec api bash

# Check Python environment
docker compose exec api python --version
docker compose exec api pip list

# Test database connections from container
docker compose exec api python -c "
from src.db.postgres import get_postgres_db
import asyncio
asyncio.run(get_postgres_db())
print('PostgreSQL connection OK')
"

# Check Neo4j from container
docker compose exec neo4j neo4j status

# Monitor resource usage
docker stats

# Inspect configuration without displaying credentials
docker compose exec api python -c \
  "import os; names=('POSTGRES_PASSWORD','NEO4J_PASSWORD','OPENAI_API_KEY'); print(*(name + ': ' + ('SET' if os.getenv(name) else 'MISSING') for name in names), sep='\n')"
```

### Common Debugging Scenarios

#### Issue: "Database connection refused"

```bash
# Check if services are running
docker compose ps

# Check network connectivity
docker compose exec api ping postgres
docker compose exec api ping neo4j

# Verify environment variables
docker compose exec api python -c "import os; print(os.getenv('POSTGRES_HOST'))"

# Test connection manually
docker compose exec postgres psql -U sage sage_db -c "SELECT 1;"
```

#### Issue: "Embeddings failing"

```python
# Debug embedding generation
async def debug_embeddings():
    from src.utils.embeddings import generate_embedding

    # Test with simple text
    test_text = "Test embedding"

    try:
        embedding = await generate_embedding(test_text)
        logger.info(f"Generated embedding: dimension={len(embedding)}")
        return embedding
    except Exception as e:
        logger.error(f"Embedding failed: {e}", exc_info=True)
        raise
```

#### Issue: "Agent not responding correctly"

```python
# Add detailed agent debugging
async def debug_agent_query(query: str):
    from src.agents.langchain.legacy_service import LangChainChatService

    service = LangChainChatService()

    # Enable verbose mode
    import logging
    logging.getLogger("langchain").setLevel(logging.DEBUG)

    # Track execution
    logger.info(f"Query: {query}")

    async for chunk in service.chat_stream(query):
        logger.debug(f"Chunk: {chunk}")
        yield chunk
```

## Database Migrations

### Creating Migrations

```bash
# Create migration file
alembic revision -m "Add new table"

# Edit migration file
nano alembic/versions/xxx_add_new_table.py
```

### Migration Example

```python
"""Add user preferences table

Revision ID: abc123
Revises: def456
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False)
    )

    op.create_index('idx_user_preferences_user_id', 'user_preferences', ['user_id'])

def downgrade():
    op.drop_index('idx_user_preferences_user_id')
    op.drop_table('user_preferences')
```

### Running Migrations

```bash
# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current
```

## Contributing

### Workflow

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes
4. Write/update tests
5. Run tests (`pytest`)
6. Commit changes (`git commit -m 'Add amazing feature'`)
7. Push branch (`git push origin feature/amazing-feature`)
8. Open Pull Request

### Commit Message Convention

```
type(scope): description

[optional body]

[optional footer]
```

Types:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style
- `refactor`: Refactoring
- `test`: Tests
- `chore`: Maintenance

Examples:

```
feat(agents): Add weather prediction agent
fix(api): Handle empty query in search endpoint
docs(readme): Update installation instructions
```

### Code Review Checklist

- [ ] Tests pass
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] No sensitive data exposed
- [ ] Performance impact considered
- [ ] Error handling implemented
- [ ] Logging added where appropriate

## Performance Optimization

### Profiling Queries

```python
# PostgreSQL query profiling
async def profile_query():
    db = await get_postgres_db()

    # Enable query timing
    await db.execute("SET log_statement = 'all'")
    await db.execute("SET log_duration = on")

    # Run query
    start = time.time()
    result = await db.fetch("SELECT ...")
    duration = time.time() - start

    logger.info(f"Query took {duration:.3f}s")
    return result
```

### Caching Strategy

```python
from functools import lru_cache
from typing import Optional
import hashlib

class CacheManager:
    def __init__(self, ttl: int = 300):
        self.cache = {}
        self.ttl = ttl

    def get_cache_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_str = f"{args}{kwargs}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def get_or_compute(self, key: str, compute_func):
        """Get from cache or compute."""
        if key in self.cache:
            return self.cache[key]

        result = await compute_func()
        self.cache[key] = result
        return result
```

### Async Best Practices

```python
# Good - concurrent execution
async def process_multiple(items: List[str]):
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    return results

# Bad - sequential execution
async def process_multiple_bad(items: List[str]):
    results = []
    for item in items:
        result = await process_item(item)
        results.append(result)
    return results
```

## Troubleshooting

### Common Issues

#### Import Errors

```python
# Add project root to path
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
```

#### Async Context Issues

```python
# Create event loop for sync context
import asyncio

def sync_wrapper():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_function())
    finally:
        loop.close()
```

#### Database Connection Pool

```python
# Reset connection pool
async def reset_pool():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
    _db_pool = await asyncpg.create_pool(DATABASE_URL)
```

## Resources

### Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [LangChain Docs](https://python.langchain.com/)
- [PydanticAI Docs](https://ai.pydantic.dev/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/)

### Tools

- [Postman](https://www.postman.com/) - API testing
- [pgAdmin](https://www.pgadmin.org/) - PostgreSQL management
- [Neo4j Browser](http://localhost:7474) - Graph visualization
- [Ray Dashboard](http://localhost:8265) - Distributed computing

### Learning Resources

- [Async Python Patterns](https://docs.python.org/3/library/asyncio-task.html)
- [Graph Database Concepts](https://neo4j.com/developer/graph-database/)
- [RAG Architecture](https://www.pinecone.io/learn/retrieval-augmented-generation/)
- [LLM Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)

---

_For deployment instructions, see the [Deployment Guide](./DEPLOYMENT_GUIDE.md)._
_For architecture overview, see the [System Architecture](./ARCHITECTURE.md)._
