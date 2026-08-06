# Luminari Sage - Intelligent Lore Management System

**Version**: 0.7.9
**Status**: Production Deployed
**Deployment**: luminarimud.com:8003
**Repository**: https://github.com/LuminariMUD/sage

**ORIGINAL AUTHOR**: Jamie McLaughlin - This is a fork
of his private project published with his permission.

---

## Vision

Luminari Sage transforms the vast lore of LuminariMUD into an intelligent, queryable knowledge system that understands context, relationships, and narrative possibilities. It serves as both a reference tool and a creative assistant for players, dungeon masters, and content creators.

## Why Luminari Sage?

### For Players

- **Instant Lore Access**: Ask questions in natural language and receive comprehensive, contextual answers
- **Story Exploration**: Discover connections between characters, events, and locations
- **Quest Discovery**: Get personalized quest recommendations based on interests

### For Dungeon Masters

- **Campaign Planning**: Generate quests and story arcs grounded in canonical lore
- **Creative Assistance**: Develop new stories while maintaining consistency
- **Narrative Generation**: Create atmospheric prose for game sessions

### For Content Creators

- **Lore Validation**: Ensure new content aligns with established canon
- **Relationship Mapping**: Understand complex interconnections in the world
- **Collaborative Development**: Build on existing lore with AI assistance

---

## Overview

Luminari Sage is a graph-based lore management system with AI-powered search and validation capabilities for the LuminariMUD world. It combines Neo4j's native graph database with PostgreSQL's pgvector extension for embeddings, orchestrated by PydanticAI agents and Graphiti knowledge graph management, to provide hybrid RAG (Retrieval-Augmented Generation) search through an MCP (Model Context Protocol) interface.

### Technical Innovation

**Hybrid Knowledge System** - Uniquely combines:

- **Vector Embeddings**: For semantic similarity search
- **Graph Database**: For relationship traversal and entity connections
- **Knowledge Graphs**: For structured fact extraction and validation

**Intelligent Agent Orchestration** - Multiple specialized AI agents that can:

- Work independently for simple tasks
- Collaborate on complex, multi-step operations
- Pass context between operations for coherent workflows

**Real-time Streaming** - Advanced streaming architecture provides:

- Token-by-token response streaming
- Progress updates for long operations
- Immediate user feedback

---

## Key Features

### ✅ Implemented

- **Graph-First Architecture**: Entities and relationships modeled in Neo4j knowledge graph
- **Hybrid RAG Search**: Combines PostgreSQL pgvector, full-text search, and graph traversal
- **Semantic Chunking**: Intelligent document segmentation with Graphiti integration
- **Entity & Relationship Extraction**: Automatic knowledge graph construction from markdown
- **Lore Validation System**: Comprehensive validation with finding storage and review workflow
- **Correction System**: Batch corrections with rollback capabilities
- **RESTful API**: 35+ endpoints for search, retrieval, validation, and corrections
- **LangChain Agents**: Multi-agent system with ReAct workflow (quest planning, story development)
- **MCP Server**: Model Context Protocol interface for Claude Desktop integration
- **Authentication**: Multi-tier API key system with middleware protection
- **Production Deployment**: Running on luminarimud.com with Docker orchestration

### 🚧 In Progress

- **Advanced Entity Resolution**: Handle aliases, variants, and disambiguation
- **Temporal Modeling**: Track both in-world and real-world timelines
- **Performance Optimization**: Query caching and index tuning

### 📋 Planned

- **Discord Bot**: Interactive queries and notifications
- **Web Interface**: Browser-based lore exploration and management
- **Public API**: Rate-limited public access for community tools

---

## System Components

1. **Neo4j Graph Database**: Native graph storage for entities and relationships
2. **PostgreSQL + pgvector**: Document storage with integrated vector embeddings
3. **PydanticAI**: Type-safe AI agent framework for entity extraction and validation
4. **Graphiti**: Knowledge graph construction and management
5. **Data Pipeline**: ETL for markdown → knowledge graph + vectors
6. **API Server**: REST/GraphQL endpoints for queries
7. **MCP Server**: AI agent interface with specialized tools
8. **Validation Engine**: Lore consistency checker for builders

