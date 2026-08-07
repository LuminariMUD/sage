-- PostgreSQL Schema for Luminari Sage
-- Document storage, vector embeddings, and metadata

-- ============================================
-- EXTENSIONS
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- Cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Trigram similarity search
CREATE EXTENSION IF NOT EXISTS "btree_gist";     -- Advanced indexing
CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector for embeddings

-- ============================================
-- ENUMS & CUSTOM TYPES
-- ============================================

CREATE TYPE document_type AS ENUM (
    'codex',           -- Core reference documents (DEITIES, KNIGHTS, etc)
    'chronicle',       -- Historical documents (TIMELINE, AGES)
    'lore_note',       -- World-building notes
    'map_note',        -- Geographic descriptions
    'quest',           -- Quest and adventure content
    'character_bio',   -- Character backstories
    'misc'            -- Other document types
);

CREATE TYPE confidence_level AS ENUM (
    'canonical',      -- 100% confirmed in core lore
    'high',          -- 80-99% confidence
    'medium',        -- 60-79% confidence
    'low',           -- 40-59% confidence
    'speculative'    -- <40% confidence
);

CREATE TYPE validation_status AS ENUM (
    'pending',
    'valid',
    'warning',
    'error',
    'conflict'
);

-- ============================================
-- CORE TABLES
-- ============================================

-- Lore documents (full markdown files)
CREATE TABLE lore_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stable_id VARCHAR(50) UNIQUE NOT NULL,  -- ULID/KSUID for consistency (hash + ulid = ~35 chars)
    title VARCHAR(255) NOT NULL,
    document_type document_type NOT NULL,
    source_file VARCHAR(500) NOT NULL,      -- Original file path
    body_md TEXT NOT NULL,                  -- Full markdown content
    summary TEXT,                            -- AI-generated summary
    canonical BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',            -- Flexible metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    indexed_at TIMESTAMPTZ,                 -- When last processed
    processing_status VARCHAR(20) DEFAULT 'pending',  -- For episode processing pipeline
    processed_at TIMESTAMPTZ,               -- When last processed into episodes

    -- Full-text search
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(body_md, '')), 'C')
    ) STORED
);

-- Document chunks for RAG
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES lore_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,           -- Position in document
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,

    -- Vector embedding (384 dimensions for MiniLM)
    embedding vector(384),
    embedding_model VARCHAR(100) DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',

    -- Entity references (Neo4j stable_ids)
    entity_refs JSONB DEFAULT '[]',         -- [{id, name, confidence}]
    keywords TEXT[] DEFAULT '{}',

    -- Metadata
    confidence confidence_level DEFAULT 'medium',
    canonical BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(document_id, chunk_index)
);

-- Entity mentions in documents (bridges to Neo4j)
CREATE TABLE entity_mentions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    entity_stable_id VARCHAR(50) NOT NULL,  -- Neo4j entity stable_id
    entity_name VARCHAR(255) NOT NULL,      -- As mentioned in text
    entity_type VARCHAR(50),
    span_start INTEGER,                     -- Character position
    span_end INTEGER,
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for entity_mentions
CREATE INDEX idx_entity_mentions_entity ON entity_mentions(entity_stable_id);
CREATE INDEX idx_entity_mentions_chunk ON entity_mentions(chunk_id);

-- Validation results for lore consistency
CREATE TABLE validation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES lore_documents(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    validation_type VARCHAR(100) NOT NULL,
    status validation_status NOT NULL,
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    viability_score INTEGER CHECK (viability_score >= 0 AND viability_score <= 100),
    validated_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(255)
);

-- Indexes for validation_results
CREATE INDEX idx_validation_status ON validation_results(status);
CREATE INDEX idx_validation_document ON validation_results(document_id);

