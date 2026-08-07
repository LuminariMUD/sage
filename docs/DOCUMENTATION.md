# Luminari Sage - Complete Documentation Guide

**Version**: 0.7.14
**Status**: Production Ready
**Last Updated**: 2025-11-12

This is the complete documentation guide for Luminari Sage - an intelligent lore management system combining graph databases, vector embeddings, and AI agents for the LuminariMUD world.

---

## Table of Contents

### [Part I: Project Overview](#part-i-project-overview)

- [System Overview](#system-overview)
- [Key Features](#key-features)
- [System Components](#system-components)
- [Implementation Status](#implementation-status)
- [Quick Start](#quick-start)

### [Part II: Documentation Navigation](#part-ii-documentation-navigation)

- [Documentation Structure](#documentation-structure)
- [Finding Information](#finding-information)
- [Documentation by Role](#documentation-by-role)
- [Quick Reference](#quick-reference)

### [Part III: Documentation Standards](#part-iii-documentation-standards)

- [Document Structure](#document-structure-standards)
- [Formatting Standards](#formatting-standards)
- [Content Guidelines](#content-guidelines)
- [Maintenance Procedures](#maintenance-procedures)

---

# Part I: Project Overview

## System Overview

**Current Status**: Production Deployed (v0.7.0)
**Deployment**: luminarimud.com:8003
**Repository**: https://github.com/LuminariMUD/sage

Luminari Sage is a graph-based lore management system with AI-powered search and validation capabilities. It combines Neo4j's native graph database with PostgreSQL's pgvector extension for embeddings, orchestrated by PydanticAI agents and Graphiti knowledge graph management, to provide hybrid RAG (Retrieval-Augmented Generation) search through an MCP (Model Context Protocol) interface.

### Project Goals

1. **Structured Knowledge Base**: Transform markdown lore documents into a queryable graph database
2. **Intelligent Search**: Enable semantic search across all lore with entity awareness
3. **Lore Validation**: Analyze zone files and story ideas for lore consistency
4. **Builder Support**: Provide AI agents that can answer lore questions with high confidence
5. **Maintainability**: Support versioning, provenance tracking, and canonical status

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

### Data Flow Architecture

```
┌─────────────────┐
│ Markdown Files  │  (83 docs in lore_docs/)
│   .md files     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ load_documents  │  Step 1: Load into PostgreSQL
│                 │  → lore_documents table
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│create_episodes  │  Step 2: Semantic chunking
│                 │  → episodes table (200-500 tokens)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│gen_embeddings   │  Step 3: Vector embeddings
│                 │  → episode.embedding (384-dim)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│sync_to_graphiti │  Step 4: Knowledge graph extraction
│                 │  → Neo4j (entities + relationships)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   Hybrid RAG Query System           │
│  ┌─────────────────────────────┐   │
│  │ PostgreSQL (pgvector)       │   │
│  │ • Vector similarity search  │   │
│  │ • Full-text search (FTS)    │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ Neo4j Graph                 │   │
│  │ • Entity relationships      │   │
│  │ • Graph traversal           │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ Reciprocal Rank Fusion      │   │
│  │ • Combines all results      │   │
│  │ • Relevance scoring         │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  AI Agents      │  • Direct Answer
│  LLM + Context  │  • Quest Planner
│                 │  • Story Developer
└─────────────────┘  • Validator
```

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

### Test with Authentication

```bash
# Search entities
./scripts/curl_with_sage_key.sh \
  "http://localhost:8003/api/v1/entities/search?query=crystal+dwarves"

# RAG query
./scripts/curl_with_sage_key.sh \
  -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Who are the crystal dwarves?", "limit": 5}'
```

### Current Lore Statistics

- **Documents**: 83 markdown files across 11 thematic directories
- **Estimated Entities**: 500-1000 (deities, locations, factions, etc.)
- **Estimated Chunks**: 5000-10000 text segments
- **Core Relationships**: ~20 relation types
- **Source Files**: Mix of converted Office documents and original markdown

---

# Part II: Documentation Navigation

## Documentation Structure

```
docs/
├── DOCUMENTATION.md                 # This file - Complete guide
├── CRUSH.md                         # Quick reference card
│
├── guides/                          # 📘 User-Facing Guides
│   ├── QUICKSTART.md               # ⚡ 10-minute setup guide
│   ├── USER_GUIDE.md               # 📖 Complete user documentation
│   ├── DEPLOYMENT_GUIDE.md         # 🚀 Production deployment
│   ├── TROUBLESHOOTING.md          # 🔧 Common issues & solutions
│   ├── FAQ.md                      # ❓ Frequently asked questions
│   └── README-MCP.md               # 🔌 Claude Desktop integration
│
├── deployment/                      # 🚀 Deployment Documentation
│   ├── DEPLOYMENT_GUIDE.md         # General deployment concepts
│   └── DEPLOYMENT_WSL2-UBUNTU.md   # WSL2 Ubuntu specific guide
│
├── reference/                       # 📚 Technical Reference
│   ├── API_REFERENCE.md            # 🔗 35+ API endpoints (924 lines)
│   ├── ARCHITECTURE.md             # 🏗️ System design (380 lines)
│   ├── SCHEMAS.md                  # 🗄️ Database schemas
│   └── DEPLOYMENT_CONFIG.md        # ⚙️ Configuration reference
│
├── development/                     # 💻 Developer Documentation
│   ├── DEVELOPER_GUIDE.md          # 🛠️ Development environment
│   ├── CONTRIBUTING.md             # 🤝 Contribution guidelines
│   └── TESTING.md                  # 🧪 Testing guide
│
├── systems/                         # 🧩 System-Specific Documentation
│   ├── AGENT_SYSTEM.md             # 🤖 AI agents (913 lines)
│   ├── VALIDATION_SYSTEM.md        # ✅ Validation (1,040 lines)
│   ├── CORRECTION_SYSTEM.md        # 🔄 Corrections (920 lines)
│   ├── VALIDATION_AGENT_GUIDE.md   # 📋 Practical validation guide
│   └── PIPELINE_SYSTEM.md          # 🔁 Data pipeline
│
├── demos/                           # 🎯 Demos and Examples
│   ├── GraphRAG_Demo_Guide.md      # Hybrid RAG demonstration
│   ├── Postman_Collections_Guide.md # API testing guide
│   └── *.postman_collection.json   # Pre-configured collections
│
└── meta/                            # 📊 Project Meta
    ├── CHANGELOG.md                # 📝 Version history
    ├── TODO.md                     # ✓ Task tracking
    └── DOCUMENTATION_AUDIT.md      # 🔍 Quality tracking

Total: 35+ documentation files, ~15,000+ lines
```

---

## Finding Information

### Quick Navigation

**I want to...**

- **Get started quickly** → [guides/QUICKSTART.md](guides/QUICKSTART.md)
- **Use the API** → [reference/API_REFERENCE.md](reference/API_REFERENCE.md)
- **Understand the system** → [reference/ARCHITECTURE.md](reference/ARCHITECTURE.md)
- **Develop or contribute** → [development/DEVELOPER_GUIDE.md](development/DEVELOPER_GUIDE.md)
- **Learn about specific systems** → [systems/](systems/)
- **See examples and demos** → [demos/](demos/)
- **Deploy to production** → [deployment/DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)
- **Deploy on WSL2 Ubuntu** → [deployment/DEPLOYMENT_WSL2-UBUNTU.md](deployment/DEPLOYMENT_WSL2-UBUNTU.md)
- **Track project status** → [meta/TODO.md](meta/TODO.md)

### Search Strategies

**By Topic**:

- Authentication → API_REFERENCE.md, DEVELOPER_GUIDE.md
- Database schemas → SCHEMAS.md
- Deployment → DEPLOYMENT_GUIDE.md, DEPLOYMENT_CONFIG.md
- Testing → TESTING.md
- Validation → VALIDATION_SYSTEM.md, VALIDATION_AGENT_GUIDE.md
- Agents → AGENT_SYSTEM.md
- Pipeline → PIPELINE_SYSTEM.md

**By Task**:

- "How do I..." → USER_GUIDE.md, DEVELOPER_GUIDE.md
- "What is..." → ARCHITECTURE.md, SCHEMAS.md
- "API endpoint for..." → API_REFERENCE.md
- "Deploy to..." → DEPLOYMENT_GUIDE.md, DEPLOYMENT_WSL2-UBUNTU.md
- "Test..." → TESTING.md

---

## Documentation by Role

### I'm a Content Creator

**Goal**: Use Luminari Sage to search lore and validate content

**Recommended Path**:

1. Start: [guides/QUICKSTART.md](guides/QUICKSTART.md)
2. Learn: [guides/USER_GUIDE.md](guides/USER_GUIDE.md)
3. Integrate: [guides/README-MCP.md](guides/README-MCP.md)

### I'm a Game Developer

**Goal**: Integrate Luminari Sage API into game systems

**Recommended Path**:

1. Start: [reference/API_REFERENCE.md](reference/API_REFERENCE.md)
2. Understand: [reference/ARCHITECTURE.md](reference/ARCHITECTURE.md)
3. Examples: [demos/](demos/)

### I'm a System Administrator

**Goal**: Deploy and maintain Luminari Sage

**Recommended Path**:

1. Start: [deployment/DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)
2. WSL2 Ubuntu: [deployment/DEPLOYMENT_WSL2-UBUNTU.md](deployment/DEPLOYMENT_WSL2-UBUNTU.md)
3. Reference: [reference/DEPLOYMENT_CONFIG.md](reference/DEPLOYMENT_CONFIG.md)
4. Schemas: [reference/SCHEMAS.md](reference/SCHEMAS.md)

### I'm a Contributor

**Goal**: Add features or fix bugs

**Recommended Path**:

1. Start: [development/DEVELOPER_GUIDE.md](development/DEVELOPER_GUIDE.md)
2. Guidelines: [development/CONTRIBUTING.md](development/CONTRIBUTING.md)
3. Testing: [development/TESTING.md](development/TESTING.md)
4. AI Help: `CLAUDE.md` (project root)

### I'm a Technical Leader

**Goal**: Understand architecture and make decisions

**Recommended Path**:

1. Overview: [Project README](../README.md) - Vision and business value
2. Architecture: [reference/ARCHITECTURE.md](reference/ARCHITECTURE.md)
3. Systems: [systems/](systems/)
4. Status: [meta/TODO.md](meta/TODO.md)

---

## Quick Reference

### Essential Documents

| Document                                                                     | Description                | Lines  |
| ---------------------------------------------------------------------------- | -------------------------- | ------ |
| [guides/QUICKSTART.md](guides/QUICKSTART.md)                                 | 10-minute setup guide      | ~200   |
| [guides/USER_GUIDE.md](guides/USER_GUIDE.md)                                 | Complete user guide        | ~500   |
| [deployment/DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)             | Production deployment      | ~800   |
| [deployment/DEPLOYMENT_WSL2-UBUNTU.md](deployment/DEPLOYMENT_WSL2-UBUNTU.md) | WSL2 Ubuntu deployment     | ~2,573 |
| [reference/API_REFERENCE.md](reference/API_REFERENCE.md)                     | Complete API documentation | 924    |
| [reference/ARCHITECTURE.md](reference/ARCHITECTURE.md)                       | System architecture        | 380    |
| [systems/AGENT_SYSTEM.md](systems/AGENT_SYSTEM.md)                           | AI agent architecture      | 913    |
| [systems/VALIDATION_SYSTEM.md](systems/VALIDATION_SYSTEM.md)                 | Validation system          | 1,040  |
| [systems/CORRECTION_SYSTEM.md](systems/CORRECTION_SYSTEM.md)                 | Correction system          | 920    |

### Visual Documentation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    📚 DOCUMENTATION HUB                     │
│                    docs/DOCUMENTATION.md                    │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
         ┌──────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
         │  New User  │ │Developer│ │  Operator  │
         └──────┬─────┘ └────┬────┘ └─────┬──────┘
                │            │             │
         ┌──────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
         │ QUICKSTART │ │DEVELOPER│ │DEPLOYMENT  │
         │            │ │  GUIDE  │ │   GUIDE    │
         └──────┬─────┘ └────┬────┘ └─────┬──────┘
                │            │             │
         ┌──────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
         │ USER GUIDE │ │   API   │ │   CONFIG   │
         │            │ │REFERENCE│ │            │
         └──────┬─────┘ └────┬────┘ └─────┬──────┘
                │            │             │
         ┌──────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
         │    FAQ     │ │ SYSTEMS │ │TROUBLESHOOT│
         └────────────┘ └─────────┘ └────────────┘
```

---

# Part III: Documentation Standards

## Document Structure Standards

### Required Header

All documentation files must include a header with:

```markdown
# Document Title

**Version**: 0.7.14
**Status**: Production Ready / In Development / Draft
**Last Updated**: YYYY-MM-DD

Brief description of the document's purpose (1-2 sentences).
```

**Example:**

```markdown
# API Reference

**Version**: 0.7.14
**Status**: Production Ready
**Last Updated**: 2025-11-12

Complete reference for all Luminari Sage API endpoints with request/response examples.
```

### Table of Contents

Documents longer than 200 lines should include a table of contents:

```markdown
## Table of Contents

- [Section 1](#section-1)
- [Section 2](#section-2)
  - [Subsection 2.1](#subsection-21)
```

### Section Organization

Follow this order:

1. **Header** (title, version, status, date, description)
2. **Table of Contents** (if needed)
3. **Overview** (what this is about)
4. **Main Content** (organized by topic)
5. **Related Documentation** (links to other docs)
6. **Footer** (optional: last updated, version)

---

## Formatting Standards

### Headings

Use ATX-style headings with proper hierarchy:

```markdown
# H1: Document Title (only one per document)

## H2: Major Sections

### H3: Subsections

#### H4: Minor Subsections
```

**Rules:**

- Only ONE H1 per document (the title)
- Don't skip heading levels (H2 → H4)
- Use sentence case: "Getting started" not "Getting Started"
- No periods at end of headings

### Text Formatting

**Bold** for emphasis:

```markdown
**Important**: This is critical information
```

_Italic_ for slight emphasis or terms:

```markdown
This is called _semantic chunking_
```

`Code` for inline code, commands, or technical terms:

```markdown
Run `make semantic-pipeline` to start
The `episodes` table stores chunks
```

### Lists

**Unordered lists:**

```markdown
- First item
- Second item
  - Nested item (2 spaces)
- Third item
```

**Ordered lists:**

```markdown
1. First step
2. Second step
3. Third step
```

**Task lists (for TODO docs):**

```markdown
- [x] Completed task
- [ ] Pending task
```

### Links

**Internal links** (relative paths):

```markdown
See [API Reference](../reference/API_REFERENCE.md)
See [Quickstart](QUICKSTART.md) # Same directory
```

**External links:**

```markdown
Visit [OpenAI](https://openai.com) for API keys
```

**Link to sections:**

```markdown
See [Installation](#installation) below
```

### Code Blocks

Always specify the language:

````markdown
```bash
docker compose up -d
```

```python
from src.db import get_postgres_db
```

```json
{
  "query": "test",
  "limit": 5
}
```
````

**Multi-line commands:**

```bash
# Use backslashes for readability
docker exec -it luminari-api \
  python src/scripts/load_documents.py \
  --verbose
```

### Tables

Use tables for structured comparisons:

```markdown
| Feature | Status      | Notes          |
| ------- | ----------- | -------------- |
| API     | ✅ Complete | 35+ endpoints  |
| MCP     | ✅ Complete | Claude Desktop |
```

**Alignment:**

- Left-align text columns: `|---------|`
- Right-align numbers: `|---------:|`
- Center-align: `|:-------:|`

### Status Indicators

Use consistent status markers:

- ✅ Complete / Resolved / Yes
- ❌ Not Available / No
- 🚧 In Progress / Partial
- 📋 Planned / To Do
- ⚠️ Warning / Caution
- ℹ️ Info / Note

---

## Content Guidelines

### Writing Style

**Clarity:**

- Write in clear, simple sentences
- Avoid jargon unless defined
- Use active voice: "Run the command" not "The command should be run"
- Be specific: "Port 8003" not "the default port"

**Consistency:**

- Use same terms throughout (e.g., "endpoint" not sometimes "route")
- Consistent capitalization (e.g., "PostgreSQL" not "Postgresql")
- Consistent command format (e.g., always `docker compose` not `docker-compose`)

**Audience:**

- Assume reader has basic technical knowledge
- Explain complex concepts with examples
- Link to detailed docs for advanced topics

### Version Information

**Always include version context:**

```markdown
**Current Version**: 0.7.0
**Introduced in**: v0.3.0
**Deprecated in**: v0.5.0 (if applicable)
```

### Dates

Use ISO format: `YYYY-MM-DD`

```markdown
**Last Updated**: 2025-11-12
```

### Commands

**Format commands consistently:**

```bash
# Good: With context and output
docker compose ps
# Expected output: Shows running containers

# Bad: No context
docker compose ps
```

**Explain what commands do:**

```bash
# Check if PostgreSQL is running
docker ps | grep postgres
```

### Examples

**Provide realistic examples:**

```bash
# Good: Realistic query
curl "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves"

# Bad: Abstract placeholder
curl "http://localhost:8003/api/v1/lore/search?query=YOUR_QUERY"
```

**Include expected output:**

```bash
curl http://localhost:8003/ping
# Output: {"message": "pong"}
```

### Error Messages

When documenting errors, include:

1. **Symptom**: What the user sees
2. **Cause**: Why it happens
3. **Solution**: How to fix it

````markdown
**Symptom:**

- `Connection refused` errors

**Cause:**

- PostgreSQL service not running

**Solution:**

```bash
docker compose up -d postgres
```
````

````

---

## Maintenance Procedures

### Regular Updates

**Quarterly (every 3 months):**
1. Review all documentation for accuracy
2. Update version numbers if needed
3. Check all links work
4. Verify commands and examples
5. Update metrics and statistics

**On each release:**
1. Update version in all document headers
2. Update CHANGELOG.md
3. Review API_REFERENCE.md for new endpoints
4. Update feature status (planned → complete)
5. Update dates in recently changed docs

**As needed:**
1. Fix errors immediately when found
2. Update when implementation changes
3. Add FAQ entries for common questions
4. Improve unclear sections based on feedback

### Version Updates

When incrementing version (e.g., 0.7.0 -> 0.7.1), substitute the old and new
version numbers into the commands below:

1. **Update all headers:**
   ```bash
   OLD=0.7.0
   NEW=0.7.1

   # Find files carrying the old version stamp
   grep -rn "^\*\*Version\*\*: $OLD" docs/ README.md

   # Update the stamps (docs/archive/ holds historical snapshots -- leave those)
   grep -rl "^\*\*Version\*\*: $OLD" docs/ README.md \
     | grep -v '^docs/archive/' \
     | xargs sed -i "s/^\*\*Version\*\*: $OLD/**Version**: $NEW/"
````

Also check for stale "Current Version" / "Current Status (vX.Y.Z)" claims, which
are not caught by the stamp pattern above.

2. **Update dates:**

   ```bash
   # Update "Last Updated" to current date
   # Do this manually to ensure accuracy
   ```

3. **Update CHANGELOG.md:**
   - Add new version section
   - List major changes

4. **Update this file:**
   - Update status if needed
   - Update feature list if new features added

### Link Checking

**Manual check:**

```bash
# Test internal links
for file in docs/**/*.md; do
  echo "Checking $file"
  grep -o '\[.*\](.*\.md)' "$file"
done
```

**Automated tools:**

```bash
# Use markdown-link-check (if available)
markdown-link-check docs/**/*.md
```

### Code Example Validation

**Test all code examples regularly:**

1. **Bash commands**: Run them in a test environment
2. **API calls**: Test against running API
3. **Python code**: Run through interpreter
4. **JSON**: Validate with `jq` or JSON validator

```bash
# Example: Test API endpoint
curl -f http://localhost:8003/api/v1/health || echo "FAIL: Health check"
```

---

## Documentation Quality

### Self-Review Checklist

Before committing documentation changes:

- [ ] Header includes version, status, date, description
- [ ] Table of contents (if >200 lines)
- [ ] Consistent formatting (headings, lists, code blocks)
- [ ] All code examples tested
- [ ] All links work (internal and external)
- [ ] No sensitive information (API keys, passwords)
- [ ] Proper spelling and grammar
- [ ] Related docs updated if needed
- [ ] Cross-references added where helpful

### Peer Review

For major documentation changes:

1. **Create PR** with documentation changes
2. **Reviewer checks:**
   - Accuracy (matches implementation)
   - Clarity (understandable by target audience)
   - Completeness (all necessary info included)
   - Consistency (follows standards)
3. **Address feedback** and update
4. **Merge** when approved

### Quality Metrics

Track these metrics over time:

**Coverage:**

- % of API endpoints documented
- % of features documented
- % of common errors in troubleshooting

**Quality:**

- Number of broken links
- Number of outdated examples
- User feedback/questions

**Freshness:**

- Days since last update
- % of docs updated in last quarter

---

## Common Documentation Patterns

### API Endpoint Documentation

````markdown
### GET /api/v1/example

**Description:** What this endpoint does

**Parameters:**

- `param1` (string, required): Description
- `param2` (integer, optional): Description (default: 10)

**Request Example:**

```bash
curl "http://localhost:8003/api/v1/example?param1=value"
```
````

**Response:**

```json
{
  "result": "data",
  "count": 5
}
```

**Status Codes:**

- 200: Success
- 400: Bad request
- 404: Not found

````

### Configuration Option Documentation

```markdown
### OPTION_NAME

**Type:** string / integer / boolean
**Required:** yes / no
**Default:** value
**Description:** What this option does

**Example:**
```bash
OPTION_NAME=value
````

**Notes:**

- Additional important information

````

### Troubleshooting Entry

```markdown
### Issue Name

**Symptoms:**
- What the user sees
- Error messages

**Cause:**
- Why this happens

**Solution:**
1. Step one
   ```bash
   command here
````

2. Step two
3. Verify fix

```

---

## Document Categories

### guides/
User-facing guides for getting started and deployment
- **Target**: End users, operators
- **Focus**: How to use the system
- **Examples**: QUICKSTART.md, USER_GUIDE.md, DEPLOYMENT_GUIDE.md

### deployment/
Deployment-specific documentation
- **Target**: System administrators, DevOps
- **Focus**: How to deploy and configure
- **Examples**: DEPLOYMENT_GUIDE.md, DEPLOYMENT_WSL2-UBUNTU.md

### reference/
Technical reference documentation
- **Target**: Developers, integrators
- **Focus**: What the system does, API specs
- **Examples**: API_REFERENCE.md, ARCHITECTURE.md, SCHEMAS.md

### development/
Developer documentation
- **Target**: Contributors, developers
- **Focus**: How to develop and contribute
- **Examples**: DEVELOPER_GUIDE.md, CONTRIBUTING.md, TESTING.md

### systems/
System-specific deep dives
- **Target**: Developers working on specific systems
- **Focus**: Detailed system internals
- **Examples**: AGENT_SYSTEM.md, VALIDATION_SYSTEM.md, CORRECTION_SYSTEM.md

### demos/
Demonstrations and examples
- **Target**: New users, evaluators
- **Focus**: Practical examples and demos
- **Examples**: GraphRAG_Demo_Guide.md, Postman collections

### meta/
Project meta-documentation
- **Target**: Project managers, contributors
- **Focus**: Project status, planning, tracking
- **Examples**: CHANGELOG.md, TODO.md, DOCUMENTATION_AUDIT.md

---

## Contributing to Documentation

Found a documentation issue? Want to improve docs?

1. Read [development/CONTRIBUTING.md](development/CONTRIBUTING.md)
2. Follow documentation standards above
3. Update cross-references if adding new documents
4. Submit pull request

**New Document Checklist:**

- [ ] Choose appropriate directory (guides/, reference/, development/, systems/, demos/, meta/)
- [ ] Include required header (version, status, date, description)
- [ ] Add table of contents if >200 lines
- [ ] Use consistent formatting (headings, lists, code blocks)
- [ ] Include practical examples
- [ ] Add cross-references to related docs
- [ ] Test all code examples
- [ ] Check all links
- [ ] Self-review with checklist
- [ ] Request peer review for major docs

---

## Documentation Statistics

### Current Status (v0.7.0)

- **Total Documentation Files**: 35+
- **Total Lines**: ~15,000+
- **Guides**: 6 documents
- **Reference**: 4 documents
- **Development**: 3 documents
- **Systems**: 5 documents
- **Demos**: 3+ documents
- **Meta**: 4 documents

### Coverage

- ✅ All API endpoints documented
- ✅ All major systems documented
- ✅ Validation and correction systems fully documented
- ✅ Testing guide comprehensive
- ✅ User guide covers all use cases
- ✅ Deployment guide production-ready
- ✅ WSL2 deployment guide comprehensive

### Key Documents (by line count)

1. **deployment/DEPLOYMENT_WSL2-UBUNTU.md**: 2,573 lines - WSL2 Ubuntu deployment
2. **systems/VALIDATION_SYSTEM.md**: 1,040 lines - Validation architecture
3. **reference/API_REFERENCE.md**: 924 lines - Complete API documentation
4. **systems/CORRECTION_SYSTEM.md**: 920 lines - Correction system
5. **systems/AGENT_SYSTEM.md**: 913 lines - Complete agent architecture

---

## Getting Help

Can't find what you need?

1. **Use Quick Navigation** - See [Finding Information](#finding-information) above
2. **Search docs** - Use your IDE's search across all markdown files
3. **Check CLAUDE.md** - Root-level file with development guidance
4. **Review Project README** - [../README.md](../README.md) for vision and overview
5. **Check GitHub issues** - Someone may have asked already

---

## Related Documentation

**Key External Files:**
- `CLAUDE.md` (project root) - AI assistant guidance for development
- `README.md` (project root) - Project overview and quick links

**Important Internal Sections:**
- [Part I: Project Overview](#part-i-project-overview) - System overview and features
- [Part II: Documentation Navigation](#part-ii-documentation-navigation) - Find any documentation
- [Part III: Documentation Standards](#part-iii-documentation-standards) - How to write docs

---

## Maintenance

**Review Schedule:**
- Quarterly: Full documentation review
- Per release: Version and feature updates
- As needed: Error fixes and improvements

**Owned by:** Development team
**Last Major Revision:** 2025-11-12 (v0.4.0)
**Next Scheduled Review:** 2025-02-12

---

**Last Updated**: 2025-11-12
**Version**: 0.7.14
**Status**: Production Ready
```
