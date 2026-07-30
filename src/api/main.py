"""Main FastAPI application for Luminari Sage."""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ValidationError

from src.auth import AuthMiddleware
from src.auth.host_validation import get_allowed_hosts
from src.db import close_neo4j_db, close_postgres_db, get_neo4j_db, get_postgres_db
from src.graphiti.edge_types import EDGE_TYPES
from src.graphiti.entity_types import ENTITY_TYPES
from src.llm.context_utils import count_tokens, select_texts_within_budget, truncate_text
from src.llm.embeddings.factory import get_embedder
from src.security import (
    SensitiveDataFormatter,
    install_sensitive_logging,
    public_error_message,
)

load_dotenv()

# Configure logging with fallback for file handler
handlers = [logging.StreamHandler(sys.stdout)]

# Try to add file handler, but don't fail startup if we can't
log_file = os.getenv("LOG_FILE", "/app/logs/startup.log")
try:
    log_path = Path(log_file)
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    log_path.parent.chmod(0o700)
    with log_path.open("a") as f:
        f.write("")  # Test write
    log_path.chmod(0o600)
    handlers.append(logging.FileHandler(log_path))
    print("✅ Secure file logging enabled")
except Exception as e:
    print(f"⚠️ Could not create secure log file ({type(e).__name__})")
    print("📝 Using console-only logging")

log_formatter = SensitiveDataFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
for handler in handlers:
    handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=handlers,
    force=True,
)
install_sensitive_logging()
logger = logging.getLogger(__name__)

# Global embedder instance
embedder = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global embedder

    logger.info("🚀 Starting Luminari Sage API...")

    # Initialize embedder
    try:
        embedder = get_embedder()
        logger.info(f"✅ Embedder loaded: {embedder.__class__.__name__}")
        logger.info(f"   Embedding dimension: {embedder.get_dimension()}")
    except Exception as e:
        logger.error("❌ Failed to load embedder (%s)", type(e).__name__)
        embedder = None

    # Initialize database connections with error handling and timeout
    logger.info("🔌 Initializing database connections...")

    try:
        logger.info("Connecting to PostgreSQL...")
        await asyncio.wait_for(get_postgres_db(), timeout=30)
        logger.info("✅ PostgreSQL connected")
    except TimeoutError:
        logger.error("❌ PostgreSQL connection timed out")
    except Exception as e:
        logger.error("❌ PostgreSQL connection failed (%s)", type(e).__name__)

    try:
        logger.info("Connecting to Neo4j...")
        await asyncio.wait_for(get_neo4j_db(), timeout=30)
        logger.info("✅ Neo4j connected")
    except TimeoutError:
        logger.error("❌ Neo4j connection timed out")
    except Exception as e:
        logger.error("❌ Neo4j connection failed (%s)", type(e).__name__)

    logger.info("🎉 API startup completed!")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Luminari Sage API...")
    try:
        await close_postgres_db()
        await close_neo4j_db()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error("❌ Error during shutdown (%s)", type(e).__name__)


# Create FastAPI app
app = FastAPI(
    title="Luminari Sage API",
    description="Intelligent lore management system for LuminariMUD",
    version="0.1.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # Set to /sage for reverse proxy
)

# Browser access is limited to explicit origins. API keys are sent in headers,
# not cookies, so credentialed cross-origin requests are unnecessary.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(
        ","
    )
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Configure Authentication
app.add_middleware(AuthMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_allowed_hosts())


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Prevent authenticated API responses from being cached or embedded."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ============================================
# Pydantic Models
# ============================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    services: dict[str, str]


class EntitySearchRequest(BaseModel):
    """Entity search request."""

    query: str = Field(..., description="Search query")
    entity_type: str | None = Field(None, description="Filter by entity type")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")


class EntityResponse(BaseModel):
    """Entity response from Neo4j Entity nodes."""

    uuid: str  # Neo4j Entity UUID (not to be confused with Episodic stable_id)
    type: str
    name: str
    description: str | None = None
    aliases: list[str] = []
    metadata: dict = {}


class LoreSearchRequest(BaseModel):
    """Lore document search request."""

    query: str = Field(..., description="Search query")
    document_type: str | None = Field(None, description="Filter by document type")
    canonical_only: bool = Field(False, description="Only return canonical documents")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")


class LoreDocument(BaseModel):
    """Lore document response."""

    id: str
    title: str
    document_type: str
    source_file: str
    summary: str | None = None
    canonical: bool
    metadata: dict = {}


class ChunkResponse(BaseModel):
    """Text chunk response."""

    chunk_id: str
    document_id: str
    text: str
    similarity: float
    keywords: list[str] = []
    entities: list[dict] = []


class RAGQueryRequest(BaseModel):
    """RAG query request."""

    query: str = Field(..., description="Natural language query")
    limit: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    include_entities: bool = Field(True, description="Include entity information")
    threshold: float = Field(0.1, ge=0.0, le=1.0, description="Similarity threshold")


class RelationshipInfo(BaseModel):
    """Relationship information in the graph."""

    source: str
    target: str
    type: str
    target_name: str
    target_type: str
    strength: int = 1  # 1 = direct, 2 = 2-hop relationship
    metadata: dict[str, Any] | None = None  # For Graphiti's rich semantic properties


class RAGQueryResponse(BaseModel):
    """RAG query response with hybrid Graph RAG support."""

    query: str
    chunks: list[ChunkResponse]
    entities: list[EntityResponse]
    relationships: list[RelationshipInfo] = []
    total_results: int
    metadata: dict[str, Any] = Field(default_factory=dict)  # For additional metadata

    model_config = {
        "extra": "forbid",  # Don't allow extra fields
        "validate_default": True,  # Validate default values
        "use_enum_values": True,
        "json_schema_extra": {
            "example": {
                "query": "example query",
                "chunks": [],
                "entities": [],
                "relationships": [],
                "total_results": 0,
                "metadata": {},
            }
        },
    }


class ValidationRequest(BaseModel):
    """Lore validation request."""

    content: str = Field(..., description="Content to validate against lore")
    context: str | None = Field(
        None, description="Additional context (e.g., location, time period)"
    )
    strict: bool = Field(False, description="Use strict validation rules")


class ValidationIssue(BaseModel):
    """Individual validation issue."""

    severity: str = Field(..., description="Issue severity: error, warning, info")
    category: str = Field(..., description="Issue category: timeline, entity, location, etc.")
    message: str = Field(..., description="Description of the issue")
    suggestion: str | None = Field(None, description="Suggested correction")
    references: list[str] = Field(default_factory=list, description="Related lore references")


class ValidationResponse(BaseModel):
    """Lore validation response."""

    is_valid: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    issues: list[ValidationIssue]
    related_entities: list[EntityResponse]
    supporting_lore: list[str]


class RelationshipValidationRequest(BaseModel):
    """Request for relationship validation with optional autonomous corrections."""

    entity_limit: int = Field(default=1000, description="Maximum entities to check")
    relationship_limit: int = Field(default=5000, description="Maximum relationships to analyze")
    check_bidirectional: bool = Field(default=True, description="Check bidirectional consistency")
    check_mutual_exclusivity: bool = Field(
        default=True, description="Check mutually exclusive relationships"
    )
    check_hierarchies: bool = Field(default=True, description="Validate hierarchical relationships")
    check_semantic_consistency: bool = Field(
        default=True, description="Check semantic property consistency"
    )
    enable_llm_analysis: bool = Field(
        default=True, description="Enable LLM-enhanced semantic analysis"
    )

    # Autonomous correction parameters
    auto_correct: bool = Field(
        default=False, description="Enable autonomous corrections for high-confidence issues"
    )
    correct_duplicates: bool = Field(default=True, description="Remove duplicate relationships")
    standardize_semantics: bool = Field(
        default=True, description="Standardize semantic types to SCREAMING_SNAKE_CASE"
    )
    confidence_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Minimum confidence for auto-correction"
    )
    max_corrections: int = Field(
        default=100, ge=1, le=1000, description="Maximum corrections to apply"
    )
    dry_run: bool = Field(default=True, description="Preview corrections without applying them")


class ValidationFindingResponse(BaseModel):
    """Single validation finding response."""

    finding_id: str
    agent_id: str
    timestamp: str
    severity: str
    category: str
    title: str
    description: str
    confidence_score: float
    confidence_explanation: str
    suggested_action: str
    priority: int
    evidence: list[str]
    affected_entities: list[str]
    affected_relationships: list[str]
    reviewed: bool