-- Search history and analytics
CREATE TABLE search_queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text TEXT NOT NULL,
    query_embedding vector(384),
    result_count INTEGER,
    top_chunks UUID[],                      -- Array of chunk IDs
    top_entities VARCHAR(50)[],             -- Array of entity stable_ids
    response_time_ms INTEGER,
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    feedback_score INTEGER CHECK (feedback_score >= 1 AND feedback_score <= 5),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hybrid Graph RAG episodes table for PostgreSQL → Graphiti → Neo4j pipeline
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES lore_documents(id) ON DELETE CASCADE,
    episode_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(768),   -- Active application space (Nomic); alternatives use shadows
    graphiti_synced BOOLEAN DEFAULT FALSE,
    graphiti_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Optional fields for compatibility and metadata
    entity_refs JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',

    -- Ensure unique episodes per document
    CONSTRAINT episodes_document_episode_unique UNIQUE(document_id, episode_index)
);

-- Immutable embedding identities. Profile rows intentionally exclude credentials,
-- provider headers, source content, and vector values.
CREATE TABLE embedding_profiles (
    fingerprint TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    endpoint_class TEXT NOT NULL,
    implementation TEXT NOT NULL,
    model TEXT NOT NULL,
    model_revision TEXT,
    dimensions INTEGER NOT NULL,
    output_encoding TEXT NOT NULL,
    storage_type TEXT NOT NULL,
    normalize BOOLEAN NOT NULL,
    distance_metric TEXT NOT NULL,
    input_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT embedding_profiles_fingerprint_check CHECK (
        length(fingerprint) BETWEEN 1 AND 512
        AND fingerprint !~ '[[:cntrl:]]'
    ),
    CONSTRAINT embedding_profiles_provider_check CHECK (
        provider IN ('ollama', 'openrouter', 'openai', 'sentence-transformers')
    ),
    CONSTRAINT embedding_profiles_endpoint_class_check CHECK (
        endpoint_class IN (
            'ollama-http',
            'openai-compatible-http',
            'in-process-sentence-transformers'
        )
    ),
    CONSTRAINT embedding_profiles_dimensions_check CHECK (
        dimensions BETWEEN 1 AND 65536
    ),
    CONSTRAINT embedding_profiles_output_encoding_check CHECK (
        output_encoding IN ('float', 'base64')
    ),
    CONSTRAINT embedding_profiles_storage_type_check CHECK (
        storage_type = 'pgvector-vector-float4'
    ),
    CONSTRAINT embedding_profiles_distance_metric_check CHECK (
        distance_metric = 'cosine'
    )
);

-- One current metadata row per physical vector space. The partial unique index
-- below permits shadow spaces but allows only one active space per semantic index.
CREATE TABLE embedding_index_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    semantic_index TEXT NOT NULL,
    physical_space TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    expected_dimensions INTEGER NOT NULL,
    distance_metric TEXT NOT NULL,
    index_name TEXT NOT NULL,
    index_method TEXT NOT NULL,
    operator_class TEXT NOT NULL,
    state TEXT NOT NULL,
    profile_fingerprint TEXT REFERENCES embedding_profiles(fingerprint) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    activated_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT embedding_index_states_space_unique UNIQUE (semantic_index, physical_space),
    CONSTRAINT embedding_index_states_column_unique UNIQUE (table_name, column_name),
    CONSTRAINT embedding_index_states_identifier_check CHECK (
        semantic_index ~ '^[a-z][a-z0-9_]{0,62}$'
        AND physical_space ~ '^[a-z][a-z0-9_.]{0,126}$'
        AND table_name ~ '^[a-z][a-z0-9_]{0,62}$'
        AND column_name ~ '^[a-z][a-z0-9_]{0,62}$'
        AND index_name ~ '^[a-z][a-z0-9_]{0,62}$'
    ),
    CONSTRAINT embedding_index_states_dimensions_check CHECK (
        expected_dimensions BETWEEN 1 AND 65536
    ),
    CONSTRAINT embedding_index_states_distance_metric_check CHECK (
        distance_metric = 'cosine'
    ),
    CONSTRAINT embedding_index_states_method_check CHECK (
        index_method IN ('ivfflat', 'hnsw')
    ),
    CONSTRAINT embedding_index_states_operator_class_check CHECK (
        operator_class = 'vector_cosine_ops'
    ),
    CONSTRAINT embedding_index_states_state_check CHECK (
        state IN ('unverified', 'building', 'ready', 'active', 'retired', 'failed')
    ),
    CONSTRAINT embedding_index_states_activation_check CHECK (
        (state = 'active' AND profile_fingerprint IS NOT NULL AND activated_at IS NOT NULL)
        OR state <> 'active'
    ),
    CONSTRAINT embedding_index_states_retirement_check CHECK (
        (state = 'retired' AND retired_at IS NOT NULL)
        OR state <> 'retired'
    ),
    CONSTRAINT embedding_index_states_timestamp_check CHECK (
        updated_at >= created_at
        AND (activated_at IS NULL OR activated_at >= created_at)
        AND (retired_at IS NULL OR retired_at >= created_at)
    )
);

