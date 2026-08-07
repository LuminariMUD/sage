-- Add profile-isolated, dimension-flexible shadow embedding storage and an
-- append-only provider-request ledger. This migration never copies, replaces,
-- or activates vectors in episodes.embedding.

CREATE TABLE IF NOT EXISTS embedding_shadow_spaces (
    profile_fingerprint TEXT PRIMARY KEY
        REFERENCES embedding_profiles(fingerprint) ON DELETE RESTRICT,
    semantic_index TEXT NOT NULL DEFAULT 'episodes',
    dimensions INTEGER NOT NULL,
    distance_metric TEXT NOT NULL,
    index_name TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'registered',
    ready_source_snapshot_fingerprint TEXT,
    ready_episode_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    ready_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    CONSTRAINT embedding_shadow_spaces_profile_dimensions_unique
        UNIQUE (profile_fingerprint, dimensions),
    CONSTRAINT embedding_shadow_spaces_profile_fingerprint_check CHECK (
        profile_fingerprint ~ '^embedding:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT embedding_shadow_spaces_semantic_index_check CHECK (
        semantic_index = 'episodes'
    ),
    CONSTRAINT embedding_shadow_spaces_dimensions_check CHECK (
        dimensions BETWEEN 1 AND 65536
    ),
    CONSTRAINT embedding_shadow_spaces_distance_metric_check CHECK (
        distance_metric = 'cosine'
    ),
    CONSTRAINT embedding_shadow_spaces_index_name_check CHECK (
        index_name ~ '^[a-z][a-z0-9_]{0,62}$'
    ),
    CONSTRAINT embedding_shadow_spaces_state_check CHECK (
        state IN ('registered', 'backfilling', 'indexing', 'ready', 'failed', 'retired')
    ),
    CONSTRAINT embedding_shadow_spaces_snapshot_check CHECK (
        ready_source_snapshot_fingerprint IS NULL
        OR ready_source_snapshot_fingerprint ~ '^source-snapshot:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT embedding_shadow_spaces_ready_check CHECK (
        (
            state = 'ready'
            AND ready_source_snapshot_fingerprint IS NOT NULL
            AND ready_episode_count >= 0
            AND ready_at IS NOT NULL
        )
        OR (
            state <> 'ready'
            AND ready_source_snapshot_fingerprint IS NULL
            AND ready_episode_count IS NULL
            AND ready_at IS NULL
        )
    ),
    CONSTRAINT embedding_shadow_spaces_retired_check CHECK (
        (state = 'retired' AND retired_at IS NOT NULL)
        OR (state <> 'retired' AND retired_at IS NULL)
    ),
    CONSTRAINT embedding_shadow_spaces_timestamp_check CHECK (
        updated_at >= created_at
        AND (ready_at IS NULL OR ready_at >= created_at)
        AND (retired_at IS NULL OR retired_at >= created_at)
    )
);

