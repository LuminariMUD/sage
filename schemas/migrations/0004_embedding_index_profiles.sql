-- Persist embedding identities, inventory physical vector spaces, and restore the
-- supported episode index without claiming provenance for existing vectors.

DO $$
DECLARE
    episode_type TEXT;
    chunk_type TEXT;
    search_query_type TEXT;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
    INTO episode_type
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = to_regclass('episodes')
      AND attribute.attname = 'embedding'
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped;

    SELECT format_type(attribute.atttypid, attribute.atttypmod)
    INTO chunk_type
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = to_regclass('chunks')
      AND attribute.attname = 'embedding'
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped;

    SELECT format_type(attribute.atttypid, attribute.atttypmod)
    INTO search_query_type
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = to_regclass('search_queries')
      AND attribute.attname = 'query_embedding'
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped;

    IF episode_type IS DISTINCT FROM 'vector(768)' THEN
        RAISE EXCEPTION 'episodes.embedding must be vector(768), found %', episode_type;
    END IF;
    IF chunk_type IS DISTINCT FROM 'vector(384)' THEN
        RAISE EXCEPTION 'chunks.embedding must be vector(384), found %', chunk_type;
    END IF;
    IF search_query_type IS DISTINCT FROM 'vector(384)' THEN
        RAISE EXCEPTION 'search_queries.query_embedding must be vector(384), found %',
            search_query_type;
    END IF;
END;
$$;

-- Use HNSW for the active, changing episode corpus instead of inheriting the
-- legacy IVFFlat list/probe tuning used by retired 384-dimensional spaces.
CREATE INDEX IF NOT EXISTS idx_episodes_embedding ON episodes
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE TABLE IF NOT EXISTS embedding_profiles (
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

CREATE TABLE IF NOT EXISTS embedding_index_states (
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

CREATE UNIQUE INDEX IF NOT EXISTS embedding_index_states_one_active
    ON embedding_index_states(semantic_index)
    WHERE state = 'active';

CREATE INDEX IF NOT EXISTS embedding_profiles_model_dimensions
    ON embedding_profiles(provider, model, dimensions);

CREATE OR REPLACE FUNCTION embedding_profile_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'embedding profile records are immutable';
END;
$$;

DROP TRIGGER IF EXISTS embedding_profiles_immutable ON embedding_profiles;
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

DROP TRIGGER IF EXISTS embedding_index_states_validate ON embedding_index_states;
CREATE TRIGGER embedding_index_states_validate
    BEFORE INSERT OR UPDATE ON embedding_index_states
    FOR EACH ROW EXECUTE FUNCTION embedding_index_state_validate();

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
)
ON CONFLICT (semantic_index, physical_space) DO NOTHING;

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
    )
ON CONFLICT (semantic_index, physical_space) DO NOTHING;

COMMENT ON TABLE embedding_profiles IS
    'Immutable secret-free identities for configured embedding vector spaces';
COMMENT ON TABLE embedding_index_states IS
    'Authoritative activation and physical-index metadata for semantic vector spaces';

DO $$
DECLARE
    invalid_episode_index_count BIGINT;
BEGIN
    SELECT count(*)
    INTO invalid_episode_index_count
    FROM pg_index AS index_metadata
    JOIN pg_class AS index_relation
      ON index_relation.oid = index_metadata.indexrelid
    JOIN pg_am AS access_method
      ON access_method.oid = index_relation.relam
    JOIN pg_opclass AS operator_class
      ON operator_class.oid = index_metadata.indclass[0]
    JOIN pg_attribute AS indexed_attribute
      ON indexed_attribute.attrelid = index_metadata.indrelid
     AND indexed_attribute.attnum = index_metadata.indkey[0]
    WHERE index_metadata.indrelid = to_regclass('episodes')
      AND index_relation.relname = 'idx_episodes_embedding'
      AND access_method.amname = 'hnsw'
      AND operator_class.opcname = 'vector_cosine_ops'
      AND indexed_attribute.attname = 'embedding'
      AND index_metadata.indnkeyatts = 1
      AND index_metadata.indisvalid
      AND index_metadata.indisready
      AND COALESCE(index_relation.reloptions, ARRAY[]::TEXT[])
            @> ARRAY['m=16', 'ef_construction=64'];

    IF invalid_episode_index_count <> 1 THEN
        RAISE EXCEPTION 'episode vector index does not match the supported contract';
    END IF;

    IF (
        SELECT count(*)
        FROM embedding_index_states
        WHERE semantic_index = 'episodes'
          AND physical_space = 'episodes.embedding'
          AND expected_dimensions = 768
          AND index_name = 'idx_episodes_embedding'
    ) <> 1 THEN
        RAISE EXCEPTION 'episode embedding index-state seed is invalid';
    END IF;
END;
$$;