CREATE UNIQUE INDEX embedding_index_states_one_active
    ON embedding_index_states(semantic_index)
    WHERE state = 'active';

CREATE INDEX embedding_profiles_model_dimensions
    ON embedding_profiles(provider, model, dimensions);

CREATE OR REPLACE FUNCTION embedding_profile_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'embedding profile records are immutable';
END;
$$;

CREATE TRIGGER embedding_profiles_immutable
    BEFORE UPDATE OR DELETE ON embedding_profiles
    FOR EACH ROW EXECUTE FUNCTION embedding_profile_reject_mutation();

CREATE OR REPLACE FUNCTION embedding_index_state_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    profile_dimensions INTEGER;
    profile_distance_metric TEXT;
BEGIN
    IF NEW.profile_fingerprint IS NOT NULL THEN
        SELECT dimensions, distance_metric
        INTO profile_dimensions, profile_distance_metric
        FROM embedding_profiles
        WHERE fingerprint = NEW.profile_fingerprint;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'embedding profile does not exist';
        END IF;
        IF profile_dimensions IS DISTINCT FROM NEW.expected_dimensions THEN
            RAISE EXCEPTION 'embedding profile dimension does not match index state';
        END IF;
        IF profile_distance_metric IS DISTINCT FROM NEW.distance_metric THEN
            RAISE EXCEPTION 'embedding profile distance metric does not match index state';
        END IF;
    END IF;

    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER embedding_index_states_validate
    BEFORE INSERT OR UPDATE ON embedding_index_states
    FOR EACH ROW EXECUTE FUNCTION embedding_index_state_validate();

-- Physical shape is known, but vector provenance is not inferred from dimensions.
-- An operator must explicitly activate/adopt the application profile after review.
INSERT INTO embedding_index_states (
    semantic_index,
    physical_space,
    table_name,
    column_name,
    expected_dimensions,
    distance_metric,
    index_name,
    index_method,
    operator_class,
    state
)
VALUES (
    'episodes',
    'episodes.embedding',
    'episodes',
    'embedding',
    768,
    'cosine',
    'idx_episodes_embedding',
    'hnsw',
    'vector_cosine_ops',
    'unverified'
);

INSERT INTO embedding_index_states (
    semantic_index,
    physical_space,
    table_name,
    column_name,
    expected_dimensions,
    distance_metric,
    index_name,
    index_method,
    operator_class,
    state,
    retired_at
)
VALUES
    (
        'legacy_chunks',
        'chunks.embedding',
        'chunks',
        'embedding',
        384,
        'cosine',
        'idx_chunks_embedding',
        'ivfflat',
        'vector_cosine_ops',
        'retired',
        statement_timestamp()
    ),
    (
        'legacy_search_queries',
        'search_queries.query_embedding',
        'search_queries',
        'query_embedding',
        384,
        'cosine',
        'idx_search_embedding',
        'ivfflat',
        'vector_cosine_ops',
        'retired',
        statement_timestamp()
    );

-- ============================================
-- DATA QUALITY CONSTRAINTS
-- ============================================

-- Ensure non-empty content
ALTER TABLE chunks ADD CONSTRAINT chunk_text_not_empty CHECK (length(text) > 0);
ALTER TABLE lore_documents ADD CONSTRAINT doc_title_not_empty CHECK (length(title) > 0);
ALTER TABLE lore_documents ADD CONSTRAINT doc_body_not_empty CHECK (length(body_md) > 0);
ALTER TABLE chunks ADD CONSTRAINT chunk_token_positive CHECK (token_count > 0);

-- ============================================
-- INDEXES
-- ============================================