---

## Documentation

**📚 Complete Documentation**: See [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) for the complete documentation guide.

### Quick Links

**Getting Started:**

- [Quickstart Guide](docs/guides/QUICKSTART.md) - Get up and running in 10 minutes
- [User Guide](docs/guides/USER_GUIDE.md) - Complete user documentation
- [FAQ](docs/guides/FAQ.md) - Frequently asked questions

**Deployment:**

- [Deployment Guide](docs/deployment/DEPLOYMENT_GUIDE.md) - Production deployment
- [WSL2 Ubuntu Deployment](docs/deployment/DEPLOYMENT_WSL2-UBUNTU.md) - WSL2-specific guide

**Technical Reference:**

- [API Reference](docs/reference/API_REFERENCE.md) - Complete API documentation (35+ endpoints)
- [Architecture](docs/reference/ARCHITECTURE.md) - System design and data flow
- [Database Schemas](docs/reference/SCHEMAS.md) - PostgreSQL and Neo4j schemas

**Development:**

- [Developer Guide](docs/development/DEVELOPER_GUIDE.md) - Development environment and patterns
- [Contributing Guide](docs/development/CONTRIBUTING.md) - How to contribute
- [Testing Guide](docs/development/TESTING.md) - Testing patterns and best practices
- [CLAUDE.md](CLAUDE.md) - AI assistant guidance for development

**Systems Deep Dives:**

- [Agent System](docs/systems/AGENT_SYSTEM.md) - LangChain and PydanticAI agents
- [Validation System](docs/systems/VALIDATION_SYSTEM.md) - Lore consistency validation
- [Correction System](docs/systems/CORRECTION_SYSTEM.md) - Automated corrections
- [Pipeline System](docs/systems/PIPELINE_SYSTEM.md) - Data ingestion and processing

**Project Meta:**

- [Changelog](docs/meta/CHANGELOG.md) - Version history
- [TODO List](docs/meta/TODO.md) - Current tasks and roadmap

---

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/LuminariMUD/sage.git
cd sage

# Copy and configure environment
cp .env.example .env
chmod 600 .env
# Edit .env with your OpenAI API key and database passwords

# Start all services (PostgreSQL, Neo4j, API)
docker compose up -d

# Check service health
docker compose logs -f api

# Run semantic data pipeline (inside container)
make semantic-pipeline
# Or run individual steps:
# make load-canon          # Load markdown documents
# make create-episodes     # Create semantic chunks
# make generate-embeddings # Generate vector embeddings
# make sync-to-graphiti    # Build knowledge graph

