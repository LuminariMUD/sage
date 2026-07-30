# System Architecture

## Overview

Luminari Sage employs a sophisticated multi-layer architecture combining traditional databases, vector stores, graph databases, and AI agents to create an intelligent knowledge management system.

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Web Chat   │  │   REST API   │  │   MCP Server     │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                      API Gateway Layer                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │          FastAPI with SSE Streaming Support          │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                    Agent Orchestration Layer                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │ Chat Agent   │  │ Story Agent  │  │ Quest Planner  │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │Narrative Gen │  │ Orchestrator │  │  Validator     │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                   Knowledge Retrieval Layer                   │
│  ┌────────────────────────────────────────────────────┐     │
│  │            Hybrid RAG (Vector + Graph)              │     │
│  └────────────────────────────────────────────────────┘     │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                       Data Storage Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  PostgreSQL  │  │    Neo4j     │  │   Embeddings   │    │
│  │  + pgvector  │  │   + APOC     │  │    Storage     │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Data Storage Layer

#### PostgreSQL with pgvector
- **Purpose**: Primary document storage and vector similarity search
- **Components**:
  - `lore_documents`: Source markdown documents
  - `episodes`: Semantic chunks (200-500 tokens)
  - `embeddings`: Vector representations (1536 dimensions)
  - `conversations`: Chat session storage
- **Key Features**:
  - Full-text search with PostgreSQL FTS
  - Vector similarity search with pgvector
  - ACID compliance for data integrity

#### Neo4j Graph Database
- **Purpose**: Entity and relationship storage
- **Components**:
  - Nodes: Characters, locations, events, organizations
  - Edges: Relationships with semantic properties
  - Properties: Metadata and attributes
- **Key Features**:
  - Cypher query language
  - APOC procedures for advanced operations
  - Pattern matching for relationship discovery

#### Graphiti Integration
- **Purpose**: Knowledge graph construction from text
- **Process**:
  1. Episode ingestion
  2. Entity extraction
  3. Relationship inference
  4. Fact extraction
- **Output**: Structured knowledge graph in Neo4j

### 2. Knowledge Retrieval Layer

#### Hybrid RAG System
The Hybrid Retrieval-Augmented Generation system combines multiple retrieval strategies:

```python
class HybridRAG:
    def query(self, text: str) -> Context:
        # 1. Vector search in PostgreSQL
        vector_results = pgvector_search(text, limit=10)
        
        # 2. Full-text search
        text_results = fulltext_search(text, limit=10)
        
        # 3. Reciprocal Rank Fusion
        combined = reciprocal_rank_fusion(vector_results, text_results)
        
        # 4. Graph expansion
        entities = extract_entities(combined)
        graph_context = neo4j_expand(entities, depth=2)
        
        # 5. Combine all context
        return merge_context(combined, graph_context)
```

#### Retrieval Strategies
1. **Vector Search**: Semantic similarity using embeddings
2. **Full-Text Search**: BM25-like scoring for keyword matching
3. **Graph Traversal**: Relationship-based context expansion
4. **Entity Search**: Direct entity lookup in Graphiti

### 3. Agent Orchestration Layer

#### Agent Architecture

##### Base Agent Pattern
```python
class BaseAgent:
    def __init__(self, model="gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model)
        self.tools = self.register_tools()
    
    async def invoke(self, input: Dict) -> Dict:
        # Process input through LLM with tools
        return await self.process(input)
```

##### Specialized Agents

###### Chat Agent (PydanticAI)
- **Model**: GPT-4o
- **Purpose**: Conversational interface
- **Features**:
  - Streaming responses
  - Tool calling (search_lore)
  - Conversation memory
  - Context management

###### Story Development Agent
- **Model**: GPT-4o-mini
- **Purpose**: Create non-canon stories
- **Features**:
  - [STORY] entity marking
  - Story memory persistence
  - Canon reference tracking
  - Creative freedom with boundaries

###### Quest Planner Agent
- **Model**: GPT-4o-mini
- **Purpose**: Structure quest generation
- **Output Schema**:
  ```json
  {
    "title": "Quest Title",
    "objective": "Main goal",
    "premise": "Background",
    "phases": [
      {
        "phase": "Hook",
        "description": "...",
        "key_entities": [],
        "risks": []
      }
    ]
  }
  ```

###### Narrative Generator
- **Model**: GPT-4o-mini
- **Purpose**: Write prose scenes
- **Features**:
  - Outline generation (3-7 beats)
  - 150-220 word scenes
  - Embellishment tracking
  - Canon adherence

###### Agent Orchestrator
- **Model**: GPT-4o-mini (planning)
- **Purpose**: Multi-step operation coordination
- **Process**:
  1. Analyze request
  2. Create execution plan
  3. Execute steps sequentially
  4. Pass context between steps
  5. Assemble combined response

### 4. API Gateway Layer

#### FastAPI Application
- **Endpoints**:
  - `/api/v1/rag/query`: Hybrid RAG queries
  - `/api/v1/chat/message`: Chat initiation
  - `/api/v1/chat/stream/{id}`: SSE streaming
  - `/api/v1/documents`: Document management
  - `/api/v1/episodes`: Episode access
  - `/api/v1/graph`: Graph operations