class RelationshipValidationResponse(BaseModel):
    """Relationship validation response with correction information."""

    report_id: str
    agent_id: str
    timestamp: str
    validation_type: str
    scope_description: str
    total_items_checked: int
    findings_count: int
    severity_counts: dict[str, int]
    category_counts: dict[str, int]
    findings: list[ValidationFindingResponse]
    execution_time_seconds: float
    success: bool
    error_message: str | None = None
    markdown_report: str

    # Correction information
    corrections_applied: int | None = None
    correction_batch_id: str | None = None
    duplicates_removed: int | None = None
    semantics_standardized: int | None = None
    auto_correction_enabled: bool | None = None
    dry_run: bool | None = None


# Correction-related models
class RollbackRequest(BaseModel):
    """Request to rollback corrections."""

    rollback_by: str = Field(..., description="Who is performing the rollback")
    rollback_reason: str = Field(
        default="Manual rollback requested", description="Reason for rollback"
    )


class RollbackResponse(BaseModel):
    """Response from rollback operation."""

    success: bool
    message: str
    rollback_by: str
    rollback_reason: str
    rollback_timestamp: str
    statistics: dict[str, int] | None = None


class CorrectionHistoryResponse(BaseModel):
    """Response for correction history."""

    corrections: list[dict[str, Any]]
    total_count: int


# ============================================
# API Endpoints
# ============================================


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Luminari Sage API",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/ping", tags=["health"])
async def ping():
    """Simple ping endpoint that doesn't require any dependencies."""
    return {"status": "ok", "message": "pong"}


@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Check API health and service status."""
    postgres_db = await get_postgres_db()
    neo4j_db = await get_neo4j_db()

    services = {}

    # Check PostgreSQL
    try:
        await postgres_db.fetchval("SELECT 1")
        services["postgresql"] = "healthy"
    except Exception:
        services["postgresql"] = "unhealthy"

    # Check Neo4j
    try:
        await neo4j_db.execute_query("RETURN 1")
        services["neo4j"] = "healthy"
    except Exception:
        services["neo4j"] = "unhealthy"

    # Check embedder
    services["embedder"] = "healthy" if embedder else "not loaded"

    overall_status = "healthy" if all(s == "healthy" for s in services.values()) else "degraded"

    return HealthResponse(
        status=overall_status,
        version="0.1.0",
        services=services,
    )


@app.get("/api/v1/entities/search", response_model=list[EntityResponse], tags=["entities"])
async def search_entities(
    query: str = Query(..., description="Search query"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
):
    """Search for entities by name or description."""
    neo4j_db = await get_neo4j_db()

    # Build Cypher query
    params = {"query": query.lower(), "limit": limit}

    # If entity_type is specified, filter by label
    label_filter = f":{entity_type}" if entity_type else ""

    cypher = f"""
        MATCH (n:Entity{label_filter})
        WHERE toLower(n.name) CONTAINS $query
              OR toLower(n.description) CONTAINS $query
        RETURN n, labels(n) as node_labels
        LIMIT $limit
    """

    results = await neo4j_db.execute_query(cypher, params)

    entities = []
    for result in results:
        node = result["n"]
        node_labels = result["node_labels"]

        # Extract entity type from labels (filter out 'Entity' and 'Entity_')
        entity_types = [label for label in node_labels if label not in ["Entity", "Entity_"]]
        entity_type = entity_types[0] if entity_types else "unknown"

        # Use uuid field as stable_id
        # Filter out datetime fields and embeddings from metadata
        metadata = {}
        for k, v in node.items():
            if k not in ["uuid", "type", "name", "description", "aliases", "name_embedding"]:
                # Skip datetime objects that can't be serialized
                if not k.endswith("_at") and not k.endswith("_embedding"):
                    metadata[k] = v

        entities.append(
            EntityResponse(
                uuid=node.get("uuid", ""),  # Neo4j Entity UUID
                type=entity_type,
                name=node.get("name", ""),
                description=node.get("description"),
                aliases=node.get("aliases", []),
                metadata=metadata,
            )
        )

    return entities


@app.get("/api/v1/entities/{entity_id}", response_model=EntityResponse, tags=["entities"])
async def get_entity_by_id(entity_id: str):
    """Get detailed information about a specific entity by ID."""
    neo4j_db = await get_neo4j_db()

    # Query Neo4j for entity by UUID
    cypher = """
        MATCH (n:Entity {uuid: $entity_id})
        RETURN n, labels(n) as node_labels
    """

    results = await neo4j_db.execute_query(cypher, {"entity_id": entity_id})

    if not results:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Extract results based on Neo4j driver version
    records = results.records if hasattr(results, "records") else results

    if not records:
        raise HTTPException(status_code=404, detail="Entity not found")

    record = records[0]
    node = record["n"]
    node_labels = record["node_labels"]

    # Extract entity type from labels (filter out 'Entity' and 'Entity_')
    entity_types = [label for label in node_labels if label not in ["Entity", "Entity_"]]
    entity_type = entity_types[0] if entity_types else "unknown"

    # Filter out datetime fields and embeddings from metadata
    metadata = {}
    for k, v in node.items():
        if k not in ["uuid", "type", "name", "description", "aliases", "name_embedding"]:
            # Skip datetime objects that can't be serialized
            if not k.endswith("_at") and not k.endswith("_embedding"):
                metadata[k] = v

    return EntityResponse(
        uuid=node.get("uuid", ""),  # Neo4j Entity UUID
        type=entity_type,
        name=node.get("name", ""),
        description=node.get("description"),
        aliases=node.get("aliases", []),
        metadata=metadata,
    )


@app.get("/api/v1/entities/{entity_id}/relationships", tags=["entities"])
async def get_entity_relationships_list(entity_id: str, limit: int = 50):
    """Get a lightweight list of relationships for an entity (IDs and basic info only)."""
    neo4j_db = await get_neo4j_db()

    # Limit to reasonable number for listing
    limit = min(limit, 100)  # Reasonable cap for listing

    # Lightweight query - just basic relationship info, no heavy properties
    cypher = """
        MATCH (source:Entity {uuid: $entity_id})
        OPTIONAL MATCH (source)-[r1]->(target:Entity)
        OPTIONAL MATCH (other:Entity)-[r2]->(source)
        WITH source,
             collect(DISTINCT {
                relationship_id: id(r1),
                relationship_type: type(r1),
                direction: 'outgoing',
                target_id: target.uuid,
                target_name: target.name,
                target_type: head([label IN labels(target) WHERE label <> 'Entity' AND label <> 'Entity_'])
             })[0..$limit] as outgoing_relationships,
             collect(DISTINCT {
                relationship_id: id(r2),
                relationship_type: type(r2),
                direction: 'incoming',
                source_id: other.uuid,
                source_name: other.name,
                source_type: head([label IN labels(other) WHERE label <> 'Entity' AND label <> 'Entity_'])
             })[0..$limit] as incoming_relationships
        RETURN outgoing_relationships, incoming_relationships
    """

    results = await neo4j_db.execute_query(cypher, {"entity_id": entity_id, "limit": limit})

    if not results:
        return {"relationships": []}

    # Extract results based on Neo4j driver version
    records = results.records if hasattr(results, "records") else results

    if not records:
        return {"relationships": []}

    record = records[0]
    all_relationships = []

    # Process outgoing relationships (lightweight - no complex properties)
    outgoing = record.get("outgoing_relationships", [])
    for rel in outgoing:
        if rel and rel.get("target_id") and rel.get("relationship_id") is not None:
            all_relationships.append(
                {
                    "relationship_id": rel["relationship_id"],
                    "relationship_type": rel["relationship_type"],
                    "direction": "outgoing",
                    "target_id": rel["target_id"],
                    "target_name": rel["target_name"],
                    "target_type": rel.get("target_type", "unknown"),
                }
            )

    # Process incoming relationships (lightweight - no complex properties)
    incoming = record.get("incoming_relationships", [])
    for rel in incoming:
        if rel and rel.get("source_id") and rel.get("relationship_id") is not None:
            all_relationships.append(
                {
                    "relationship_id": rel["relationship_id"],
                    "relationship_type": rel["relationship_type"],
                    "direction": "incoming",
                    "source_id": rel["source_id"],
                    "source_name": rel["source_name"],
                    "source_type": rel.get("source_type", "unknown"),
                }
            )

    return {"relationships": all_relationships}


@app.get("/api/v1/relationships/{relationship_id}", tags=["entities"])
async def get_relationship_details(relationship_id: int):
    """Get detailed information about a specific relationship including all properties."""
    neo4j_db = await get_neo4j_db()

    # Query for relationship details by internal Neo4j ID
    cypher = """
        MATCH (source)-[r]->(target)
        WHERE id(r) = $relationship_id
        RETURN
            id(r) as relationship_id,
            type(r) as relationship_type,
            source.uuid as source_id,
            source.name as source_name,
            labels(source) as source_labels,
            target.uuid as target_id,
            target.name as target_name,
            labels(target) as target_labels,
            properties(r) as properties
    """

    results = await neo4j_db.execute_query(cypher, {"relationship_id": relationship_id})

    if not results:
        raise HTTPException(status_code=404, detail="Relationship not found")

    records = results.records if hasattr(results, "records") else results
    if not records:
        raise HTTPException(status_code=404, detail="Relationship not found")

    record = records[0]

    # Extract entity types
    source_labels = record.get("source_labels", [])
    source_type = next(
        (label for label in source_labels if label not in ["Entity", "Entity_"]), "unknown"
    )

    target_labels = record.get("target_labels", [])
    target_type = next(
        (label for label in target_labels if label not in ["Entity", "Entity_"]), "unknown"
    )

    # Process properties with serialization safety
    properties = record.get("properties", {})
    safe_properties = {}

    for k, v in properties.items():
        if k not in [
            "source_node_uuid",
            "target_node_uuid",
            "uuid",
            "embedding",
            "name_embedding",
            "summary_embedding",
        ]:
            try:
                if hasattr(v, "isoformat"):  # DateTime objects
                    safe_properties[k] = v.isoformat()
                elif isinstance(v, list) and len(v) > 100:  # Skip large embeddings
                    safe_properties[k] = f"<embedding vector with {len(v)} dimensions>"
                elif isinstance(v, (str, int, float, bool, type(None))):
                    safe_properties[k] = v
                else:
                    safe_properties[k] = str(v)
            except Exception:
                continue  # Skip problematic properties

    return {
        "relationship_id": record["relationship_id"],
        "relationship_type": record["relationship_type"],
        "source": {"id": record["source_id"], "name": record["source_name"], "type": source_type},
        "target": {"id": record["target_id"], "name": record["target_name"], "type": target_type},
        "properties": safe_properties,
    }


@app.get("/api/v1/lore/search", response_model=list[LoreDocument], tags=["lore"])
async def search_lore(
    query: str = Query(..., description="Search query"),
    document_type: str | None = Query(None, description="Filter by document type"),
    canonical_only: bool = Query(False, description="Only canonical documents"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
):
    """Search lore documents by title or content."""
    postgres_db = await get_postgres_db()

    # Build SQL query
    conditions = ["search_vector @@ plainto_tsquery('english', $1)"]
    params = [query]
    param_count = 1

    if document_type:
        param_count += 1
        conditions.append(f"document_type = ${param_count}")
        params.append(document_type)

    if canonical_only:
        conditions.append("canonical = true")

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT id, title, document_type, source_file, summary, canonical, metadata
        FROM lore_documents
        WHERE {where_clause}
        ORDER BY ts_rank(search_vector, plainto_tsquery('english', $1)) DESC
        LIMIT ${param_count + 1}
    """
    params.append(limit)

    results = await postgres_db.fetch(sql, *params)

    documents = []
    for row in results:
        # Handle metadata that may be returned as string or dict
        metadata = row["metadata"]
        if isinstance(metadata, str):
            import json

            metadata = json.loads(metadata) if metadata else {}
        elif metadata is None:
            metadata = {}

        documents.append(
            LoreDocument(
                id=str(row["id"]),
                title=row["title"],
                document_type=row["document_type"],
                source_file=row["source_file"],
                summary=row["summary"],
                canonical=row["canonical"],
                metadata=metadata,
            )
        )

    return documents


