# Contributing to Luminari Sage

Thank you for your interest in contributing to Luminari Sage! This document provides guidelines and best practices for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Security Requirements](#security-requirements)
- [Code Standards](#code-standards)
- [Pull Request Process](#pull-request-process)
- [Testing Requirements](#testing-requirements)
- [Documentation](#documentation)

## Getting Started

### Prerequisites

- **Python 3.11+** - Core language (containers and CI run 3.13)
- **Docker & Docker Compose** - Container orchestration
- **Git** - Version control
- **Pre-commit** - Git hooks (installed automatically)

### First-Time Setup

1. **Fork and clone the repository**:

   ```bash
   git clone https://github.com/YOUR_USERNAME/sage.git
   cd sage
   ```

2. **Install pre-commit hooks** (REQUIRED):

   ```bash
   pip install pre-commit
   pre-commit install
   ```

   This installs automatic security scanning before each commit.

3. **Create environment file**:

   ```bash
   cp .env.example .env
   # Edit .env and set secure passwords (see SECURITY.md)
   ```

4. **Start development environment**:
   ```bash
   docker compose up -d
   ```

## Development Setup

### Environment Configuration

**NEVER commit real credentials**. All secrets must be in `.env` (git-ignored).

Required environment variables (see `.env.example`):

- `POSTGRES_PASSWORD` - PostgreSQL password (16+ characters)
- `NEO4J_PASSWORD` - Neo4j password (16+ characters)
- `SAGE_API_KEY` - Backend API key (64-character hex)
- `OPENAI_API_KEY` - OpenAI API key (if using OpenAI embeddings)

Generate secure credentials:

```bash
# Generate 64-character hex API key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate secure password
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Development Workflow

1. Create a feature branch:

   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Make changes and test locally
3. Run security checks before committing:

   ```bash
   # Pre-commit hooks run automatically, but you can run manually:
   pre-commit run --all-files

   # Check for vulnerabilities
   pip-audit -r requirements.txt

   # Lint for security issues
   bandit -r src/
   ```

4. Commit with conventional commit messages:
   ```bash
   git commit -m "feat: add new lore search endpoint"
   ```

### Branch Naming Convention

- `feat/feature-name` - New features
- `fix/bug-description` - Bug fixes
- `docs/documentation-update` - Documentation changes
- `refactor/code-improvement` - Code refactoring
- `test/test-addition` - Test additions or improvements

## Security Requirements

**All pull requests must meet these security requirements:**

### Pre-Commit Checks

- [ ] **Pre-commit hooks installed and passing**
  - Gitleaks secret scanning
  - Python code formatting (Black, isort)
  - YAML validation
  - Large file detection
  - Private key detection

### Code Security

- [ ] **No hardcoded credentials**
  - No API keys, passwords, tokens in code
  - All secrets loaded from environment variables via `os.getenv()`
  - No default/fallback credentials (use fail-fast validation)
- [ ] **Parameterized queries**
  - Database queries use parameterization: `execute_query(query, {"param": value})`
  - Never use f-strings or concatenation for queries
  - Prevents SQL/Cypher injection
- [ ] **Input validation**
  - Use Pydantic models for all API inputs
  - Validate file paths, user inputs, external data
  - Sanitize data before database insertion
- [ ] **No sensitive data in logs**
  - Never log API keys, passwords, tokens
  - Use `bool(api_key)` instead of actual value
  - Redact sensitive fields in error messages

### Dependency Security

- [ ] **No vulnerable dependencies**
  - Run `pip-audit -r requirements.txt` before PR
  - Update or justify any vulnerabilities found
  - Pin dependency versions to avoid supply chain attacks

### Docker Security

- [ ] **Non-root containers** (already configured)
- [ ] **No secrets in Dockerfiles**
- [ ] **Resource limits defined**

### Documentation Security

- [ ] **No credentials in examples**
  - Use placeholders: `<YOUR_API_KEY_HERE>`, `PLACEHOLDER_PASSWORD`
  - Mark test credentials clearly: `test_dummy_key_12345`
- [ ] **Security impact assessed**
  - Document any security implications of changes
  - Update SECURITY.md if adding new secrets/features

## Code Standards

### Python Style

- **Formatting**: Use `black` (enforced by pre-commit)
- **Import sorting**: Use `isort` with black profile (enforced by pre-commit)
- **Linting**: Follow `flake8` rules (max line length: 100)
- **Type hints**: Required for all function signatures
  ```python
  def search_lore(query: str, limit: int = 10) -> List[Dict[str, Any]]:
      ...
  ```

### Code Organization

- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes
- **Docstrings**: Google style with Args, Returns, Raises sections
  ```python
  def process_document(doc_path: str, chunk_size: int) -> List[Episode]:
      """Process a lore document into semantic chunks.

      Args:
          doc_path: Path to markdown document
          chunk_size: Maximum tokens per chunk

      Returns:
          List of Episode objects with embeddings

      Raises:
          FileNotFoundError: If doc_path doesn't exist
          ValueError: If chunk_size < 100
      """
  ```

### FastAPI Patterns

- Use `async`/`await` for all endpoints
- Never manually close database connections (managed globally)
- Use dependency injection for auth and database connections
- Return Pydantic models for automatic validation

### Database Queries

**ALWAYS use parameterized queries**:

```python
# GOOD - Parameterized
await db.fetch("SELECT * FROM table WHERE id = $1", user_id)

# BAD - SQL injection risk
await db.fetch(f"SELECT * FROM table WHERE id = {user_id}")
```

### Git Workflow

- **Commit messages**: Use conventional commits
  - `feat:` - New feature
  - `fix:` - Bug fix
  - `docs:` - Documentation changes
  - `refactor:` - Code refactoring
  - `test:` - Test additions
  - `chore:` - Build/tooling updates
- **Never commit**:
  - `.env` files (only `.env.example` allowed)
  - Credentials, API keys, passwords
  - Large binary files (>1MB)
  - Personal configuration files

## Pull Request Process

### Before Submitting

1. **Update from main**:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Run full test suite**:

   ```bash
   pytest
   ```

3. **Run security checks**:

   ```bash
   pre-commit run --all-files
   pip-audit -r requirements.txt
   bandit -r src/
   ```

4. **Update documentation** if needed

### PR Checklist

- [ ] **Code compiles and runs** without errors
- [ ] **All tests pass** (`pytest`)
- [ ] **Pre-commit hooks pass** (Gitleaks, formatters, linters)
- [ ] **No security vulnerabilities** (pip-audit, Bandit clean)
- [ ] **Code follows style guide** (Black, isort, flake8)
- [ ] **Type hints added** for new functions
- [ ] **Docstrings added** for public APIs
- [ ] **Tests added** for new features
- [ ] **Documentation updated** (README, CLAUDE.md, comments)
- [ ] **Security reviewed** (see Security Requirements above)
- [ ] **Commits are clean** (squash if messy)
- [ ] **Branch is up-to-date** with main

### PR Description Template

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] Documentation update
- [ ] Security fix

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Security Impact

- [ ] No new secrets or credentials added
- [ ] All secrets loaded from environment variables
- [ ] Pre-commit hooks passing
- [ ] No vulnerable dependencies (pip-audit clean)
- [ ] Parameterized queries used for database access

## Checklist

- [ ] Code follows project style guide
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] Tests pass locally
- [ ] No merge conflicts
```

### Review Process

1. **Automated checks** must pass:
   - GitHub Actions security scan
   - Gitleaks secret detection
   - Dependency vulnerability scan
   - Code quality checks
2. **Code review** by maintainer
3. **Security review** if changes affect authentication, database, or credentials
4. **Approval and merge** by project maintainer

## Testing Requirements

### Test Coverage

- **Minimum coverage**: 80% for new code
- **Test types**:
  - Unit tests: Fast, isolated logic tests
  - Integration tests: Database, API, agent tests
  - Data-dependent tests: Tests requiring loaded lore data

### Running Tests

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

### Writing Tests

- Mark tests appropriately:
  ```python
  @pytest.mark.unit
  def test_parse_markdown():
      ...
  @pytest.mark.integration
  async def test_neo4j_connection():
      ...
  ```
- Use fixtures for common setup
- Mock external services (OpenAI, Neo4j) in unit tests
- Never use real credentials in tests (use obvious dummy values)

## Documentation

### Required Documentation

- **Code comments**: For complex logic, algorithms, security-sensitive code
- **Docstrings**: For all public functions, classes, modules
- **README.md**: Update if adding user-facing features
- **CLAUDE.md**: Update if changing architecture or dev workflow
- **SECURITY.md**: Update if adding new secrets or security features

### Documentation Style

- Use **Markdown** for all documentation files
- Include **code examples** with expected output
- Keep documentation **up-to-date** with code changes
- Use **diagrams** for complex workflows (Mermaid preferred)

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security**: Email security@luminarimud.com (see SECURITY.md)
- **Documentation**: Check README.md and CLAUDE.md first

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Assume good intentions
- Follow the security guidelines (no credential sharing in issues/PRs)

## License

By contributing, you agree that your contributions will be licensed under the project's license.

---

**Thank you for contributing to Luminari Sage!**

For security-specific guidelines, see [SECURITY.md](SECURITY.md).