# Test the API
curl http://localhost:8003/ping
curl http://localhost:8003/api/v1/health
```

See [docs/guides/QUICKSTART.md](docs/guides/QUICKSTART.md) for detailed instructions.

---

## Current Statistics

### Data Scale

- **16 Approved Canon Documents**: Markdown lore in `lore_docs/canon/`
- **93 Draft Documents**: Markdown source material in `lore_docs/drafts/`
- **~10,000 Episodes**: Semantic chunks with embeddings
- **1,000+ Entities**: Characters, locations, factions, items, events
- **5,000+ Relationships**: Graph connections with semantic properties
- **384-dimension Vectors**: Using sentence-transformers/all-MiniLM-L6-v2

### System Capabilities

- **35+ API Endpoints**: Health, search, RAG, validation, corrections, chat
- **6 Validation Types**: Structural, semantic, type-specific, cross-ref, temporal, canonical
- **2 Correction Types**: Deduplication, semantic standardization
- **4 Major Agent Types**: Direct answer, quest planner, story developer, validator
- **3 Authentication Tiers**: Backend API, MCP operations, MCP backend access

### Performance

- **Entity Search**: 100-300ms average
- **Lore Search**: 200-500ms average
- **RAG Query**: 1-3 seconds average
- **Agent Response**: 3-10 seconds (streaming)
- **Pipeline Processing**: 30-60 minutes (initial load)

---

## Implementation Status

### ✅ Phase 1: Foundation (Complete)

- ✅ Development environment setup
- ✅ Database schemas (PostgreSQL + Neo4j)
- ✅ Entity extraction pipeline with Graphiti
- ✅ Docker configuration
- ✅ Semantic chunking with episode system

### ✅ Phase 2: Core Implementation (Complete)

- ✅ FastAPI API with 35+ endpoints
- ✅ Entity and relationship extraction
- ✅ Hybrid RAG (vector + graph + FTS)
- ✅ LangChain agent system with ReAct workflow
- ✅ Validation system with finding management
- ✅ Correction system with batch operations
- ✅ MCP server for Claude Desktop
- ✅ Authentication middleware
- ✅ Conversation storage

### ✅ Phase 3: Testing & Validation (Complete)

- ✅ Unit tests for core components
- ✅ Integration testing suite
- ✅ API integration tests
- ✅ Data-dependent test markers

### ✅ Phase 4: Production Deployment (Complete)

- ✅ Server deployment (luminarimud.com:8003)
- ✅ Docker orchestration with compose
- ✅ Health checks and monitoring
- ✅ API authentication system
- ✅ Database persistence with volumes
- ✅ Data pipeline automation with Makefile

### 🚧 Phase 5: Enhancements (In Progress)

- 📋 Performance optimization (caching, indexes)
- 📋 Discord bot integration
- 📋 Web-based administration interface
- 📋 Public API with rate limiting
- 📋 Advanced analytics and metrics

See [docs/meta/TODO.md](docs/meta/TODO.md) for detailed task tracking.

---

## API Endpoints

The API runs on `http://localhost:8003` by default (production: luminarimud.com:8003).

### Core Services

- Health checks and system status
- Entity search and retrieval
- Lore document search
- Hybrid RAG queries (vector + graph + FTS)

### Validation System

- Content validation
- Relationship validation
- Finding management and review
- Validation history and statistics

### Correction System

- Batch corrections with rollback
- Correction history tracking
- Preview before applying

### AI Agents

- Streaming chat with LangChain ReAct
- Legacy PydanticAI agent support
- Conversation history storage

**Interactive API docs**: http://localhost:8003/docs
**Complete reference**: [docs/reference/API_REFERENCE.md](docs/reference/API_REFERENCE.md)

---

## Data Pipeline

The data pipeline processes markdown lore documents into a queryable knowledge graph:

```bash
# Complete pipeline (recommended)
make semantic-pipeline

# Individual steps (run in order)
make load-canon              # Load canonical lore into PostgreSQL
make create-episodes         # Create semantic chunks (200-500 tokens)
make generate-embeddings     # Generate vector embeddings
make sync-to-graphiti        # Extract entities/relationships to Neo4j

# Monitoring and status
make status                  # System health and statistics
```

**Pipeline Features:**

- Idempotent operations (safe to re-run)
- Processing flags track completion
- Resume capability after interruption
- Resource-intensive (run separately from deployment)

See [docs/systems/PIPELINE_SYSTEM.md](docs/systems/PIPELINE_SYSTEM.md) for detailed documentation.

---

## Testing

```bash
# Run all tests
pytest

# Run unit tests only (fast)
pytest -m unit

# Run integration tests (requires running services)
pytest -m integration

# Run data-dependent tests (requires loaded data)
pytest -m data_dependent

# Run with coverage
pytest --cov=src tests/ --cov-report=html
```

See [docs/development/TESTING.md](docs/development/TESTING.md) for complete testing guide.

---

## Troubleshooting

### Common Issues

**PostgreSQL connection failed**