CREATE TABLE IF NOT EXISTS embedding_shadow_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_fingerprint TEXT NOT NULL
        REFERENCES embedding_shadow_spaces(profile_fingerprint) ON DELETE RESTRICT,
    state TEXT NOT NULL DEFAULT 'running',
    target_source_snapshot_fingerprint TEXT NOT NULL,
    target_episode_count INTEGER NOT NULL,
    provider_request_limit INTEGER NOT NULL,
    provider_requests_reserved INTEGER NOT NULL DEFAULT 0,
    provider_requests_succeeded INTEGER NOT NULL DEFAULT 0,
    stored_episode_count INTEGER NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(18, 8),
    failure_type TEXT,
    failure_code TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT embedding_shadow_runs_id_profile_unique
        UNIQUE (id, profile_fingerprint),
    CONSTRAINT embedding_shadow_runs_state_check CHECK (
        state IN ('running', 'stopped', 'completed', 'failed')
    ),
    CONSTRAINT embedding_shadow_runs_snapshot_check CHECK (
        target_source_snapshot_fingerprint ~ '^source-snapshot:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT embedding_shadow_runs_counts_check CHECK (
        target_episode_count >= 0
        AND provider_request_limit BETWEEN 1 AND 100
        AND provider_requests_reserved BETWEEN 0 AND provider_request_limit
        AND provider_requests_succeeded BETWEEN 0 AND provider_requests_reserved
        AND stored_episode_count BETWEEN 0 AND target_episode_count
        AND input_tokens >= 0
        AND total_tokens >= input_tokens
        AND (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0)
    ),
    CONSTRAINT embedding_shadow_runs_failure_check CHECK (
        (failure_type IS NULL OR failure_type ~ '^[A-Za-z][A-Za-z0-9_.]{0,127}$')
        AND (failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_]{0,63}$')
    ),
    CONSTRAINT embedding_shadow_runs_finished_check CHECK (
        (state = 'running' AND finished_at IS NULL)
        OR (state <> 'running' AND finished_at IS NOT NULL)
    ),
    CONSTRAINT embedding_shadow_runs_timestamp_check CHECK (
        updated_at >= started_at
        AND (finished_at IS NULL OR finished_at >= started_at)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS embedding_shadow_runs_one_running
    ON embedding_shadow_runs(profile_fingerprint)
    WHERE state = 'running';

CREATE TABLE IF NOT EXISTS embedding_shadow_batches (
    run_id UUID NOT NULL,
    profile_fingerprint TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'reserved',
    episode_count INTEGER NOT NULL,
    latency_ms INTEGER,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(18, 8),
    actual_model TEXT,
    failure_type TEXT,
    failure_code TEXT,
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (run_id, ordinal),
    CONSTRAINT embedding_shadow_batches_run_profile_unique
        UNIQUE (run_id, ordinal, profile_fingerprint),
    CONSTRAINT embedding_shadow_batches_run_fk
        FOREIGN KEY (run_id, profile_fingerprint)
        REFERENCES embedding_shadow_runs(id, profile_fingerprint) ON DELETE RESTRICT,
    CONSTRAINT embedding_shadow_batches_ordinal_check CHECK (ordinal >= 1),
    CONSTRAINT embedding_shadow_batches_state_check CHECK (
        state IN ('reserved', 'succeeded', 'failed', 'source_changed', 'abandoned')
    ),
    CONSTRAINT embedding_shadow_batches_counts_check CHECK (
        episode_count BETWEEN 1 AND 2048
        AND (latency_ms IS NULL OR latency_ms >= 0)
        AND input_tokens >= 0
        AND total_tokens >= input_tokens
        AND (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0)
    ),
    CONSTRAINT embedding_shadow_batches_model_check CHECK (
        actual_model IS NULL
        OR (
            length(actual_model) BETWEEN 1 AND 255
            AND actual_model !~ '[[:cntrl:]]'
        )
    ),
    CONSTRAINT embedding_shadow_batches_failure_check CHECK (
        (failure_type IS NULL OR failure_type ~ '^[A-Za-z][A-Za-z0-9_.]{0,127}$')
        AND (failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_]{0,63}$')
    ),
    CONSTRAINT embedding_shadow_batches_completed_check CHECK (
        (state = 'reserved' AND completed_at IS NULL)
        OR (state <> 'reserved' AND completed_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS embedding_shadow_batch_items (
    run_id UUID NOT NULL,
    batch_ordinal INTEGER NOT NULL,
    position INTEGER NOT NULL,
    episode_id UUID NOT NULL,
    source_fingerprint TEXT NOT NULL,
    PRIMARY KEY (run_id, batch_ordinal, episode_id),
    CONSTRAINT embedding_shadow_batch_items_position_unique
        UNIQUE (run_id, batch_ordinal, position),
    CONSTRAINT embedding_shadow_batch_items_batch_fk
        FOREIGN KEY (run_id, batch_ordinal)
        REFERENCES embedding_shadow_batches(run_id, ordinal) ON DELETE RESTRICT,
    CONSTRAINT embedding_shadow_batch_items_position_check CHECK (
        position BETWEEN 0 AND 2047
    ),
    CONSTRAINT embedding_shadow_batch_items_source_check CHECK (
        source_fingerprint ~ '^sha256:v1:[0-9a-f]{64}$'
    )
);

CREATE TABLE IF NOT EXISTS episode_embedding_shadows (
    profile_fingerprint TEXT NOT NULL,
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    source_fingerprint TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding vector NOT NULL,
    run_id UUID NOT NULL,
    batch_ordinal INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (profile_fingerprint, episode_id),
    CONSTRAINT episode_embedding_shadows_space_fk
        FOREIGN KEY (profile_fingerprint, dimensions)
        REFERENCES embedding_shadow_spaces(profile_fingerprint, dimensions)
        ON DELETE RESTRICT,
    CONSTRAINT episode_embedding_shadows_batch_fk
        FOREIGN KEY (run_id, batch_ordinal, profile_fingerprint)
        REFERENCES embedding_shadow_batches(run_id, ordinal, profile_fingerprint)
        ON DELETE RESTRICT,
    CONSTRAINT episode_embedding_shadows_source_check CHECK (
        source_fingerprint ~ '^sha256:v1:[0-9a-f]{64}$'
    ),
    CONSTRAINT episode_embedding_shadows_dimensions_check CHECK (
        dimensions BETWEEN 1 AND 65536
        AND vector_dims(embedding) = dimensions
    ),
    CONSTRAINT episode_embedding_shadows_nonzero_check CHECK (
        vector_norm(embedding) > 0
    )
);

CREATE INDEX IF NOT EXISTS episode_embedding_shadows_profile_source
    ON episode_embedding_shadows(profile_fingerprint, source_fingerprint);

CREATE INDEX IF NOT EXISTS embedding_shadow_batch_items_episode
    ON embedding_shadow_batch_items(episode_id);

CREATE OR REPLACE FUNCTION embedding_shadow_space_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    profile_dimensions INTEGER;
    profile_distance_metric TEXT;
BEGIN
    SELECT dimensions, distance_metric
    INTO profile_dimensions, profile_distance_metric
    FROM embedding_profiles
    WHERE fingerprint = NEW.profile_fingerprint;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'embedding shadow profile does not exist';
    END IF;
    IF profile_dimensions IS DISTINCT FROM NEW.dimensions THEN
        RAISE EXCEPTION 'embedding shadow dimension does not match profile';
    END IF;
    IF profile_distance_metric IS DISTINCT FROM NEW.distance_metric THEN
        RAISE EXCEPTION 'embedding shadow distance metric does not match profile';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.profile_fingerprint IS DISTINCT FROM OLD.profile_fingerprint
        OR NEW.semantic_index IS DISTINCT FROM OLD.semantic_index
        OR NEW.dimensions IS DISTINCT FROM OLD.dimensions
        OR NEW.distance_metric IS DISTINCT FROM OLD.distance_metric
        OR NEW.index_name IS DISTINCT FROM OLD.index_name
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'embedding shadow identity is immutable';
    END IF;

    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS embedding_shadow_spaces_validate ON embedding_shadow_spaces;
CREATE TRIGGER embedding_shadow_spaces_validate
    BEFORE INSERT OR UPDATE ON embedding_shadow_spaces
    FOR EACH ROW EXECUTE FUNCTION embedding_shadow_space_validate();

CREATE OR REPLACE FUNCTION embedding_shadow_batch_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'embedding shadow batch evidence is append-only';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.state <> 'reserved' OR NEW.state = 'reserved' THEN
            RAISE EXCEPTION 'embedding shadow batch outcome is immutable';
        END IF;
        IF NEW.run_id IS DISTINCT FROM OLD.run_id
           OR NEW.profile_fingerprint IS DISTINCT FROM OLD.profile_fingerprint
           OR NEW.ordinal IS DISTINCT FROM OLD.ordinal
           OR NEW.episode_count IS DISTINCT FROM OLD.episode_count
           OR NEW.reserved_at IS DISTINCT FROM OLD.reserved_at THEN
            RAISE EXCEPTION 'embedding shadow batch identity is immutable';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS embedding_shadow_batches_validate ON embedding_shadow_batches;
CREATE TRIGGER embedding_shadow_batches_validate
    BEFORE UPDATE OR DELETE ON embedding_shadow_batches
    FOR EACH ROW EXECUTE FUNCTION embedding_shadow_batch_validate();

CREATE OR REPLACE FUNCTION embedding_shadow_batch_item_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'embedding shadow batch item evidence is immutable';
END;
$$;

DROP TRIGGER IF EXISTS embedding_shadow_batch_items_validate ON embedding_shadow_batch_items;
CREATE TRIGGER embedding_shadow_batch_items_validate
    BEFORE UPDATE OR DELETE ON embedding_shadow_batch_items
    FOR EACH ROW EXECUTE FUNCTION embedding_shadow_batch_item_validate();

COMMENT ON TABLE embedding_shadow_spaces IS
    'Profile-isolated candidate vector spaces that never overwrite the active episode column';
COMMENT ON TABLE embedding_shadow_runs IS
    'Resumable shadow backfill invocations with bounded aggregate usage and no source text';
COMMENT ON TABLE embedding_shadow_batches IS
    'Provider requests reserved before inference and finalized once with sanitized outcomes';
COMMENT ON TABLE embedding_shadow_batch_items IS
    'Content-free episode/source identities pinned to each reserved provider request';
COMMENT ON TABLE episode_embedding_shadows IS
    'Candidate vectors keyed by immutable embedding profile and fenced source revision';