-- Vector similarity search indexes
CREATE INDEX idx_chunks_embedding ON chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX idx_episodes_embedding ON episodes
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Additional indexes for hybrid Graph RAG
CREATE INDEX idx_episodes_document_id ON episodes(document_id);
CREATE INDEX idx_episodes_graphiti_synced ON episodes(graphiti_synced) WHERE graphiti_synced = FALSE;
CREATE INDEX idx_episodes_entity_refs ON episodes USING GIN(entity_refs);

CREATE INDEX idx_search_embedding ON search_queries
USING ivfflat (query_embedding vector_cosine_ops)
WITH (lists = 50);

-- Full-text search indexes
CREATE INDEX idx_documents_search ON lore_documents
USING GIN (search_vector);

CREATE INDEX idx_chunks_text ON chunks
USING GIN (to_tsvector('english', text));

-- JSONB indexes for entity references
CREATE INDEX idx_chunks_entities ON chunks
USING GIN (entity_refs);

CREATE INDEX idx_episodes_entities ON episodes
USING GIN (entity_refs);

-- Performance indexes
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_canonical ON chunks(canonical) WHERE canonical = true;
CREATE INDEX idx_documents_type ON lore_documents(document_type);
CREATE INDEX idx_documents_canonical ON lore_documents(canonical) WHERE canonical = true;

-- ============================================
-- FUNCTIONS
-- ============================================