@app.post("/api/v1/rag/query", response_model=RAGQueryResponse, tags=["rag"])
async def rag_query(request: RAGQueryRequest):
    """Hybrid Graph RAG with PostgreSQL primary search + Graphiti focused search.

    Implementation strategy:
    1. PostgreSQL vector search for relevant episodes
    2. Get Neo4j Episodic node UUIDs via stable_id
    3. Use Graphiti focused search centered on those episodes
    4. Combine results for comprehensive response
    """
    logger.info("RAG query received (%d characters)", len(request.query))

    # Check embedder is available
    if not embedder:
        raise HTTPException(status_code=503, detail="Embedder not loaded")

    postgres_db = await get_postgres_db()

    # Generate query embedding
    query_embedding = await embedder.embed_text(request.query)
    # Convert to PostgreSQL vector format
    query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Step 1: Hybrid search - both vector similarity and full-text search
    # Vector search results
    vector_results = await postgres_db.fetch(
        """
        SELECT
            e.id as episode_id,
            e.document_id,
            e.text,
            e.episode_index,
            1 - (e.embedding <=> $1::vector) as vector_similarity,
            d.title as doc_title,
            'vector' as search_type
        FROM episodes e
        JOIN lore_documents d ON e.document_id = d.id
        WHERE e.embedding IS NOT NULL
            AND 1 - (e.embedding <=> $1::vector) > $2
        ORDER BY e.embedding <=> $1::vector
        LIMIT $3
    """,
        query_embedding_str,
        request.threshold,
        request.limit,
    )

    # Full-text search results (BM25-like)
    text_results = await postgres_db.fetch(
        """
        SELECT
            e.id as episode_id,
            e.document_id,
            e.text,
            e.episode_index,
            ts_rank(to_tsvector('english', e.text), plainto_tsquery('english', $1)) as text_score,
            d.title as doc_title,
            'text' as search_type
        FROM episodes e
        JOIN lore_documents d ON e.document_id = d.id
        WHERE to_tsvector('english', e.text) @@ plainto_tsquery('english', $1)
        ORDER BY ts_rank(to_tsvector('english', e.text), plainto_tsquery('english', $1)) DESC
        LIMIT $2
    """,
        request.query,
        request.limit,
    )

    # Combine results using Reciprocal Rank Fusion (RRF)
    episode_results = []
    rrf_scores = {}
    k = 60  # RRF constant

    # Add vector results with RRF scoring
    for rank, row in enumerate(vector_results, 1):
        episode_id = row["episode_id"]
        rrf_scores[episode_id] = rrf_scores.get(episode_id, 0) + 1.0 / (k + rank)
        if episode_id not in [r["episode_id"] for r in episode_results]:
            episode_results.append(
                {
                    **dict(row),
                    "similarity": row[
                        "vector_similarity"
                    ],  # Use vector similarity as primary score
                    "rrf_score": rrf_scores[episode_id],
                    "search_type": "hybrid",
                }
            )

    # Add text results with RRF scoring
    for rank, row in enumerate(text_results, 1):
        episode_id = row["episode_id"]
        rrf_scores[episode_id] = rrf_scores.get(episode_id, 0) + 1.0 / (k + rank)

        # Update existing or add new
        existing = next((r for r in episode_results if r["episode_id"] == episode_id), None)
        if existing:
            existing["rrf_score"] = rrf_scores[episode_id]
            existing["search_type"] = "hybrid"
            # Boost similarity score if found in both searches
            existing["similarity"] = min(1.0, existing["similarity"] + 0.1)
        else:
            # For text-only results, create a synthetic similarity score from text_score
            episode_results.append(
                {
                    "episode_id": episode_id,
                    "document_id": row["document_id"],
                    "text": row["text"],
                    "episode_index": row["episode_index"],
                    "similarity": min(0.9, row["text_score"]),  # Convert text_score to similarity
                    "doc_title": row["doc_title"],
                    "rrf_score": rrf_scores[episode_id],
                    "search_type": "text",
                }
            )

    # Sort by RRF score (higher is better)
    episode_results.sort(key=lambda x: x["rrf_score"], reverse=True)
    # Use the requested limit
    episode_results = episode_results[: request.limit]

    # Convert episodes to chunk format for compatibility
    chunks = []
    episode_uuids = []
    episode_id_set = set()
    doc_neighbor_indices: dict[Any, set[int]] = {}
    doc_similarity_map: dict[Any, float] = {}

    for row in episode_results:
        chunk = ChunkResponse(
            chunk_id=str(row["episode_id"]),  # Using episode_id as chunk_id
            document_id=str(row["document_id"]),
            text=row["text"],
            similarity=float(row["similarity"]),
            keywords=[],  # Episodes don't have keywords yet
            entities=[],  # Will be populated from graph
        )
        chunks.append(chunk)
        episode_uuids.append(str(row["episode_id"]))
        episode_id_set.add(str(row["episode_id"]))

        doc_id = row["document_id"]
        doc_similarity_map[doc_id] = max(
            doc_similarity_map.get(doc_id, 0.0), float(row["similarity"])
        )

        neighbor_indices = doc_neighbor_indices.setdefault(doc_id, set())
        base_index = row["episode_index"]
        for offset in (-2, -1, 1, 2):
            neighbor_index = base_index + offset
            if neighbor_index >= 0:
                neighbor_indices.add(neighbor_index)

    # Bring in neighboring episodes so the answer chain sees adjacent lore context
    for doc_id, indices in doc_neighbor_indices.items():
        # Skip if we only collected the current episode index
        if not indices:
            continue

        # Limit to a small window to avoid blowing up the response payload
        sorted_indices = sorted(idx for idx in indices if idx >= 0)[:10]
        if not sorted_indices:
            continue

        additional_episodes = await postgres_db.fetch(
            """
            SELECT
                e.id as episode_id,
                e.document_id,
                e.text,
                e.episode_index
            FROM episodes e
            WHERE e.document_id = $1
              AND e.episode_index = ANY($2::int[])
            """,
            doc_id,
            sorted_indices,
        )

        base_similarity = doc_similarity_map.get(doc_id, 0.0)
        for episode in additional_episodes:
            episode_id = str(episode["episode_id"])
            if episode_id in episode_id_set:
                continue

            episode_id_set.add(episode_id)
            # Slightly discount similarity for non-primary neighbors to keep ordering stable
            neighbor_similarity = max(base_similarity - 0.05, 0.0)

            chunks.append(
                ChunkResponse(
                    chunk_id=episode_id,
                    document_id=str(episode["document_id"]),
                    text=episode["text"],
                    similarity=neighbor_similarity,
                    keywords=[],
                    entities=[],
                )
            )

    # Step 2: Get Neo4j Episodic node UUIDs and use Graphiti focused search
    graphiti_entities = []
    graphiti_relationships = []

    # Map PostgreSQL episode UUIDs to Neo4j Episodic node UUIDs
    neo4j_episode_map = {}
    if episode_uuids:
        try:
            neo4j_db = await get_neo4j_db()

            # Get Neo4j Episodic nodes by stable_id
            neo4j_episodes = await neo4j_db.execute_query(
                """
                MATCH (ep:Episodic)
                WHERE ep.stable_id IN $episode_uuids
                RETURN ep.stable_id as pg_uuid, ep.uuid as neo4j_uuid
            """,
                {"episode_uuids": episode_uuids},
            )

            # Build mapping
            for record in neo4j_episodes:
                neo4j_episode_map[record["pg_uuid"]] = record["neo4j_uuid"]

            logger.info(f"Mapped {len(neo4j_episode_map)} episodes to Neo4j nodes")

        except Exception as e:
            logger.warning("Failed to map episodes to Neo4j (%s)", type(e).__name__)

    # Step 3: Use Graphiti focused search for each top episode
    if neo4j_episode_map and len(neo4j_episode_map) > 0:
        try:
            from ..graphiti import initialize_graphiti

            graphiti = await initialize_graphiti()

            # Use focused search on top episodes (limit to top 3 for performance)
            top_episodes = list(neo4j_episode_map.values())[:3]
            all_edges = []

            for center_uuid in top_episodes:
                try:
                    # Focused search centered on this episode
                    edges = await graphiti.graphiti.search(
                        query=request.query,
                        center_node_uuid=center_uuid,
                        num_results=5,  # Get top 5 edges per episode
                    )
                    all_edges.extend(edges)
                    logger.debug("Found %d edges for focused episode", len(edges))
                except Exception as e:
                    logger.warning(
                        "Graphiti focused search failed (%s)",
                        type(e).__name__,
                    )

            # Process Graphiti edges to extract entities and relationships
            entity_uuids = set()
            for edge in all_edges:
                entity_uuids.add(edge.source_node_uuid)
                entity_uuids.add(edge.target_node_uuid)

                # Add relationship info with semantic properties from attributes
                # Filter out embedding fields to prevent context overflow
                properties = {}
                if hasattr(edge, "attributes") and edge.attributes:
                    properties = {
                        k: v
                        for k, v in edge.attributes.items()
                        if not k.endswith("_embedding") and k != "fact_embedding"
                    }
                typed_edge_attributes: dict[str, Any] = {}
                edge_model = EDGE_TYPES.get(edge.name)
                if edge_model and properties:
                    try:
                        model_instance = edge_model(
                            **{k: properties.get(k) for k in edge_model.model_fields}
                        )
                        typed_edge_attributes = {
                            k: v
                            for k, v in model_instance.model_dump().items()
                            if v not in (None, "", [], {})
                        }
                    except ValidationError as exc:
                        logger.debug(
                            "Failed to parse edge metadata for %s (%s)",
                            edge.name,
                            type(exc).__name__,
                        )

                graphiti_relationships.append(
                    {
                        "source": edge.source_node_uuid,
                        "target": edge.target_node_uuid,
                        "type": edge.name,
                        "fact": edge.fact,
                        "episodes": edge.episodes,
                        "properties": properties,
                        "typed_attributes": typed_edge_attributes,
                    }
                )

            # Fetch entity details from Neo4j
            if entity_uuids:
                entity_results = await neo4j_db.execute_query(
                    """
                    MATCH (n)
                    WHERE n.uuid IN $uuids
                    RETURN n.uuid as uuid, n.name as name,
                           labels(n) as labels, n.summary as summary,
                           properties(n) as properties
                """,
                    {"uuids": list(entity_uuids)},
                )

                for record in entity_results:
                    graphiti_entities.append(
                        {
                            "id": record["uuid"],
                            "name": record["name"],
                            "labels": record["labels"] or [],
                            "summary": record.get("summary"),
                            "properties": record.get("properties", {}) or {},
                        }
                    )

            await graphiti.close()
            logger.info(
                f"Graphiti focused search found {len(all_edges)} edges, {len(graphiti_entities)} entities"
            )

        except Exception as graphiti_error:
            # Gracefully handle Graphiti failures - don't break the main RAG flow
            logger.warning(
                "Graphiti focused search failed (%s)",
                type(graphiti_error).__name__,
            )

    # Step 4: Simplified - We rely on Graphiti for all graph traversal
    # The Graphiti focused search already gave us entities and relationships

    # Note: Don't manually disconnect PostgreSQL - it's a global singleton
    # Connection pooling is handled by asyncpg

    # Process Graphiti results - this is our primary source for graph data
    all_entities = []
    all_relationships = []

    # Process Graphiti entities
    for graphiti_entity in graphiti_entities:
        raw_properties = graphiti_entity.get("properties", {})
        labels = graphiti_entity.get("labels") or raw_properties.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        entity_type_label = "Entity"
        for label in labels:
            if label in ENTITY_TYPES:
                entity_type_label = label
                break
        else:
            if labels:
                entity_type_label = labels[0]
        typed_metadata: dict[str, Any] = {}
        extra_metadata: dict[str, Any] = {}

        model_cls = ENTITY_TYPES.get(entity_type_label)
        if model_cls:
            try:
                model_instance = model_cls(
                    **{k: raw_properties.get(k) for k in model_cls.model_fields}
                )
                typed_metadata = {
                    k: v
                    for k, v in model_instance.model_dump().items()
                    if v not in (None, "", [], {})
                }
            except ValidationError as exc:
                logger.debug(
                    "Failed to parse entity metadata for %s (%s)",
                    graphiti_entity.get("name"),
                    type(exc).__name__,
                )

        for key, value in raw_properties.items():
            if key in {"name", "summary", "labels", "name_embedding", "uuid", "created_at"}:
                continue
            if key.endswith("_embedding"):
                continue
            if key in (model_cls.model_fields if model_cls else {}):
                continue
            if value in (None, "", [], {}):
                continue
            extra_metadata[key] = value

        metadata: dict[str, Any] = {}
        if typed_metadata:
            metadata["attributes"] = typed_metadata
        if extra_metadata:
            metadata["raw"] = extra_metadata

        entity_response = EntityResponse(
            uuid=graphiti_entity["id"],
            type=entity_type_label,
            name=graphiti_entity["name"],
            description=graphiti_entity.get("summary") or raw_properties.get("summary"),
            aliases=(
                raw_properties.get("aliases", [])
                if isinstance(raw_properties.get("aliases"), list)
                else []
            ),
            metadata=metadata,
        )
        all_entities.append(entity_response)

    # Process Graphiti relationships
    for graphiti_rel in graphiti_relationships:
        if graphiti_rel["source"] and graphiti_rel["target"]:
            # Get target entity name from properties or set default
            target_name = "Unknown"
            target_type = "unknown"

            # Try to find target entity name from the properties
            if graphiti_rel.get("properties"):
                target_name = graphiti_rel["properties"].get("name", target_name)
                target_type = graphiti_rel["properties"].get("type", target_type)

            # Include ALL Graphiti properties in the relationship
            enhanced_rel = {
                "source": graphiti_rel["source"],
                "target": graphiti_rel["target"],
                "type": graphiti_rel["type"],
                "target_name": target_name,
                "target_type": target_type,
                "strength": 1,  # Default strength
                "fact": graphiti_rel.get("fact", ""),  # Include the fact text
                "episodes": graphiti_rel.get("episodes", []),  # Include episode references
                "graphiti_properties": graphiti_rel.get(
                    "properties", {}
                ),  # ALL semantic properties
                "typed_attributes": graphiti_rel.get("typed_attributes", {}),
            }
            all_relationships.append(enhanced_rel)

    # Convert relationships to the proper format
    relationship_info = []
    logger.info(f"Processing {len(all_relationships)} relationships from Graphiti")
    for rel in all_relationships:
        # Standard RelationshipInfo fields
        rel_info = RelationshipInfo(
            source=rel["source"],
            target=rel["target"],
            type=rel["type"],
            target_name=rel["target_name"],
            target_type=rel["target_type"],
            strength=rel["strength"],
        )

        # Include fact, episodes, and Graphiti properties as metadata
        metadata_dict = {}

        # Add the fact if it exists - this is the most important piece
        if rel.get("fact"):
            metadata_dict["fact"] = rel["fact"]
            logger.debug("Added relationship fact (%d characters)", len(rel["fact"]))

        # Add episodes if they exist
        if rel.get("episodes"):
            metadata_dict["episodes"] = rel["episodes"][:5]  # Limit to first 5 episodes

        # Add other Graphiti properties
        if rel.get("graphiti_properties"):
            # Clean metadata: remove embeddings and internal fields
            for k, v in rel["graphiti_properties"].items():
                # Skip embeddings and internal fields
                if not k.endswith("_embedding") and k not in [
                    "fact_embedding",
                    "uuid",
                    "created_at",
                    "group_id",
                    "source_node_uuid",
                    "target_node_uuid",
                    "name",
                    "episodes",
                ]:
                    metadata_dict[k] = v

        if rel.get("typed_attributes"):
            metadata_dict["attributes"] = rel["typed_attributes"]

        if metadata_dict:
            rel_info.metadata = metadata_dict

        relationship_info.append(rel_info)

    # Build structured metadata payloads and synthetic chunks for graph insights
    graph_entity_payload: list[dict[str, Any]] = []
    graph_relationship_payload: list[dict[str, Any]] = []
    graph_chunks: list[ChunkResponse] = []

    for entity in all_entities:
        graph_entity_payload.append(
            {
                "uuid": entity.uuid,
                "name": entity.name,
                "type": entity.type,
                "description": entity.description,
                "metadata": entity.metadata,
            }
        )

        insight_lines = [f"Entity: {entity.name} ({entity.type})"]
        if entity.description:
            insight_lines.append(entity.description)

        attributes = entity.metadata.get("attributes") if entity.metadata else None
        if isinstance(attributes, dict):
            for key, value in attributes.items():
                insight_lines.append(f"{key.replace('_', ' ').title()}: {value}")

        raw_meta = entity.metadata.get("raw") if entity.metadata else None
        if isinstance(raw_meta, dict):
            for key in ["stable_id", "group_id", "status"]:
                if raw_meta.get(key):
                    insight_lines.append(f"{key.replace('_', ' ').title()}: {raw_meta[key]}")

        if len(insight_lines) > 1:
            chunk_text = "\n".join(insight_lines)
            graph_chunks.append(
                ChunkResponse(
                    chunk_id=f"graph-entity-{entity.uuid}",
                    document_id=entity.uuid,
                    text=chunk_text,
                    similarity=0.92,
                    keywords=[],
                    entities=[{"uuid": entity.uuid, "name": entity.name, "type": entity.type}],
                )
            )

    for rel, rel_info in zip(all_relationships, relationship_info):
        graph_relationship_payload.append(
            {
                "source": rel_info.source,
                "target": rel_info.target,
                "type": rel_info.type,
                "fact": rel.get("fact"),
                "metadata": rel_info.metadata,
            }
        )

        insight_lines = [
            f"Relationship: {rel_info.type} ({rel_info.source} → {rel_info.target_name or rel_info.target})"
        ]
        fact_text = (
            rel.get("fact") or (rel_info.metadata or {}).get("fact") if rel_info.metadata else None
        )
        if fact_text:
            insight_lines.append(f"Fact: {fact_text}")

        attributes = (rel_info.metadata or {}).get("attributes") if rel_info.metadata else None
        if isinstance(attributes, dict):
            for key, value in attributes.items():
                insight_lines.append(f"{key.replace('_', ' ').title()}: {value}")

        if len(insight_lines) > 1:
            graph_chunks.append(
                ChunkResponse(
                    chunk_id=f"graph-rel-{rel_info.source}-{rel_info.target}",
                    document_id=rel_info.target,
                    text="\n".join(insight_lines),
                    similarity=0.9,
                    keywords=[],
                    entities=[
                        {"uuid": rel_info.source, "role": "source"},
                        {"uuid": rel_info.target, "role": "target"},
                    ],
                )
            )

    if graph_chunks:
        max_graph_chunks = 5
        chunks.extend(graph_chunks[:max_graph_chunks])

    response_metadata: dict[str, Any] = {}
    if graph_entity_payload:
        response_metadata["graph_entities"] = graph_entity_payload
    if graph_relationship_payload:
        response_metadata["graph_relationships"] = graph_relationship_payload

    # Calculate token usage for context monitoring
    total_context_text = "\n\n".join([chunk.text for chunk in chunks])
    context_tokens = count_tokens(total_context_text)
    max_context_tokens = 3000  # Reserve space for prompt and response (out of 4096 total)

    logger.info(f"Context tokens: {context_tokens}/{max_context_tokens} ({len(chunks)} chunks)")

    # Apply intelligent context truncation if needed
    if context_tokens > max_context_tokens:
        logger.warning(
            f"⚠️ Context exceeds recommended size: {context_tokens} > {max_context_tokens}. Applying truncation."
        )

        # Select the highest-similarity chunks that fit the budget. This works on indices
        # rather than matching chunk text against a joined-then-resplit string: chunk text
        # is markdown containing blank lines, so splitting the join on "\n\n" shattered
        # every chunk and matched none of them, silently emptying the result set.
        original_chunk_count = len(chunks)
        keep_indices = select_texts_within_budget(
            [(chunk.text, chunk.similarity) for chunk in chunks],
            max_tokens=max_context_tokens,
            model="gpt-4",  # Use as approximation for token counting
        )
        chunks = [chunks[i] for i in keep_indices]

        # A single chunk larger than the whole budget is kept but trimmed to fit, so the
        # caller still gets its most relevant context instead of nothing.
        if len(chunks) == 1 and count_tokens(chunks[0].text) > max_context_tokens:
            chunks = [
                chunks[0].model_copy(
                    update={"text": truncate_text(chunks[0].text, max_context_tokens)}
                )
            ]

        # Recalculate context tokens
        total_context_text = "\n\n".join([chunk.text for chunk in chunks])
        context_tokens = count_tokens(total_context_text)
        logger.info(
            f"✂️ Truncated context: {original_chunk_count} → {len(chunks)} chunks, {context_tokens} tokens"
        )

    # Create response
    response_kwargs: dict[str, Any] = {
        "query": request.query,
        "chunks": chunks,
        "entities": all_entities,
        "relationships": relationship_info,
        "total_results": len(chunks),
    }

    if response_metadata:
        response_kwargs["metadata"] = response_metadata
        # Add token usage to metadata
        response_kwargs["metadata"]["context_tokens"] = context_tokens
        response_kwargs["metadata"]["max_context_tokens"] = max_context_tokens

    response = RAGQueryResponse(**response_kwargs)

    logger.info(f"📤 Returning response with metadata keys: {list(response.metadata.keys())}")
    return response


