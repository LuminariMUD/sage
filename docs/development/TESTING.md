# Testing Guide

**Version**: 0.7.10
**Status**: Production Ready
**Last Updated**: 2025-11-12

Comprehensive guide for testing Luminari Sage, covering unit tests, integration tests, and testing strategies.

---

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Markers](#test-markers)
- [Writing Tests](#writing-tests)
- [Testing Patterns](#testing-patterns)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Testing Philosophy

Luminari Sage follows a pragmatic testing approach:

1. **Unit Tests**: Fast, isolated tests for business logic
2. **Integration Tests**: Test interactions with databases and services
3. **Data-Dependent Tests**: Tests requiring loaded lore data
4. **End-to-End Tests**: Full workflow testing via API

### Test Framework

- **pytest**: Main testing framework
- **pytest-asyncio**: Async test support
- **httpx**: HTTP client for API testing
- **pytest markers**: Organize tests by type

---

## Test Structure

### Directory Layout

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures and configuration
├── test_api_integration.py        # API endpoint tests
├── test_auth.py                   # Authentication tests
├── test_correction_agent.py       # Correction system tests
├── test_langchain_chat.py         # LangChain agent tests
├── test_mcp_integration.py        # MCP server tests
├── test_quest_workflow.py         # Quest generation tests
├── test_questline_react.py        # ReAct agent tests
├── test_story_development.py      # Story workflow tests
└── test_validation_agent.py       # Validation system tests
```

### Configuration Files

#### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --asyncio-mode=auto
markers =
    integration: Integration tests requiring running services
    data_dependent: Tests requiring loaded test data
    slow: Slow running tests
    unit: Fast unit tests
```

#### conftest.py

Shared fixtures and configuration:

```python
# Test configuration
@pytest.fixture(scope="session")
def test_config():
    return {
        "api_base_url": "http://localhost:8003",
        "mcp_base_url": "http://localhost:8004",
        "test_entity_id": "40dd54d0-e6f0-43a1-a8ad-2e5c9dc17c14",
        "timeout": 10
    }

# Skip helpers
@pytest.fixture
def skip_if_no_data():
    def _skip_if_no_data(response):
        if not response:
            pytest.skip("Test data not available")
        return response
    return _skip_if_no_data
```

---

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_api_integration.py

# Run specific test function
pytest tests/test_api_integration.py::test_health_check

# Run tests matching pattern
pytest -k "test_entity"
```

### Running by Marker

```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run data-dependent tests
pytest -m data_dependent

# Exclude slow tests
pytest -m "not slow"

# Combine markers
pytest -m "integration and not slow"
```

### Coverage Reports

```bash
# Run with coverage
pytest --cov=src tests/

# Generate HTML coverage report
pytest --cov=src --cov-report=html tests/
# Open htmlcov/index.html in browser

# Show missing lines
pytest --cov=src --cov-report=term-missing tests/
```

### Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel (4 workers)
pytest -n 4

# Run tests in parallel (auto-detect CPUs)
pytest -n auto
```

---

## Test Markers

### Available Markers

#### @pytest.mark.unit

Fast unit tests with no external dependencies:

```python
@pytest.mark.unit
def test_calculate_confidence_score():
    """Test confidence calculation logic."""
    score = calculate_confidence(evidence_count=5, total_checks=10)
    assert 0.0 <= score <= 1.0
```

**When to use**: Testing pure functions, business logic, data transformations

#### @pytest.mark.integration

Tests requiring running services (PostgreSQL, Neo4j, API):

```python
@pytest.mark.integration
async def test_entity_search(test_config):
    """Test entity search endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{test_config['api_base_url']}/api/v1/entities/search",
            params={"query": "void"}
        )
        assert response.status_code == 200
```

**When to use**: API tests, database operations, service interactions

#### @pytest.mark.data_dependent

Tests requiring loaded lore data in the database:

```python
@pytest.mark.data_dependent
async def test_search_voids_wake(test_config, skip_if_no_data):
    """Test searching for specific entity."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{test_config['api_base_url']}/api/v1/entities/search",
            params={"query": "Void's Wake"}
        )
        skip_if_no_data(response)
        data = response.json()
        assert len(data) > 0
```

**When to use**: Tests that query specific lore content

#### @pytest.mark.slow

Long-running tests (>5 seconds):

```python
@pytest.mark.slow
@pytest.mark.integration
async def test_full_validation_workflow():
    """Test complete validation workflow."""
    # This test takes 30+ seconds
    result = await run_full_validation()
    assert result.success
```

**When to use**: Full workflow tests, bulk operations, comprehensive validations

---

## Writing Tests

### Test Structure

Follow the **Arrange-Act-Assert** pattern:

```python
@pytest.mark.unit
def test_entity_extraction():
    # Arrange: Set up test data
    text = "The Crystal Dwarves of Hir-Pesh worship the Earth Mother."

    # Act: Execute the function
    entities = extract_entities(text)

    # Assert: Verify results
    assert len(entities) == 2
    assert any(e.name == "Crystal Dwarves" for e in entities)
    assert any(e.name == "Earth Mother" for e in entities)
```

### Async Tests

Use `async def` for async tests (pytest-asyncio auto-mode):

```python
@pytest.mark.integration
async def test_async_database_query():
    """Test async database operations."""
    db = await get_postgres_db()
    result = await db.fetchrow("SELECT COUNT(*) FROM episodes")
    assert result['count'] >= 0
```

### Fixtures

Create reusable test fixtures:

```python
@pytest.fixture
async def test_entity():
    """Create a test entity."""
    db = await get_neo4j_db()
    entity_id = await db.create_entity({
        "name": "Test Entity",
        "entity_type": "Location"
    })
    yield entity_id
    # Cleanup
    await db.delete_entity(entity_id)

@pytest.mark.integration
async def test_with_fixture(test_entity):
    """Test using fixture."""
    db = await get_neo4j_db()
    entity = await db.get_entity(test_entity)
    assert entity['name'] == "Test Entity"
```

### Parameterized Tests

Test multiple inputs efficiently:

```python
@pytest.mark.unit
@pytest.mark.parametrize("query,expected_count", [
    ("crystal dwarves", 5),
    ("void's wake", 3),
    ("nonexistent entity", 0),
])
def test_search_results(query, expected_count):
    """Test search with different queries."""
    results = search_entities(query)
    assert len(results) == expected_count
```

### Mocking External Services

Mock external dependencies for unit tests:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.unit
@patch('src.agents.openai_client.create_embedding')
async def test_embedding_generation(mock_embedding):
    """Test embedding generation with mocked OpenAI."""
    mock_embedding.return_value = [0.1] * 384

    result = await generate_embedding("test text")

    assert len(result) == 384
    mock_embedding.assert_called_once()
```

---

## Testing Patterns

### Testing API Endpoints

```python
@pytest.mark.integration
async def test_health_endpoint(test_config):
    """Test health check endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{test_config['api_base_url']}/api/v1/health"
        )
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
```

### Testing Authentication

```python
@pytest.mark.integration
async def test_protected_endpoint_requires_auth(test_config):
    """Test that protected endpoints require authentication."""
    async with httpx.AsyncClient() as client:
        # No API key
        response = await client.get(
            f"{test_config['api_base_url']}/api/v1/validate"
        )
        assert response.status_code == 403

        # With API key
        response = await client.post(
            f"{test_config['api_base_url']}/api/v1/validate",
            headers={"X-API-Key": os.getenv("BACKEND_API_KEY")},
            json={"content": "Test content"}
        )
        assert response.status_code == 200
```

### Testing Database Operations

```python
@pytest.mark.integration
async def test_episode_creation():
    """Test creating episodes in PostgreSQL."""
    db = await get_postgres_db()

    # Create test document
    doc_id = await db.fetchval("""
        INSERT INTO lore_documents (stable_id, title, document_type,
                                     source_file, body_md)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, "test-doc", "Test Doc", "lore_note", "test.md", "# Test")

    # Create episode
    episode_id = await db.fetchval("""
        INSERT INTO episodes (document_id, episode_index, text)
        VALUES ($1, $2, $3)
        RETURNING id
    """, doc_id, 0, "Test episode text")

    assert episode_id is not None

    # Cleanup
    await db.execute("DELETE FROM lore_documents WHERE id = $1", doc_id)
```

### Testing Graph Queries

```python
@pytest.mark.integration
@pytest.mark.data_dependent
async def test_entity_relationships():
    """Test finding entity relationships in Neo4j."""
    db = await get_neo4j_db()

    result = await db.execute_query("""
        MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(connected:Entity)
        RETURN e.name as source,
               r.semantic_type as relationship,
               connected.name as target
        LIMIT 5
    """, {"name": "Void's Wake"})

    assert len(result) > 0
    assert all('source' in record for record in result)
```

### Testing Async Workflows

```python
@pytest.mark.integration
@pytest.mark.slow
async def test_validation_workflow():
    """Test complete validation workflow."""
    from src.agents.relationship_validator import RelationshipValidator

    validator = RelationshipValidator()

    # Run validation
    report = await validator.validate_relationships(limit=10)

    # Verify report structure
    assert report.report_id is not None
    assert report.total_items_checked > 0
    assert isinstance(report.findings_count, int)
    assert report.execution_time_seconds > 0
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: test-only-postgres-password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      neo4j:
        image: neo4j:5.15
        env:
          NEO4J_AUTH: neo4j/password
        options: >-
          --health-cmd "cypher-shell 'RETURN 1'"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run unit tests
        run: pytest -m unit --cov=src

      - name: Run integration tests
        run: pytest -m integration
        env:
          POSTGRES_HOST: localhost
          NEO4J_URI: bolt://localhost:7687
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Example `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-unit
        name: pytest unit tests
        entry: pytest -m unit
        language: system
        pass_filenames: false
        always_run: true
```

---

## Troubleshooting

### Common Issues

#### Services Not Running

**Error**: `Connection refused` or `Service not available`

**Solution**:

```bash
# Check services are running
docker compose ps

# Start services if needed
docker compose up -d

# Check logs
docker compose logs api
```

#### Test Data Not Available

**Error**: Tests skipped with "Test data not available"

**Solution**:

```bash
# Load test data
make load-canon
make sync-to-graphiti

# Or use sample data
make load-sample-data
```

#### Async Test Errors

**Error**: `RuntimeError: Event loop is closed`

**Solution**: Ensure pytest-asyncio is configured correctly:

```ini
# pytest.ini
[tool:pytest]
asyncio_mode = auto
```

#### Database Connection Issues

**Error**: `asyncpg.exceptions.ConnectionDoesNotExistError`

**Solution**:

```python
# Use proper connection management
from src.db import get_postgres_db, get_neo4j_db

async def test_example():
    # Get connections (don't create new ones)
    postgres = await get_postgres_db()
    neo4j = await get_neo4j_db()

    # Don't close connections in tests
    # They're managed by the application
```

### Debugging Tests

#### Verbose Output

```bash
# Show print statements
pytest -s

# Show full traceback
pytest --tb=long

# Show local variables in traceback
pytest -l
```

#### Run Single Test with Debugging

```bash
# Drop into debugger on failure
pytest --pdb

# Drop into debugger at start
pytest --trace

# Use breakpoint() in code
def test_example():
    result = some_function()
    breakpoint()  # Debugger stops here
    assert result == expected
```

#### Logging

```python
import logging

@pytest.mark.integration
async def test_with_logging(caplog):
    """Test with log capture."""
    caplog.set_level(logging.DEBUG)

    result = await some_async_function()

    # Check logs
    assert "Expected log message" in caplog.text
```

---

## Best Practices

### 1. Test Independence

Each test should be independent and not rely on other tests:

```python
# BAD: Tests depend on order
def test_create_entity():
    global entity_id
    entity_id = create_entity("Test")

def test_update_entity():
    update_entity(entity_id, name="Updated")  # Fails if previous test skipped

# GOOD: Tests are independent
@pytest.fixture
def test_entity():
    entity_id = create_entity("Test")
    yield entity_id
    delete_entity(entity_id)

def test_update_entity(test_entity):
    update_entity(test_entity, name="Updated")
```

### 2. Clear Test Names

Use descriptive test names that explain what is being tested:

```python
# BAD
def test_1():
    ...

# GOOD
def test_entity_search_returns_results_for_valid_query():
    ...

def test_entity_search_returns_empty_list_for_nonexistent_entity():
    ...
```

### 3. Test One Thing

Each test should verify one specific behavior:

```python
# BAD: Testing too much
def test_entity_operations():
    entity = create_entity("Test")
    assert entity.name == "Test"
    update_entity(entity.id, name="Updated")
    assert get_entity(entity.id).name == "Updated"
    delete_entity(entity.id)
    assert get_entity(entity.id) is None

# GOOD: Separate tests
def test_create_entity():
    entity = create_entity("Test")
    assert entity.name == "Test"

def test_update_entity(test_entity):
    update_entity(test_entity, name="Updated")
    assert get_entity(test_entity).name == "Updated"
```

### 4. Use Appropriate Markers

Mark tests correctly for efficient testing:

```python
@pytest.mark.unit  # Fast, no external dependencies
def test_calculate_score():
    ...

@pytest.mark.integration  # Requires services
async def test_api_endpoint():
    ...

@pytest.mark.data_dependent  # Requires loaded data
@pytest.mark.integration
async def test_search_specific_entity():
    ...
```

### 5. Clean Up Resources

Always clean up test resources:

```python
@pytest.fixture
async def temp_document():
    """Create temporary test document."""
    db = await get_postgres_db()
    doc_id = await create_test_document(db)
    yield doc_id
    # Cleanup happens even if test fails
    await db.execute("DELETE FROM lore_documents WHERE id = $1", doc_id)
```

---

## Related Documentation

- [Developer Guide](DEVELOPER_GUIDE.md)
- [Contributing Guide](CONTRIBUTING.md)
- [API Reference](../reference/API_REFERENCE.md)
- [Architecture](../reference/ARCHITECTURE.md)