-- Semantic search function
CREATE OR REPLACE FUNCTION search_chunks(
    query_embedding vector(384),
    limit_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE(
    chunk_id UUID,
    document_id UUID,
    text TEXT,
    similarity FLOAT,
    entities JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id as chunk_id,
        c.document_id,
        c.text,
        1 - (c.embedding <=> query_embedding) as similarity,
        c.entity_refs as entities
    FROM chunks c
    WHERE 1 - (c.embedding <=> query_embedding) > similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Hybrid search combining vector and keyword
CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_embedding vector(384),
    limit_count INTEGER DEFAULT 10,
    vector_weight FLOAT DEFAULT 0.7
)
RETURNS TABLE(
    chunk_id UUID,
    document_id UUID,
    text TEXT,
    combined_score FLOAT,
    vector_similarity FLOAT,
    text_rank FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH vector_results AS (
        SELECT
            c.id,
            c.document_id,
            c.text,
            1 - (c.embedding <=> query_embedding) as similarity
        FROM chunks c
        ORDER BY c.embedding <=> query_embedding
        LIMIT limit_count * 2
    ),
    text_results AS (
        SELECT
            c.id,
            c.document_id,
            c.text,
            ts_rank(to_tsvector('english', c.text),
                   plainto_tsquery('english', query_text)) as rank
        FROM chunks c
        WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', query_text)
        ORDER BY rank DESC
        LIMIT limit_count * 2
    )
    SELECT
        COALESCE(v.id, t.id) as chunk_id,
        COALESCE(v.document_id, t.document_id) as document_id,
        COALESCE(v.text, t.text) as text,
        (COALESCE(v.similarity, 0) * vector_weight +
         COALESCE(t.rank, 0) * (1 - vector_weight)) as combined_score,
        v.similarity as vector_similarity,
        t.rank as text_rank
    FROM vector_results v
    FULL OUTER JOIN text_results t ON v.id = t.id
    ORDER BY combined_score DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_documents_timestamp
    BEFORE UPDATE ON lore_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Episodes table update trigger
CREATE TRIGGER update_episodes_timestamp
    BEFORE UPDATE ON episodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- VIEWS
-- ============================================

-- Canonical content view
CREATE VIEW canonical_content AS
SELECT
    d.id as document_id,
    d.title,
    d.document_type,
    c.id as chunk_id,
    c.text,
    c.entity_refs,
    c.embedding
FROM lore_documents d
JOIN chunks c ON c.document_id = d.id
WHERE d.canonical = true AND c.canonical = true;

-- Entity mention statistics
CREATE VIEW entity_mention_stats AS
SELECT
    entity_stable_id,
    entity_type,
    COUNT(*) as mention_count,
    AVG(confidence) as avg_confidence,
    array_agg(DISTINCT chunk_id) as chunk_ids
FROM entity_mentions
GROUP BY entity_stable_id, entity_type;

-- Document statistics
CREATE VIEW document_stats AS
SELECT
    d.id,
    d.title,
    d.document_type,
    COUNT(DISTINCT c.id) as chunk_count,
    COUNT(DISTINCT em.entity_stable_id) as unique_entities,
    AVG(c.token_count) as avg_chunk_size,
    MAX(c.created_at) as last_indexed
FROM lore_documents d
LEFT JOIN chunks c ON c.document_id = d.id
LEFT JOIN entity_mentions em ON em.chunk_id = c.id
GROUP BY d.id, d.title, d.document_type;

-- ============================================
-- INITIAL DATA
-- ============================================

-- Sample confidence thresholds
INSERT INTO lore_documents (stable_id, title, document_type, source_file, body_md, canonical)
VALUES
    ('01HN3XQGK5NMCSQG7KQHF6P8YB', 'System Configuration', 'misc', 'system/config.md',
     '# System Configuration\nThis document contains system-wide configuration.', false)
ON CONFLICT (stable_id) DO NOTHING;

-- ============================================
-- PERMISSIONS (adjust as needed)
-- ============================================

-- Create read-only role for API queries
CREATE ROLE luminari_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO luminari_reader;

-- Create write role for data pipeline
CREATE ROLE luminari_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO luminari_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO luminari_writer;

-- ============================================
-- VALIDATION SYSTEM TABLES
-- ============================================

-- Create validation_reports table
CREATE TABLE IF NOT EXISTS validation_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id VARCHAR(255) UNIQUE NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Report details
    validation_type VARCHAR(255) NOT NULL,
    scope_description TEXT NOT NULL,
    total_items_checked INTEGER NOT NULL DEFAULT 0,

    -- Summary statistics
    findings_count INTEGER NOT NULL DEFAULT 0,
    severity_counts JSONB NOT NULL DEFAULT '{}',
    category_counts JSONB NOT NULL DEFAULT '{}',

    -- Execution details
    execution_time_seconds DECIMAL(10, 3) NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,

    -- Full markdown report for human review
    markdown_report TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Create validation_findings table
CREATE TABLE IF NOT EXISTS validation_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id VARCHAR(255) UNIQUE NOT NULL,
    report_id UUID NOT NULL REFERENCES validation_reports(id) ON DELETE CASCADE,
    agent_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Finding classification
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    category VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,

    -- Evidence and confidence
    confidence_score DECIMAL(3, 2) NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    confidence_explanation TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]',

    -- Suggested actions
    suggested_action TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority >= 1 AND priority <= 5),

    -- Affected items
    affected_entities JSONB NOT NULL DEFAULT '[]',
    affected_relationships JSONB NOT NULL DEFAULT '[]',

    -- Human review tracking
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewer VARCHAR(255),
    review_timestamp TIMESTAMP WITH TIME ZONE,
    review_action VARCHAR(255),
    review_notes TEXT,

    -- Additional metadata
    metadata JSONB DEFAULT '{}'
);

-- ============================================
-- RELATIONSHIP CORRECTION SYSTEM TABLES
-- ============================================

