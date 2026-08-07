# Contributing to Luminari Sage

**Last Updated**: November 12, 2025
**Version**: 0.7.16

Thank you for considering contributing to Luminari Sage! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style Guide](#code-style-guide)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Documentation](#documentation)

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inspiring community for all. Please be respectful and constructive in your interactions.

### Expected Behavior

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive criticism
- Accept responsibility for mistakes
- Prioritize the community and project goals

### Unacceptable Behavior

- Harassment, trolling, or discriminatory comments
- Personal attacks or inflammatory language
- Publishing private information without permission
- Unethical or unprofessional conduct

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- Python 3.11+ installed (containers and CI run 3.13)
- Docker and Docker Compose
- Git configured with your name and email
- A GitHub account

### Setting Up Development Environment

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/sage.git
cd sage

# 3. Add upstream remote
git remote add upstream https://github.com/LuminariMUD/sage.git

# 4. Create development environment
cp .env.example .env
chmod 600 .env
# Edit .env with your settings

# 5. Start services
docker compose up -d

# 6. Run tests to verify setup
pytest -m unit
```

## Development Workflow

### Creating a Feature Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/bug-description
```

### Making Changes

1. **Write Tests First** (TDD recommended)

   ```bash
   # Create test file
   touch tests/test_your_feature.py

   # Write failing tests
   # Then implement feature
   ```

2. **Implement Changes**
   - Follow the [Code Style Guide](#code-style-guide)
   - Add docstrings to all public functions
   - Use type hints consistently
   - Keep functions focused and small

3. **Run Tests**

   ```bash
   # Run all tests
   pytest

   # Run specific test file
   pytest tests/test_your_feature.py -v

   # Run with coverage
   pytest --cov=src tests/
   ```

4. **Test Locally**
   ```bash
   # Test API endpoints
   docker compose up -d
   curl http://localhost:8003/api/v1/your-endpoint

   # Check logs
   docker compose logs -f api
   ```

### Keeping Your Fork Updated

```bash
# Fetch upstream changes
git fetch upstream

# Merge into your main branch
git checkout main
git merge upstream/main

# Rebase your feature branch
git checkout feature/your-feature-name
git rebase main
```

## Code Style Guide

### Python Style (PEP 8 + Modifications)

**General Rules:**

- Line length: 100 characters maximum
- Indentation: 4 spaces (no tabs)
- Imports: Organize with isort
- Formatting: Use Black formatter
- Type hints: Required for all functions

**Example:**

```python
from typing import Dict, List, Optional

async def process_entity(
    entity_id: str,
    attributes: Dict[str, Any],
    validate: bool = True
) -> Optional[Dict[str, Any]]:
    """Process an entity and return validated results.

    Args:
        entity_id: Unique identifier for the entity
        attributes: Entity attributes to process
        validate: Whether to run validation (default: True)

    Returns:
        Processed entity dictionary or None if validation fails

    Raises:
        ValueError: If entity_id is empty
        ValidationError: If attributes fail validation

    Example:
        >>> result = await process_entity("uuid-123", {"name": "Tyr"})
        >>> print(result["name"])
        Tyr
    """
    if not entity_id:
        raise ValueError("entity_id cannot be empty")

    if validate:
        validated = await validate_attributes(attributes)
        if not validated:
            return None

    return {"id": entity_id, **attributes}
```

### Import Organization

```python
# 1. Standard library imports
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

# 2. Third-party imports
import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 3. Local imports
from src.db.postgres import get_postgres_db
from src.db.neo4j_db import get_neo4j_db
from src.utils.logging import get_logger
```

### Naming Conventions

- **Functions/Variables**: `snake_case`

  ```python
  def calculate_similarity_score():
      user_input = get_input()
  ```

- **Classes**: `PascalCase`

  ```python
  class EntityValidator:
      pass
  ```

- **Constants**: `UPPER_SNAKE_CASE`

  ```python
  MAX_RETRIES = 3
  DEFAULT_TIMEOUT = 30
  ```

- **Private members**: Leading underscore
  ```python
  def _internal_helper():
      pass
  ```

### Async/Await Pattern

Always use async/await for I/O operations:

```python
# Good
async def fetch_data():
    postgres_db = await get_postgres_db()
    results = await postgres_db.fetch("SELECT * FROM episodes")
    return results

# Bad - blocking
def fetch_data():
    postgres_db = get_postgres_db_sync()
    results = postgres_db.fetch("SELECT * FROM episodes")
    return results
```

### Error Handling

Use specific exceptions and provide context:

```python
# Good
try:
    result = await process_data(input)
except ValidationError as e:
    logger.error(f"Validation failed for input {input}: {e}")
    raise HTTPException(
        status_code=400,
        detail=f"Invalid input: {str(e)}"
    )
except DatabaseError as e:
    logger.error(f"Database error: {e}", exc_info=True)
    raise HTTPException(
        status_code=503,
        detail="Service temporarily unavailable"
    )

# Bad
try:
    result = await process_data(input)
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

## Testing Requirements

### Test Coverage

- **Minimum coverage**: 80% for new code
- **Required tests**:
  - Unit tests for all new functions
  - Integration tests for API endpoints
  - Data-dependent tests marked appropriately

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch

# Test file: tests/test_feature.py

@pytest.mark.unit
def test_function_with_valid_input():
    """Test function behavior with valid input."""
    result = my_function("valid_input")
    assert result == expected_output

@pytest.mark.unit
def test_function_with_invalid_input():
    """Test function error handling with invalid input."""
    with pytest.raises(ValueError):
        my_function(None)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_api_endpoint():
    """Test API endpoint with database."""
    # Setup
    async with TestClient(app) as client:
        # Execute
        response = await client.post("/api/v1/endpoint", json={"data": "test"})

        # Assert
        assert response.status_code == 200
        assert response.json()["result"] == "expected"

@pytest.mark.data_dependent
async def test_with_loaded_data():
    """Test requiring loaded lore data."""
    results = await search_lore("crystal dwarves")
    assert len(results) > 0
```

### Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest -m unit

# Integration tests
pytest -m integration

# With coverage
pytest --cov=src --cov-report=html tests/

# Specific file
pytest tests/test_feature.py -v

# Stop on first failure
pytest -x
```

### Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.unit          # Fast unit tests with no external dependencies
@pytest.mark.integration   # Tests requiring database connections
@pytest.mark.data_dependent # Tests requiring loaded lore data
@pytest.mark.slow          # Long-running tests
@pytest.mark.skip          # Temporarily skip test
```

## Pull Request Process

### Before Submitting

1. **Run all tests**

   ```bash
   pytest
   ```

2. **Check code style**

   ```bash
   # Format with Black
   black src/ tests/

   # Sort imports
   isort src/ tests/

   # Lint with flake8
   flake8 src/ tests/
   ```

3. **Update documentation**
   - Add/update docstrings
   - Update relevant markdown docs
   - Add example usage if needed

4. **Test manually**
   ```bash
   # Start services
   docker compose up -d

   # Test your changes
   ./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/your-endpoint
   ```

### Submitting Pull Request

1. **Push to your fork**

   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request**
   - Go to GitHub and create a PR from your fork
   - Use a clear, descriptive title
   - Reference related issues with `#issue_number`
   - Fill out the PR template completely

3. **PR Template**
   ```markdown
   ## Description

   Brief description of changes

   ## Type of Change

   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Related Issues

   Fixes #123

   ## Testing

   - [ ] Unit tests added/updated
   - [ ] Integration tests added/updated
   - [ ] Manual testing completed

   ## Checklist

   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] Tests pass locally
   - [ ] No new warnings
   ```

### Review Process

1. **Automated Checks**
   - Tests must pass
   - Code coverage must meet minimum
   - Linting must pass

2. **Code Review**
   - At least one approving review required
   - Address all review comments
   - Make requested changes

3. **Merging**
   - Squash commits if requested
   - Maintainer will merge once approved

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements

### Examples

```bash
# Simple feature
feat(api): add entity relationship endpoint

# Bug fix with issue reference
fix(validation): handle null values in entity attributes

Fixes #123

# Breaking change
feat(auth)!: implement API key authentication

BREAKING CHANGE: All API endpoints now require authentication header
```

### Best Practices

- Use present tense ("add feature" not "added feature")
- Keep subject line under 50 characters
- Capitalize subject line
- No period at end of subject
- Separate subject from body with blank line
- Wrap body at 72 characters
- Explain _what_ and _why_, not _how_

## Documentation

### Code Documentation

**Docstrings** (Google style):

```python
def function_name(param1: str, param2: int = 10) -> bool:
    """Short description of function.

    Longer description if needed, explaining the purpose,
    behavior, and any important details.

    Args:
        param1: Description of first parameter
        param2: Description of second parameter with default

    Returns:
        Description of return value

    Raises:
        ValueError: When and why this is raised
        TypeError: When and why this is raised

    Example:
        >>> result = function_name("test", 20)
        >>> print(result)
        True
    """
    pass
```

### Markdown Documentation

When updating documentation:

1. **Keep it current** - Update docs with code changes
2. **Be clear** - Write for developers unfamiliar with the code
3. **Add examples** - Include code examples where helpful
4. **Link related docs** - Cross-reference related documentation

### Required Documentation Updates

For significant changes, update:

- `README.md` - If user-facing changes
- `API_REFERENCE.md` - If API changes
- `DEVELOPER_GUIDE.md` - If development process changes
- `CHANGELOG.md` - All notable changes
- Inline code comments - For complex logic

## Questions?

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and ideas
- **Developer Guide**: For development details
- **Architecture Doc**: For system design questions

## Recognition

Contributors will be recognized in:

- `CHANGELOG.md` for their contributions
- GitHub contributor list
- Project documentation as appropriate

Thank you for contributing to Luminari Sage!