@app.post("/api/v1/validate", response_model=ValidationResponse, tags=["validation"])
async def validate_lore(request: ValidationRequest):
    """Validate content against existing lore."""
    if not embedder:
        raise HTTPException(status_code=503, detail="Embedder not loaded")

    postgres_db = await get_postgres_db()
    neo4j_db = await get_neo4j_db()

    issues = []
    related_entities = []
    supporting_lore = []

    # Generate embedding for the content
    content_embedding = await embedder.embed_text(request.content)

    # Find similar lore chunks for context
    similar_chunks = await postgres_db.fetch(
        """
        SELECT
            c.text,
            c.keywords,
            c.entity_refs,
            1 - (c.embedding <=> $1::vector) as similarity,
            d.title,
            d.canonical
        FROM chunks c
        JOIN lore_documents d ON c.document_id = d.id
        WHERE 1 - (c.embedding <=> $1::vector) > 0.5
        ORDER BY c.embedding <=> $1::vector
        LIMIT 10
    """,
        content_embedding,
    )

    # Extract mentioned entities from content (simple pattern matching for demo)
    import re

    # Look for capitalized proper nouns
    potential_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", request.content)

    # Check each potential entity
    for entity_name in potential_entities:
        # Search for entity in Neo4j
        cypher = """
            MATCH (n:Entity)
            WHERE toLower(n.name) = toLower($name) OR $name IN n.aliases
            RETURN n
        """
        results = await neo4j_db.execute_query(cypher, {"name": entity_name})

        if results:
            # Entity exists, add to related entities
            node = results[0]["n"]
            related_entities.append(
                EntityResponse(
                    uuid=node.get("uuid", ""),  # Neo4j Entity UUID (not stable_id)
                    type=node.get("type", "unknown"),
                    name=node.get("name", ""),
                    description=node.get("description"),
                    aliases=node.get("aliases", []),
                    metadata={},
                )
            )
        elif request.strict:
            # Unknown entity in strict mode
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="entity",
                    message=f"Unknown entity: '{entity_name}'",
                    suggestion=f"Verify if '{entity_name}' is a new entity or a typo",
                    references=[],
                )
            )

    # Check for timeline consistency (simplified)
    year_pattern = re.findall(r"\b(\d{3,4})\s*(?:DR|CR|Age)\b", request.content, re.IGNORECASE)
    if year_pattern:
        for year_str in year_pattern:
            year = int(year_str)
            # Check if year is within known timeline bounds
            if year > 1500:  # Example: current year in Luminari timeline
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="timeline",
                        message=f"Year {year} is beyond the current timeline (1500 DR)",
                        suggestion="Check the timeline reference",
                        references=["ages_and_cataclysms/TIMELINE.md"],
                    )
                )

    # Add supporting lore from similar chunks
    for chunk in similar_chunks[:3]:
        if chunk["canonical"]:
            supporting_lore.append(f"{chunk['title']}: {chunk['text'][:200]}...")

    # Calculate validation confidence
    confidence = 0.8  # Base confidence
    if issues:
        confidence -= len([i for i in issues if i.severity == "error"]) * 0.2
        confidence -= len([i for i in issues if i.severity == "warning"]) * 0.1
    confidence = max(0.0, min(1.0, confidence))

    # Determine overall validity
    is_valid = not any(issue.severity == "error" for issue in issues)

    return ValidationResponse(
        is_valid=is_valid,
        confidence=confidence,
        issues=issues,
        related_entities=related_entities,
        supporting_lore=supporting_lore,
    )