-- Table to store all relationship corrections with complete backup data
CREATE TABLE IF NOT EXISTS relationship_corrections (
    -- Primary identification
    correction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    validation_report_id UUID REFERENCES validation_reports(id),
    correction_batch_id UUID NOT NULL, -- Groups corrections from single run

    -- Correction metadata
    correction_type TEXT NOT NULL CHECK (correction_type IN ('DEDUPLICATION', 'SEMANTIC_STANDARDIZATION')),
    action TEXT NOT NULL CHECK (action IN ('DELETE', 'UPDATE')),
    confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    agent_reasoning TEXT NOT NULL,

    -- Neo4j relationship identification
    relationship_id TEXT NOT NULL, -- Neo4j elementId
    relationship_type TEXT NOT NULL, -- RELATES_TO or MENTIONS
    source_node_id TEXT NOT NULL, -- Neo4j elementId of source node
    target_node_id TEXT NOT NULL, -- Neo4j elementId of target node
    source_node_name TEXT,
    target_node_name TEXT,
    source_node_labels TEXT[], -- Array of node labels
    target_node_labels TEXT[], -- Array of node labels

    -- Complete relationship backup (JSONB for efficient storage/queries)
    original_properties JSONB NOT NULL, -- ALL properties including embeddings
    new_properties JSONB, -- Updated properties (NULL for deletions)

    -- Semantic type tracking (for easier queries)
    original_semantic_type TEXT,
    new_semantic_type TEXT,
    duplicate_count INTEGER, -- For deduplication: how many duplicates were found

    -- Audit timestamps
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Rollback tracking
    rolled_back BOOLEAN DEFAULT FALSE,
    rollback_at TIMESTAMP WITH TIME ZONE,
    rollback_by TEXT,
    rollback_reason TEXT,

    -- Metadata for extensibility
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================
-- VALIDATION SYSTEM INDEXES
-- ============================================

-- Validation reports indexes
CREATE INDEX IF NOT EXISTS idx_validation_reports_agent_id ON validation_reports(agent_id);
CREATE INDEX IF NOT EXISTS idx_validation_reports_created_at ON validation_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_validation_reports_validation_type ON validation_reports(validation_type);

-- Validation findings indexes
CREATE INDEX IF NOT EXISTS idx_validation_findings_report_id ON validation_findings(report_id);
CREATE INDEX IF NOT EXISTS idx_validation_findings_agent_id ON validation_findings(agent_id);
CREATE INDEX IF NOT EXISTS idx_validation_findings_severity ON validation_findings(severity);
CREATE INDEX IF NOT EXISTS idx_validation_findings_category ON validation_findings(category);
CREATE INDEX IF NOT EXISTS idx_validation_findings_reviewed ON validation_findings(reviewed);
CREATE INDEX IF NOT EXISTS idx_validation_findings_priority ON validation_findings(priority);
CREATE INDEX IF NOT EXISTS idx_validation_findings_created_at ON validation_findings(created_at DESC);

-- GIN indexes for JSONB columns for efficient searching
CREATE INDEX IF NOT EXISTS idx_validation_reports_severity_counts_gin ON validation_reports USING GIN (severity_counts);
CREATE INDEX IF NOT EXISTS idx_validation_reports_category_counts_gin ON validation_reports USING GIN (category_counts);
CREATE INDEX IF NOT EXISTS idx_validation_findings_evidence_gin ON validation_findings USING GIN (evidence);
CREATE INDEX IF NOT EXISTS idx_validation_findings_affected_entities_gin ON validation_findings USING GIN (affected_entities);
CREATE INDEX IF NOT EXISTS idx_validation_findings_affected_relationships_gin ON validation_findings USING GIN (affected_relationships);

-- ============================================
-- CORRECTION SYSTEM INDEXES
-- ============================================

-- Correction system indexes
CREATE INDEX IF NOT EXISTS idx_corrections_report_id ON relationship_corrections(validation_report_id);
CREATE INDEX IF NOT EXISTS idx_corrections_batch_id ON relationship_corrections(correction_batch_id);
CREATE INDEX IF NOT EXISTS idx_corrections_not_rolled_back ON relationship_corrections(rolled_back) WHERE NOT rolled_back;
CREATE INDEX IF NOT EXISTS idx_corrections_type ON relationship_corrections(correction_type);
CREATE INDEX IF NOT EXISTS idx_corrections_relationship_id ON relationship_corrections(relationship_id);
CREATE INDEX IF NOT EXISTS idx_corrections_applied_at ON relationship_corrections(applied_at);

-- Partial index for active corrections
CREATE INDEX IF NOT EXISTS idx_corrections_active ON relationship_corrections(correction_batch_id, applied_at)
    WHERE NOT rolled_back;

-- GIN index for efficient JSONB queries on properties
CREATE INDEX IF NOT EXISTS idx_corrections_original_props ON relationship_corrections USING GIN (original_properties);
CREATE INDEX IF NOT EXISTS idx_corrections_new_props ON relationship_corrections USING GIN (new_properties);

-- ============================================
-- CORRECTION SYSTEM FUNCTIONS
-- ============================================

-- Function to get corrections summary for a batch
CREATE OR REPLACE FUNCTION get_correction_batch_summary(batch_uuid UUID)
RETURNS TABLE (
    total_corrections BIGINT,
    deduplication_count BIGINT,
    standardization_count BIGINT,
    deleted_relationships BIGINT,
    updated_relationships BIGINT,
    rolled_back_count BIGINT,
    avg_confidence NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) as total_corrections,
        COUNT(*) FILTER (WHERE correction_type = 'DEDUPLICATION') as deduplication_count,
        COUNT(*) FILTER (WHERE correction_type = 'SEMANTIC_STANDARDIZATION') as standardization_count,
        COUNT(*) FILTER (WHERE action = 'DELETE') as deleted_relationships,
        COUNT(*) FILTER (WHERE action = 'UPDATE') as updated_relationships,
        COUNT(*) FILTER (WHERE rolled_back = TRUE) as rolled_back_count,
        ROUND(AVG(confidence_score), 3) as avg_confidence
    FROM relationship_corrections
    WHERE correction_batch_id = batch_uuid;
END;
$$ LANGUAGE plpgsql;

-- Function to validate that a correction can be rolled back
CREATE OR REPLACE FUNCTION can_rollback_correction(corr_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    correction_exists BOOLEAN;
    already_rolled_back BOOLEAN;
BEGIN
    SELECT EXISTS(SELECT 1 FROM relationship_corrections WHERE correction_id = corr_id),
           COALESCE((SELECT rolled_back FROM relationship_corrections WHERE correction_id = corr_id), FALSE)
    INTO correction_exists, already_rolled_back;

    RETURN correction_exists AND NOT already_rolled_back;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update correction batch metadata when corrections are added
CREATE OR REPLACE FUNCTION update_correction_batch_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Could add logic here to update batch-level statistics table if needed
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER correction_batch_stats_trigger
    AFTER INSERT ON relationship_corrections
    FOR EACH ROW EXECUTE FUNCTION update_correction_batch_stats();

-- ============================================
-- CORRECTION SYSTEM VIEWS
-- ============================================

-- View for easy querying of active (non-rolled-back) corrections
CREATE OR REPLACE VIEW active_corrections AS
SELECT
    correction_id,
    validation_report_id,
    correction_batch_id,
    correction_type,
    action,
    confidence_score,
    agent_reasoning,
    relationship_id,
    relationship_type,
    source_node_name,
    target_node_name,
    original_semantic_type,
    new_semantic_type,
    duplicate_count,
    applied_at,
    metadata
FROM relationship_corrections
WHERE NOT rolled_back
ORDER BY applied_at DESC;

-- ============================================
-- SYSTEM COMMENTS
-- ============================================

COMMENT ON TABLE validation_reports IS 'Stores validation reports generated by PydanticAI agents for Luminari Sage knowledge graph validation';
COMMENT ON TABLE validation_findings IS 'Stores individual validation findings with audit trails and human review tracking';
COMMENT ON TABLE relationship_corrections IS 'Audit trail for all relationship corrections with complete backup data for rollback';

COMMENT ON COLUMN validation_findings.severity IS 'Severity level: info, warning, error, critical';
COMMENT ON COLUMN validation_findings.priority IS 'Priority level: 1 (highest) to 5 (lowest)';
COMMENT ON COLUMN validation_findings.confidence_score IS 'Confidence score from 0.0 to 1.0 indicating agent certainty';
COMMENT ON COLUMN validation_findings.reviewed IS 'Whether this finding has been reviewed by a human';

COMMENT ON COLUMN relationship_corrections.correction_batch_id IS 'Groups all corrections made in a single validation run';
COMMENT ON COLUMN relationship_corrections.original_properties IS 'Complete Neo4j relationship properties including embeddings before correction';
COMMENT ON COLUMN relationship_corrections.new_properties IS 'Updated properties after correction (NULL for deletions)';
COMMENT ON COLUMN relationship_corrections.duplicate_count IS 'For deduplication corrections: total number of duplicates found';

-- ============================================
-- MAINTENANCE
-- ============================================

-- Vacuum and analyze for optimal performance
-- Run these periodically:
-- VACUUM ANALYZE chunks;
-- VACUUM ANALYZE validation_reports;
-- VACUUM ANALYZE validation_findings;
-- VACUUM ANALYZE relationship_corrections;
-- REINDEX INDEX idx_chunks_embedding;