- Check if PostgreSQL is running: `docker ps`
- Verify credentials in `.env`
- Ensure pgvector extension is installed

**Neo4j connection failed**

- Check Neo4j browser at http://localhost:7474
- Verify Neo4j credentials
- Check if indexes were created

**Entity extraction not working**

- Ensure documents are loaded first: `make load-canon`
- Check logs: `docker compose logs api`
- Verify Graphiti is properly initialized

See [docs/guides/TROUBLESHOOTING.md](docs/guides/TROUBLESHOOTING.md) for comprehensive troubleshooting.

---

## Security

Luminari Sage follows industry best practices for security and credential management.

### Security Posture

The repository received a full credential and runtime hardening review on
2026-07-30. See [SECURITY.md](SECURITY.md) for findings and response guidance.

✅ **Runtime-managed credentials** - Secret values are not tracked in Git
✅ **Automated secret scanning** - Pre-commit and full-history CI scans
✅ **Credential validation** - Missing database credentials are rejected before connecting
✅ **Credential redaction** - Public errors and logs redact credential-shaped values
✅ **Validated dynamic identifiers** - SQL/Cypher identifiers are allowlisted
✅ **Non-root containers** - Docker runs as unprivileged user

### Required Environment Variables

All secrets must be configured in `.env` (never commit this file):

**Required production secrets**:

- `SAGE_API_KEY` - Backend API authentication (64-character hex)
- `POSTGRES_PASSWORD` - PostgreSQL password (16+ characters)
- `NEO4J_PASSWORD` - Neo4j password (16+ characters)
- `OPENAI_API_KEY` - OpenAI API for embeddings/LLM
- `SAGE_MCP_KEY` - MCP operations authentication
- `SAGE_MCP_BACKEND_KEY` - MCP backend access authentication

**Optional secrets**:

- `LANGSMITH_API_KEY` - LangSmith tracing (optional)

### Generate Secure Credentials

```bash
# Generate 64-character hex API key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate 32-character URL-safe token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

⚠️ **NEVER** commit `.env` files, API keys, or passwords to version control.

### Security Features

**Automated Scanning**:

- Pre-commit hooks with Gitleaks (blocks commits with secrets)
- GitHub Actions security workflow (secrets, dependencies, Docker)
- pip-audit for Python dependency vulnerabilities
- Bandit for Python security linting
- Trivy for Docker image scanning

**Access Control**:

- Multi-tier API key authentication (backend, MCP operations, MCP backend)
- Path-based authorization (different endpoints require different keys)
- Configurable auth bypass for local development (`DISABLE_AUTH=true`)

**Data Protection**:

- Query values are parameterized and dynamic identifiers are validated
- Pydantic models validate all API inputs
- Credential-shaped values are redacted from public errors and logs
- Restrictive CORS, host validation, and browser security headers

### Security Audit History

The latest audit was completed on 2026-07-30. The point-in-time findings and
credential-response requirements are documented in [SECURITY.md](SECURITY.md).

### Reporting Security Issues

If you discover a security vulnerability:

- **Email**: security@luminarimud.com
- **Response time**: Within 48 hours
- **Disclosure**: Coordinated disclosure (90-day policy)

**Please do not** publicly disclose vulnerabilities until they have been addressed.

For complete security documentation, see [SECURITY.md](SECURITY.md).

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development environment setup
- Security requirements (REQUIRED)
- Code style guidelines
- Testing requirements
- Pull request process
- Commit message conventions

**Security Note**: All contributors must install pre-commit hooks (`pre-commit install`) before making commits. This ensures automated security scanning and prevents accidental credential commits.

---

## Resources

- **Documentation Hub**: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)
- **LuminariMUD**: https://www.luminarimud.com
- **Issues**: https://github.com/LuminariMUD/sage/issues

---

## License

[License details to be determined]

---

**Last Updated**: 2026-07-30
**Version**: 0.7.9
**Status**: Production Ready