@app.post(
    "/api/v1/validate/relationships",
    response_model=RelationshipValidationResponse,
    tags=["validation"],
)
async def validate_relationships(request: RelationshipValidationRequest):
    """Validate entity relationships in the knowledge graph."""
    try:
        # Get OpenAI API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        # Import here to avoid circular import
        from src.agents.relationship_validator import RelationshipValidator

        # Create validator
        validator = RelationshipValidator(openai_api_key=openai_api_key)

        # Run validation with optional corrections
        report = await validator.validate(
            entity_limit=request.entity_limit,
            relationship_limit=request.relationship_limit,
            check_bidirectional=request.check_bidirectional,
            check_mutual_exclusivity=request.check_mutual_exclusivity,
            check_hierarchies=request.check_hierarchies,
            check_semantic_consistency=request.check_semantic_consistency,
            enable_llm_analysis=request.enable_llm_analysis,
            auto_correct=request.auto_correct,
            correct_duplicates=request.correct_duplicates,
            standardize_semantics=request.standardize_semantics,
            confidence_threshold=request.confidence_threshold,
            max_corrections=request.max_corrections,
            dry_run=request.dry_run,
        )

        # Convert findings to response format
        finding_responses = []
        for finding in report.findings:
            finding_responses.append(
                ValidationFindingResponse(
                    finding_id=finding.finding_id,
                    agent_id=finding.agent_id,
                    timestamp=finding.timestamp.isoformat(),
                    severity=finding.severity.value,
                    category=finding.category,
                    title=finding.title,
                    description=finding.description,
                    confidence_score=finding.confidence_score,
                    confidence_explanation=finding.confidence_explanation,
                    suggested_action=finding.suggested_action,
                    priority=finding.priority,
                    evidence=finding.evidence,
                    affected_entities=finding.affected_entities,
                    affected_relationships=finding.affected_relationships,
                    reviewed=finding.reviewed,
                )
            )

        # Generate markdown report
        markdown_report = report.to_markdown()

        # Extract correction metadata from report
        correction_metadata = report.metadata or {}

        return RelationshipValidationResponse(
            report_id=report.report_id,
            agent_id=report.agent_id,
            timestamp=report.timestamp.isoformat(),
            validation_type=report.validation_type,
            scope_description=report.scope_description,
            total_items_checked=report.total_items_checked,
            findings_count=report.findings_count,
            severity_counts=report.severity_counts,
            category_counts=report.category_counts,
            findings=finding_responses,
            execution_time_seconds=report.execution_time_seconds,
            success=report.success,
            error_message=report.error_message,
            markdown_report=markdown_report,
            # Include correction information
            corrections_applied=correction_metadata.get("corrections_applied"),
            correction_batch_id=correction_metadata.get("correction_batch_id"),
            duplicates_removed=correction_metadata.get("duplicates_removed"),
            semantics_standardized=correction_metadata.get("semantics_standardized"),
            auto_correction_enabled=correction_metadata.get("auto_correction_enabled"),
            dry_run=correction_metadata.get("dry_run"),
        )

    except Exception as e:
        logger.error("Relationship validation failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Validation"))