#### Authentication
Multi-key authentication system:
- `SAGE_API_KEY`: General API access
- `SAGE_MCP_BACKEND_KEY`: Internal MCP operations
- `SAGE_MCP_KEY`: MCP server access

#### Streaming Architecture
Server-Sent Events (SSE) for real-time streaming:
```python
async def stream_response():
    yield {"type": "route", "route": "lore_query"}
    yield {"type": "token", "content": "The"}
    yield {"type": "token", "content": " answer"}
    yield {"type": "final", "answer": "The answer..."}
```

### 5. User Interface Layer

#### Web Chat Interface
- **Technology**: HTML5 + JavaScript
- **Features**:
  - Real-time streaming display
  - Markdown rendering
  - Tool result visualization
  - Session management

#### REST API
- **Documentation**: Auto-generated Swagger/OpenAPI
- **Format**: JSON request/response
- **Standards**: RESTful design principles

#### MCP Server
- **Protocol**: Model Context Protocol
- **Purpose**: IDE integration
- **Features**:
  - Direct tool access
  - Context management
  - Resource handling

## Data Flow

### Query Processing Pipeline

```
User Query
    ↓
Classification (LLM or heuristic)
    ↓
Route Selection
    ├─→ Simple Route (single agent)
    │      ↓
    │   Direct Execution
    │
    └─→ Orchestrated Route (multiple agents)
           ↓
       Plan Generation
           ↓
       Sequential Execution
           ↓
       Context Passing
           ↓
       Response Assembly
```

### Document Processing Pipeline

```
Markdown Documents
    ↓
Document Ingestion
    ↓
Semantic Chunking (200-500 tokens)
    ↓
Embedding Generation (OpenAI)
    ↓
Vector Storage (pgvector)
    ↓
Graphiti Processing
    ↓
Entity/Relationship Extraction
    ↓
Neo4j Graph Storage
```

## Performance Optimizations

### Caching Strategy
- **Embedding Cache**: 15-minute TTL for repeated queries
- **Query Cache**: Result caching for common questions
- **Graph Cache**: Cached entity relationships

### Connection Pooling
- **PostgreSQL**: asyncpg connection pool (min=5, max=20)
- **Neo4j**: Driver connection pool (max=50)
- **HTTP**: aiohttp session reuse

### Chunking Strategy
- **Dynamic Sizing**: 200-500 tokens based on content
- **Overlap**: 25% overlap for context preservation
- **Boundaries**: Sentence-level splitting

### Indexing
- **PostgreSQL**:
  - B-tree indexes on IDs
  - GIN indexes for full-text search
  - IVFFlat indexes for vector search
- **Neo4j**:
  - Node label indexes
  - Property indexes on name, type
  - Full-text indexes for search

## Scalability Considerations

### Horizontal Scaling
- **API Layer**: Multiple FastAPI instances behind load balancer
- **Database**: Read replicas for PostgreSQL
- **Cache Layer**: Redis for distributed caching (future)

### Vertical Scaling
- **Vector Operations**: GPU acceleration possible
- **Graph Operations**: Memory-optimized Neo4j configuration
- **Concurrent Requests**: Async/await throughout

### Resource Requirements
- **Minimum**: 8GB RAM, 4 CPU cores, 20GB storage
- **Recommended**: 16GB RAM, 8 CPU cores, 50GB SSD
- **Production**: 32GB RAM, 16 CPU cores, 100GB NVMe SSD

## Security Architecture

### Authentication Layers
1. **API Key Validation**: Middleware-based checking
2. **Rate Limiting**: Per-key quotas (future)
3. **CORS Configuration**: Controlled origins

### Data Protection
- **Encryption in Transit**: HTTPS/TLS
- **Encryption at Rest**: Database encryption
- **Sensitive Data**: Environment variable storage

### Audit Trail
- **Request Logging**: All API calls logged
- **Change Tracking**: Document modifications tracked
- **Error Logging**: Comprehensive error capture

## Monitoring & Observability

### Metrics
- **API Metrics**: Request count, latency, errors
- **Database Metrics**: Query performance, connection pool
- **AI Metrics**: Token usage, model performance

### Logging
- **Application Logs**: Structured JSON logging
- **Error Tracking**: Exception capture with context
- **Debug Mode**: Verbose logging for development

### Health Checks
- **Database Connectivity**: PostgreSQL and Neo4j
- **API Health**: Endpoint availability
- **Model Access**: OpenAI API status

## Future Architecture Enhancements

### Planned Improvements
1. **Multi-Modal Support**: Image and map processing
2. **Distributed Processing**: Celery task queue
3. **Advanced Caching**: Redis integration
4. **Federation**: Multi-instance coordination
5. **Plugin System**: Dynamic agent loading

### Experimental Features
- **Local LLMs**: Ollama integration for privacy
- **Vector Database**: Dedicated vector store (Qdrant/Weaviate)
- **Stream Processing**: Apache Kafka for events
- **GraphQL API**: Alternative query interface

---

*For implementation details, see the [Developer Guide](./DEVELOPER_GUIDE.md).*
*For deployment instructions, see the [Deployment Guide](./DEPLOYMENT_GUIDE.md).*