@app.get("/api/v1/validate/history", tags=["validation"])
async def get_validation_history(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    validation_type: str | None = Query(None, description="Filter by validation type"),
    limit: int = Query(50, description="Maximum number of reports to return"),
    offset: int = Query(0, description="Number of reports to skip"),
):
    """Get validation history with optional filtering."""
    try:
        from src.agents.validation_storage import ValidationStorageService

        reports = await ValidationStorageService.list_reports(
            agent_id=agent_id, validation_type=validation_type, limit=limit, offset=offset
        )

        return reports

    except Exception as e:
        logger.error("Failed to retrieve validation history (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Validation history retrieval")
        )


@app.get("/api/v1/validate/report/{report_id}", tags=["validation"])
async def get_validation_report(report_id: str):
    """Get a specific validation report with all findings."""
    try:
        from src.agents.validation_storage import ValidationStorageService

        report = await ValidationStorageService.get_report(report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Validation report not found")

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve validation report (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Validation report retrieval")
        )


@app.get("/api/v1/validate/findings/unreviewed", tags=["validation"])
async def get_unreviewed_findings(
    severity: str | None = Query(None, description="Filter by severity"),
    category: str | None = Query(None, description="Filter by category"),
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    limit: int = Query(100, description="Maximum number of findings to return"),
):
    """Get unreviewed validation findings for human review."""
    try:
        from src.agents.validation_storage import ValidationStorageService

        findings = await ValidationStorageService.get_unreviewed_findings(
            severity=severity, category=category, agent_id=agent_id, limit=limit
        )

        return findings

    except Exception as e:
        logger.error("Failed to retrieve unreviewed findings (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Validation findings retrieval")
        )


class ReviewFindingRequest(BaseModel):
    """Request to mark a finding as reviewed."""

    reviewer: str = Field(..., description="Name/ID of the reviewer")
    action: str = Field(..., description="Action taken by the reviewer")
    notes: str = Field(default="", description="Optional review notes")


@app.post("/api/v1/validate/findings/{finding_id}/review", tags=["validation"])
async def review_finding(finding_id: str, request: ReviewFindingRequest):
    """Mark a validation finding as reviewed by a human."""
    try:
        from src.agents.validation_storage import ValidationStorageService

        success = await ValidationStorageService.mark_finding_reviewed(
            finding_id=finding_id,
            reviewer=request.reviewer,
            action=request.action,
            notes=request.notes,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Validation finding not found")

        return {"message": "Finding marked as reviewed", "finding_id": finding_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to review finding (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Validation finding review")
        )


@app.get("/api/v1/validate/stats", tags=["validation"])
async def get_validation_statistics():
    """Get validation statistics summary."""
    try:
        from src.agents.validation_storage import ValidationStorageService

        stats = await ValidationStorageService.get_statistics()
        return stats

    except Exception as e:
        logger.error("Failed to retrieve validation statistics (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Validation statistics retrieval")
        )


@app.get("/api/v1/stats", tags=["stats"])
async def get_statistics():
    """Get statistics about the lore database."""
    postgres_db = await get_postgres_db()
    neo4j_db = await get_neo4j_db()

    # Get document stats
    doc_stats = await postgres_db.fetchrow("""
        SELECT
            COUNT(*) as total_documents,
            COUNT(DISTINCT document_type) as document_types,
            COUNT(CASE WHEN canonical THEN 1 END) as canonical_documents
        FROM lore_documents
    """)

    # Get episode stats
    chunk_stats = await postgres_db.fetchrow("""
        SELECT
            COUNT(*) as total_chunks,
            AVG(LENGTH(text)) as avg_chunk_size
        FROM episodes
    """)

    # Get entity stats from Neo4j
    entity_stats = await neo4j_db.execute_query("""
        MATCH (n:Entity)
        RETURN COUNT(n) as total_entities,
               COUNT(DISTINCT n.type) as entity_types
    """)

    # Get relationship stats
    rel_stats = await neo4j_db.execute_query("""
        MATCH ()-[r]->()
        RETURN COUNT(r) as total_relationships,
               COUNT(DISTINCT type(r)) as relationship_types
    """)

    return {
        "documents": {
            "total": doc_stats["total_documents"] if doc_stats else 0,
            "types": doc_stats["document_types"] if doc_stats else 0,
            "canonical": doc_stats["canonical_documents"] if doc_stats else 0,
        },
        "chunks": {
            "total": chunk_stats["total_chunks"] if chunk_stats else 0,
            "avg_size": (
                int(chunk_stats["avg_chunk_size"])
                if chunk_stats and chunk_stats["avg_chunk_size"]
                else 0
            ),
        },
        "entities": {
            "total": entity_stats[0]["total_entities"] if entity_stats else 0,
            "types": entity_stats[0]["entity_types"] if entity_stats else 0,
        },
        "relationships": {
            "total": rel_stats[0]["total_relationships"] if rel_stats else 0,
            "types": rel_stats[0]["relationship_types"] if rel_stats else 0,
        },
    }


# ============================================
# Correction & Rollback Endpoints
# ============================================


@app.post(
    "/api/v1/corrections/{correction_id}/rollback",
    response_model=RollbackResponse,
    tags=["corrections"],
)
async def rollback_correction(correction_id: str, request: RollbackRequest):
    """Rollback a single correction."""
    try:
        from src.agents.rollback_manager import RollbackManager

        result = await RollbackManager.rollback_correction(
            correction_id=correction_id,
            rollback_by=request.rollback_by,
            rollback_reason=request.rollback_reason,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail="Rollback failed")

        return RollbackResponse(
            success=result["success"],
            message=result["message"],
            rollback_by=result["rollback_by"],
            rollback_reason=result["rollback_reason"],
            rollback_timestamp=result["rollback_timestamp"],
        )

    except Exception as e:
        logger.error("Failed to rollback correction (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Rollback"))


@app.post(
    "/api/v1/corrections/batch/{batch_id}/rollback",
    response_model=RollbackResponse,
    tags=["corrections"],
)
async def rollback_correction_batch(batch_id: str, request: RollbackRequest):
    """Rollback all corrections in a batch."""
    try:
        from src.agents.rollback_manager import RollbackManager

        result = await RollbackManager.rollback_batch(
            correction_batch_id=batch_id,
            rollback_by=request.rollback_by,
            rollback_reason=request.rollback_reason,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail="Batch rollback failed")

        return RollbackResponse(
            success=result["success"],
            message=result["message"],
            rollback_by=result["rollback_by"],
            rollback_reason=result["rollback_reason"],
            rollback_timestamp=result["rollback_timestamp"],
            statistics=result.get("statistics"),
        )

    except Exception as e:
        logger.error("Failed to rollback correction batch (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Batch rollback"))


@app.get("/api/v1/corrections/batch/{batch_id}/preview", tags=["corrections"])
async def preview_rollback_batch(batch_id: str):
    """Preview what would be rolled back in a batch."""
    try:
        from src.agents.rollback_manager import RollbackManager

        preview = await RollbackManager.preview_rollback_batch(batch_id)

        if not preview["success"]:
            raise HTTPException(status_code=404, detail="Batch not found")

        return preview

    except Exception as e:
        logger.error("Failed to preview rollback for batch (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Rollback preview"))


@app.get(
    "/api/v1/corrections/history", response_model=CorrectionHistoryResponse, tags=["corrections"]
)
async def get_correction_history(
    limit: int = Query(100, description="Maximum corrections to return"),
):
    """Get recent correction history."""
    try:
        from src.agents.correction_storage import CorrectionStorageService

        corrections = await CorrectionStorageService.list_recent_corrections(limit=limit)

        return CorrectionHistoryResponse(corrections=corrections, total_count=len(corrections))

    except Exception as e:
        logger.error("Failed to get correction history (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Correction history retrieval")
        )


@app.get("/api/v1/corrections/stats", tags=["corrections"])
async def get_correction_statistics(days: int = Query(30, description="Number of days to analyze")):
    """Get correction and rollback statistics."""
    try:
        from src.agents.rollback_manager import RollbackManager

        stats = await RollbackManager.get_rollback_statistics(days=days)
        return stats

    except Exception as e:
        logger.error("Failed to get correction statistics (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Correction statistics retrieval")
        )


@app.get("/api/v1/corrections/{correction_id}", tags=["corrections"])
async def get_correction_details(correction_id: str):
    """Get details of a specific correction."""
    try:
        from src.agents.correction_storage import CorrectionStorageService

        correction = await CorrectionStorageService.get_correction(correction_id)

        if not correction:
            raise HTTPException(status_code=404, detail="Correction not found")

        return correction

    except Exception as e:
        logger.error("Failed to get correction (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Correction retrieval"))


@app.get("/api/v1/corrections/batch/{batch_id}/summary", tags=["corrections"])
async def get_correction_batch_summary(batch_id: str):
    """Get summary of corrections in a batch."""
    try:
        from src.agents.correction_storage import CorrectionStorageService

        summary = await CorrectionStorageService.get_correction_batch_summary(batch_id)

        if not summary:
            raise HTTPException(status_code=404, detail="Correction batch not found")

        return summary

    except Exception as e:
        logger.error("Failed to get batch summary (%s)", type(e).__name__)
        raise HTTPException(
            status_code=500, detail=public_error_message("Correction batch retrieval")
        )


# ============================================
# Chat Agent Endpoints
# ============================================


class ChatMessageRequest(BaseModel):
    """Request to send a message to the chat agent."""

    message: str = Field(description="The user's message")
    conversation_id: str | None = Field(
        None, description="Existing conversation ID, or None to create new"
    )
    user_id: str | None = Field(None, description="Optional user identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional request metadata"
    )
    engine: str | None = Field(
        None, description="Chat engine to use: default (legacy) or langchain"
    )


class ChatMessageResponse(BaseModel):
    """Response from sending a chat message."""

    conversation_id: str
    stream_url: str
    stream_id: str
    message_id: str


@app.post("/api/v1/chat/message", response_model=ChatMessageResponse, tags=["chat"])
async def send_chat_message(request: ChatMessageRequest):
    """Send a message to the chat agent and get streaming response URL."""
    stage = "init"
    try:
        requested_engine = request.engine or (request.metadata or {}).get("engine")
        if not requested_engine:
            requested_engine = "langchain"
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        stage = "check_openai_key"
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if requested_engine not in ("langchain", None) and not openai_api_key:
            # Legacy engine requires key
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing for legacy engine")

        stage = "imports"
        # Lazy imports (avoid cost if failing earlier)
        from src.agents.conversation_storage import ConversationStorageService

        # (Legacy / langchain service imports only to validate availability)
        try:
            if requested_engine == "langchain":
                from src.agents.langchain.legacy_service import LangChainChatService  # noqa: F401
            else:
                pass
        except Exception as imp_err:
            logger.error("Chat engine import failed (%s)", type(imp_err).__name__)
            raise HTTPException(
                status_code=500, detail=public_error_message("Chat engine initialization")
            )

        storage_service = ConversationStorageService()

        stage = "conversation_lookup_or_create"
        if request.conversation_id:
            conversation = await storage_service.get_conversation(request.conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            target_engine = requested_engine
            current_meta = conversation.metadata or {}
            if current_meta.get("engine") != target_engine:
                # Attempt metadata update
                try:
                    postgres_db = await get_postgres_db()
                    current_meta["engine"] = target_engine
                    await postgres_db.execute(
                        "UPDATE conversations SET metadata = $1, updated_at = $2 WHERE id = $3",
                        json.dumps(current_meta),
                        datetime.now(),
                        conversation.id,
                    )
                    conversation.metadata = current_meta
                except Exception as meta_err:
                    logger.warning(
                        "Metadata engine update failed conversation=%s (%s)",
                        conversation.id,
                        type(meta_err).__name__,
                    )
        else:
            conversation = await storage_service.create_conversation(
                user_id=request.user_id,
                metadata={**(request.metadata or {}), "engine": requested_engine},
            )

        stage = "add_user_message"
        user_msg = await storage_service.add_message(
            conversation_id=conversation.id, message_type="user", content=request.message
        )

        stage = "create_stream_session"
        stream_id = await storage_service.create_stream_session(
            conversation_id=conversation.id, current_message_id=user_msg.id, expires_in_minutes=60
        )

        stage = "maybe_placeholder"
        if (request.engine or (conversation.metadata or {}).get("engine")) == "langchain":
            try:
                await storage_service.add_message(
                    conversation_id=conversation.id,
                    message_type="assistant",
                    content="",
                    metadata={"engine": "langchain", "status": "pending"},
                )
            except Exception as placeholder_err:
                logger.warning(
                    "Assistant placeholder create failed (%s)",
                    type(placeholder_err).__name__,
                )

        stage = "response"
        return ChatMessageResponse(
            conversation_id=str(conversation.id),
            stream_url=f"/api/v1/chat/stream/{stream_id}",
            stream_id=stream_id,
            message_id=str(user_msg.id),
        )

    except HTTPException as http_e:
        # If detail is a plain string, wrap with stage field for consistency
        if isinstance(http_e.detail, str):
            raise HTTPException(
                status_code=http_e.status_code, detail={"error": http_e.detail, "stage": stage}
            )
        raise
    except Exception as e:
        logger.error("Chat message failed at stage=%s (%s)", stage, type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "chat_message_failed",
                "stage": stage,
                "message": public_error_message("Chat message"),
            },
        )


@app.get("/api/v1/chat/stream/{stream_id}", tags=["chat"])
async def chat_stream(
    stream_id: str, trace: int = Query(0, description="Include trace events if 1")
):
    """SSE endpoint for streaming chat responses."""
    from datetime import datetime

    from fastapi.responses import StreamingResponse

    from src.agents.conversation_storage import ConversationStorageService

    async def event_stream():
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")

            storage_service = ConversationStorageService()

            # Get stream session
            session = await storage_service.get_stream_session(stream_id)
            if not session:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Stream session not found or expired'})}\n\n"
                return

            # Get the conversation and recent messages for context
            conversation, messages = await storage_service.get_conversation_context(
                session["conversation_id"],
                max_messages=10,  # Get more messages for conversation context
            )

            # Find the last user message (might not be the very last if there's a placeholder)
            user_message = None
            for msg in reversed(messages):
                if msg.message_type == "user":
                    user_message = msg
                    break

            if not user_message:
                yield f"data: {json.dumps({'type': 'error', 'content': 'No user message found'})}\n\n"
                return

            engine = (conversation.metadata or {}).get("engine", "langchain")
            if engine == "langchain":
                # Check if we should use modern service
                from src.agents.langchain.service_selector import get_chat_service

                service = get_chat_service()
                # Find existing latest assistant placeholder if any
                assistant_message_id = None
                try:
                    conv_msgs = await storage_service.get_conversation_messages(
                        conversation.id, limit=8
                    )
                    for m in reversed(conv_msgs):
                        if (
                            m.message_type == "assistant"
                            and m.metadata.get("engine") == "langchain"
                        ):
                            assistant_message_id = m.id
                            break
                except Exception as e:
                    logger.warning(
                        "Could not retrieve assistant placeholder (%s)",
                        type(e).__name__,
                    )

                # If trace requested, perform retrieval once for context preview
                if trace == 1:
                    try:
                        from src.agents.langchain.chains.retrieval import RetrievalChain

                        retr = RetrievalChain()
                        retrieval_result = await retr.ainvoke({"query": messages[-1].content})
                        preview = {
                            "blocks": retrieval_result.get("context_blocks", []),
                            "entities": [
                                e.get("name")
                                for e in retrieval_result.get("raw", {}).get("entities", [])[:6]
                                if isinstance(e, dict)
                            ],
                        }
                        yield f"data: {json.dumps({'type': 'trace', 'retrieval_preview': preview})}\n\n"
                    except Exception as e:
                        logger.warning("Retrieval preview failed (%s)", type(e).__name__)
                        yield f"data: {json.dumps({'type': 'trace', 'error': public_error_message('Retrieval preview')})}\n\n"

                # Format conversation history for the service
                conversation_history = []
                for msg in messages:
                    # Include all messages before the current user message
                    if msg.id == user_message.id:
                        break
                    # Skip empty placeholder messages
                    if msg.message_type == "assistant" and not msg.content:
                        continue
                    history_entry = {
                        "role": "assistant" if msg.message_type == "assistant" else "user",
                        "content": msg.content,
                    }
                    # Include tool context for assistant messages
                    if msg.message_type == "assistant" and msg.tools_used:
                        history_entry["tools_used"] = msg.tools_used
                    conversation_history.append(history_entry)

                buffer = ""
                async for event in service.stream_chat(user_message.content, conversation_history):
                    etype = event.get("type")
                    if etype == "token":
                        buffer += event.get("content", "")
                        if assistant_message_id and len(buffer) % 40 < len(
                            event.get("content", "")
                        ):
                            await storage_service.update_message(
                                assistant_message_id, content=buffer
                            )
                    elif etype == "final":
                        if assistant_message_id:
                            meta = {
                                "engine": "langchain",
                                "route": event.get("route"),
                                "confidence": event.get("confidence"),
                            }
                            for key in ("plan", "narrative", "story_development"):
                                if key in event:
                                    meta[key] = event[key]
                            # Get content from answer field (all routes should have it now)
                            content = event.get("answer") or buffer
                            # Store structured data in metadata if present
                            if "story_development" in event:
                                meta["story_development"] = event["story_development"]

                            # Extract tool calls if present (from modern service)
                            tools_used = None
                            if event.get("tool_calls"):
                                tools_used = event["tool_calls"]

                            await storage_service.update_message(
                                assistant_message_id,
                                content=content,
                                metadata=meta,
                                tools_used=tools_used,
                            )
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                if not openai_api_key:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'OpenAI API key not configured'})}\n\n"
                    return
                # Legacy streaming agent path
                # Create streaming chat agent with proper pydantic-ai streaming
                # Use localhost:8003 since we're inside the container
                from src.agents.lore_chat_agent_streaming import StreamingLoreChatAgent

                chat_agent = StreamingLoreChatAgent(
                    openai_api_key, api_base_url="http://localhost:8003"
                )
                async for event in chat_agent.stream_chat(user_message.content):
                    yield f"data: {json.dumps(event)}\n\n"

            # Update stream status to completed
            await storage_service.update_stream_status(stream_id, "completed")

        except Exception as e:
            logger.error("Stream error (%s)", type(e).__name__)
            error_event = {
                "type": "error",
                "content": public_error_message("Chat stream"),
                "timestamp": datetime.now().isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"

            # Update stream status to error
            try:
                await storage_service.update_stream_status(stream_id, "error")
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # CORS headers are handled by Apache reverse proxy
        },
    )


@app.get("/api/v1/chat/conversations", tags=["chat"])
async def list_conversations(
    user_id: str | None = Query(None, description="Filter by user ID"),
    limit: int = Query(50, description="Maximum number of conversations", ge=1, le=100),
    offset: int = Query(0, description="Number of conversations to skip", ge=0),
):
    """List conversations with pagination."""
    try:
        from src.agents.conversation_storage import ConversationStorageService

        storage_service = ConversationStorageService()
        conversations = await storage_service.list_conversations(
            user_id=user_id, limit=limit, offset=offset
        )

        return {"conversations": [conv.to_dict() for conv in conversations]}

    except Exception as e:
        logger.error("Failed to list conversations (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Conversation listing"))


@app.get("/api/v1/chat/conversations/{conversation_id}", tags=["chat"])
async def get_conversation_history(
    conversation_id: str,
    limit: int = Query(100, description="Maximum number of messages", ge=1, le=200),
    offset: int = Query(0, description="Number of messages to skip", ge=0),
):
    """Get conversation history with messages."""
    try:
        from src.agents.conversation_storage import ConversationStorageService

        storage_service = ConversationStorageService()

        # Get conversation details
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get messages
        messages = await storage_service.get_conversation_messages(
            conversation_id=conversation_id, limit=limit, offset=offset
        )

        return {
            "conversation": conversation.to_dict(),
            "messages": [msg.to_dict() for msg in messages],
        }

    except Exception as e:
        logger.error("Failed to get conversation (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Conversation retrieval"))


@app.delete("/api/v1/chat/conversations/{conversation_id}", tags=["chat"])
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    try:
        from src.agents.conversation_storage import ConversationStorageService

        storage_service = ConversationStorageService()

        # Check if conversation exists
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Delete conversation
        await storage_service.delete_conversation(conversation_id)

        return {"message": "Conversation deleted successfully"}

    except Exception as e:
        logger.error("Failed to delete conversation (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Conversation deletion"))


@app.post("/api/v1/chat/cleanup", tags=["chat"])
async def cleanup_expired_streams():
    """Clean up expired stream sessions (maintenance endpoint)."""
    try:
        from src.agents.conversation_storage import ConversationStorageService

        storage_service = ConversationStorageService()
        deleted_count = await storage_service.cleanup_expired_streams()

        return {"message": f"Cleaned up {deleted_count} expired stream sessions"}

    except Exception as e:
        logger.error("Failed to cleanup expired streams (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail=public_error_message("Stream cleanup"))


# ============================================
# Run the application
# ============================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )
