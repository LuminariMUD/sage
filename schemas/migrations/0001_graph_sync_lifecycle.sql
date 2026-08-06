-- Durable PostgreSQL state for the Graphiti ingestion lifecycle.
-- This migration is additive and preserves episodes.graphiti_synced as a
-- compatibility projection. The durable graph_sync_jobs row is authoritative.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION graph_sync_source_fingerprint(content TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT 'sha256:v1:' || encode(digest(content, 'sha256'), 'hex')
$$;

CREATE TABLE graph_sync_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state TEXT NOT NULL DEFAULT 'running',
    worker_id TEXT NOT NULL,
    sync_profile_fingerprint TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    stopped_at TIMESTAMPTZ,
    last_failure_class TEXT,
    last_failure_code TEXT,
    last_failure_summary VARCHAR(512),
    CONSTRAINT graph_sync_runs_state_check CHECK (
        state IN ('running', 'draining', 'paused_systemic', 'stopped')
    ),
    CONSTRAINT graph_sync_runs_failure_class_check CHECK (
        last_failure_class IS NULL OR last_failure_class IN (
            'transport',
            'authentication',
            'authorization',
            'configuration',
            'profile_mismatch',
            'rate_limit',
            'resource_exhaustion',
            'output_limit',
            'malformed_json',
            'schema_validation',
            'graph_validation',
            'persistence',
            'verification',
            'cancellation',
            'shutdown',
            'internal'
        )
    ),
    CONSTRAINT graph_sync_runs_paused_failure_check CHECK (
        state <> 'paused_systemic' OR last_failure_class IS NOT NULL
    ),
    CONSTRAINT graph_sync_runs_stopped_at_check CHECK (
        (state = 'stopped' AND stopped_at IS NOT NULL)
        OR (state <> 'stopped' AND stopped_at IS NULL)
    )
);

CREATE TABLE graph_sync_jobs (
    episode_id UUID PRIMARY KEY REFERENCES episodes(id) ON DELETE RESTRICT,
    desired_source_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    job_attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_attempt_id UUID,
    last_error_class TEXT,
    last_error_code TEXT,
    last_error_summary VARCHAR(512),
    sync_profile_fingerprint TEXT NOT NULL DEFAULT 'legacy:unversioned',
    verified_source_fingerprint TEXT,
    verified_sync_profile_fingerprint TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_jobs_state_check CHECK (
        state IN ('pending', 'leased', 'retry_wait', 'quarantined', 'synced')
    ),
    CONSTRAINT graph_sync_jobs_attempt_count_check CHECK (job_attempt_count >= 0),
    CONSTRAINT graph_sync_jobs_failure_class_check CHECK (
        last_error_class IS NULL OR last_error_class IN (
            'transport',
            'authentication',
            'authorization',
            'configuration',
            'profile_mismatch',
            'rate_limit',
            'resource_exhaustion',
            'output_limit',
            'malformed_json',
            'schema_validation',
            'graph_validation',
            'persistence',
            'verification',
            'cancellation',
            'shutdown',
            'internal'
        )
    ),
    CONSTRAINT graph_sync_jobs_lease_check CHECK (
        (
            state = 'leased'
            AND job_attempt_count > 0
            AND last_attempt_id IS NOT NULL
            AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL
            AND lease_expires_at IS NOT NULL
        )
        OR (
            state <> 'leased'
            AND lease_owner IS NULL
            AND lease_token IS NULL
            AND lease_expires_at IS NULL
        )
    ),
    CONSTRAINT graph_sync_jobs_retry_time_check CHECK (
        (state = 'retry_wait' AND next_attempt_at IS NOT NULL)
        OR (state <> 'retry_wait' AND next_attempt_at IS NULL)
    ),
    CONSTRAINT graph_sync_jobs_verified_check CHECK (
        (
            state = 'synced'
            AND verified_source_fingerprint IS NOT NULL
            AND verified_sync_profile_fingerprint IS NOT NULL
            AND verified_at IS NOT NULL
        )
        OR (
            state <> 'synced'
            AND verified_source_fingerprint IS NULL
            AND verified_sync_profile_fingerprint IS NULL
            AND verified_at IS NULL
        )
    )
);

CREATE TABLE graph_sync_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL REFERENCES graph_sync_jobs(episode_id) ON DELETE RESTRICT,
    run_id UUID NOT NULL REFERENCES graph_sync_runs(id) ON DELETE RESTRICT,
    attempt_number INTEGER NOT NULL,
    lease_token UUID NOT NULL UNIQUE,
    lease_owner TEXT NOT NULL,
    captured_source_fingerprint TEXT NOT NULL,
    sync_profile_fingerprint TEXT NOT NULL,
    route_fingerprint TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_attempts_number_check CHECK (attempt_number > 0),
    CONSTRAINT graph_sync_attempts_episode_number_unique UNIQUE (episode_id, attempt_number)
);

ALTER TABLE graph_sync_jobs
    ADD CONSTRAINT graph_sync_jobs_last_attempt_fk
    FOREIGN KEY (last_attempt_id)
    REFERENCES graph_sync_attempts(id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE graph_sync_attempt_results (
    attempt_id UUID PRIMARY KEY REFERENCES graph_sync_attempts(id) ON DELETE RESTRICT,
    outcome TEXT NOT NULL,
    degraded BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    provider_call_count INTEGER NOT NULL DEFAULT 0,
    prompt_tokens BIGINT,
    completion_tokens BIGINT,
    total_tokens BIGINT,
    proposed_entity_count INTEGER,
    accepted_entity_count INTEGER,
    rejected_entity_count INTEGER,
    proposed_edge_count INTEGER,
    accepted_edge_count INTEGER,
    rejected_edge_count INTEGER,
    failure_class TEXT,
    failure_code TEXT,
    failure_summary VARCHAR(512),
    CONSTRAINT graph_sync_attempt_results_outcome_check CHECK (
        outcome IN (
            'primary_success',
            'fallback_success',
            'retry_wait',
            'quarantined',
            'paused_systemic',
            'cancelled',
            'shutdown'
        )
    ),
    CONSTRAINT graph_sync_attempt_results_degraded_check CHECK (
        degraded = (outcome = 'fallback_success')
    ),
    CONSTRAINT graph_sync_attempt_results_provider_calls_check CHECK (
        provider_call_count >= 0
    ),
    CONSTRAINT graph_sync_attempt_results_token_check CHECK (
        (prompt_tokens IS NULL OR prompt_tokens >= 0)
        AND (completion_tokens IS NULL OR completion_tokens >= 0)
        AND (total_tokens IS NULL OR total_tokens >= 0)
    ),
    CONSTRAINT graph_sync_attempt_results_graph_counts_check CHECK (
        (proposed_entity_count IS NULL OR proposed_entity_count >= 0)
        AND (accepted_entity_count IS NULL OR accepted_entity_count >= 0)
        AND (rejected_entity_count IS NULL OR rejected_entity_count >= 0)
        AND (proposed_edge_count IS NULL OR proposed_edge_count >= 0)
        AND (accepted_edge_count IS NULL OR accepted_edge_count >= 0)
        AND (rejected_edge_count IS NULL OR rejected_edge_count >= 0)
    ),
    CONSTRAINT graph_sync_attempt_results_failure_class_check CHECK (
        failure_class IS NULL OR failure_class IN (
            'transport',
            'authentication',
            'authorization',
            'configuration',
            'profile_mismatch',
            'rate_limit',
            'resource_exhaustion',
            'output_limit',
            'malformed_json',
            'schema_validation',
            'graph_validation',
            'persistence',
            'verification',
            'cancellation',
            'shutdown',
            'internal'
        )
    ),
    CONSTRAINT graph_sync_attempt_results_failure_required_check CHECK (
        (
            outcome IN ('primary_success', 'fallback_success')
            AND failure_class IS NULL
        )
        OR (
            outcome NOT IN ('primary_success', 'fallback_success')
            AND failure_class IS NOT NULL
        )
    )
);

CREATE TABLE graph_sync_provider_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES graph_sync_attempts(id) ON DELETE RESTRICT,
    call_number INTEGER NOT NULL,
    logical_model_attempt INTEGER NOT NULL,
    transport_attempt INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_revision TEXT,
    actual_model TEXT,
    actual_upstream_provider TEXT,
    candidate_fingerprint TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    latency_ms INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    failure_class TEXT,
    failure_code TEXT,
    failure_summary VARCHAR(512),
    prompt_tokens BIGINT,
    completion_tokens BIGINT,
    total_tokens BIGINT,
    CONSTRAINT graph_sync_provider_calls_number_unique UNIQUE (attempt_id, call_number),
    CONSTRAINT graph_sync_provider_calls_number_check CHECK (
        call_number > 0 AND logical_model_attempt > 0 AND transport_attempt > 0
    ),
    CONSTRAINT graph_sync_provider_calls_time_check CHECK (completed_at >= started_at),
    CONSTRAINT graph_sync_provider_calls_latency_check CHECK (latency_ms >= 0),
    CONSTRAINT graph_sync_provider_calls_outcome_check CHECK (
        outcome IN ('success', 'failure', 'cancelled')
    ),
    CONSTRAINT graph_sync_provider_calls_failure_class_check CHECK (
        failure_class IS NULL OR failure_class IN (
            'transport',
            'authentication',
            'authorization',
            'configuration',
            'profile_mismatch',
            'rate_limit',
            'resource_exhaustion',
            'output_limit',
            'malformed_json',
            'schema_validation',
            'graph_validation',
            'persistence',
            'verification',
            'cancellation',
            'shutdown',
            'internal'
        )
    ),
    CONSTRAINT graph_sync_provider_calls_failure_required_check CHECK (
        (outcome = 'success' AND failure_class IS NULL)
        OR (outcome <> 'success' AND failure_class IS NOT NULL)
    ),
    CONSTRAINT graph_sync_provider_calls_token_check CHECK (
        (prompt_tokens IS NULL OR prompt_tokens >= 0)
        AND (completion_tokens IS NULL OR completion_tokens >= 0)
        AND (total_tokens IS NULL OR total_tokens >= 0)
    )
);

CREATE INDEX idx_graph_sync_runs_state ON graph_sync_runs(state, updated_at);
CREATE UNIQUE INDEX idx_graph_sync_runs_one_active
    ON graph_sync_runs ((TRUE))
    WHERE state <> 'stopped';
CREATE INDEX idx_graph_sync_jobs_claim ON graph_sync_jobs(state, next_attempt_at, updated_at)
    WHERE state IN ('pending', 'retry_wait');
CREATE INDEX idx_graph_sync_jobs_lease_expiry ON graph_sync_jobs(lease_expires_at)
    WHERE state = 'leased';
CREATE INDEX idx_graph_sync_jobs_last_error ON graph_sync_jobs(last_error_class)
    WHERE last_error_class IS NOT NULL;
CREATE INDEX idx_graph_sync_attempts_episode ON graph_sync_attempts(episode_id, started_at);
CREATE INDEX idx_graph_sync_attempts_run ON graph_sync_attempts(run_id, started_at);
CREATE INDEX idx_graph_sync_provider_calls_candidate
    ON graph_sync_provider_calls(candidate_fingerprint, started_at);
CREATE INDEX idx_graph_sync_provider_calls_failure
    ON graph_sync_provider_calls(failure_class, started_at)
    WHERE failure_class IS NOT NULL;

CREATE OR REPLACE FUNCTION graph_sync_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_runs_set_updated_at
    BEFORE UPDATE ON graph_sync_runs
    FOR EACH ROW EXECUTE FUNCTION graph_sync_set_updated_at();

CREATE TRIGGER graph_sync_jobs_set_updated_at
    BEFORE UPDATE ON graph_sync_jobs
    FOR EACH ROW EXECUTE FUNCTION graph_sync_set_updated_at();

CREATE OR REPLACE FUNCTION graph_sync_reject_ledger_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; % is not allowed', TG_TABLE_NAME, TG_OP;
END;
$$;

CREATE TRIGGER graph_sync_attempts_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_attempts
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

CREATE TRIGGER graph_sync_attempt_results_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_attempt_results
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

CREATE TRIGGER graph_sync_provider_calls_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_provider_calls
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

INSERT INTO graph_sync_jobs (
    episode_id,
    desired_source_fingerprint,
    state,
    sync_profile_fingerprint,
    verified_source_fingerprint,
    verified_sync_profile_fingerprint,
    verified_at
)
SELECT
    id,
    graph_sync_source_fingerprint(text),
    CASE WHEN graphiti_synced IS TRUE THEN 'synced' ELSE 'pending' END,
    'legacy:unversioned',
    CASE
        WHEN graphiti_synced IS TRUE THEN graph_sync_source_fingerprint(text)
        ELSE NULL
    END,
    CASE WHEN graphiti_synced IS TRUE THEN 'legacy:unversioned' ELSE NULL END,
    CASE
        WHEN graphiti_synced IS TRUE
            THEN COALESCE(graphiti_synced_at, updated_at, created_at, clock_timestamp())
        ELSE NULL
    END
FROM episodes;

CREATE OR REPLACE FUNCTION graph_sync_project_compatibility()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE episodes
    SET graphiti_synced = (NEW.state = 'synced'),
        graphiti_synced_at = CASE WHEN NEW.state = 'synced' THEN NEW.verified_at ELSE NULL END
    WHERE id = NEW.episode_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_jobs_project_compatibility
    AFTER INSERT OR UPDATE OF state, verified_at ON graph_sync_jobs
    FOR EACH ROW EXECUTE FUNCTION graph_sync_project_compatibility();

CREATE OR REPLACE FUNCTION graph_sync_guard_legacy_projection()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_synced BOOLEAN;
    expected_synced_at TIMESTAMPTZ;
BEGIN
    SELECT state = 'synced', verified_at
    INTO expected_synced, expected_synced_at
    FROM graph_sync_jobs
    WHERE episode_id = NEW.id;

    IF FOUND AND (
        NEW.graphiti_synced IS DISTINCT FROM expected_synced
        OR NEW.graphiti_synced_at IS DISTINCT FROM expected_synced_at
    ) THEN
        RAISE EXCEPTION
            'episodes.graphiti_synced is a derived graph_sync_jobs projection';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER episodes_guard_graph_sync_projection
    BEFORE UPDATE OF graphiti_synced, graphiti_synced_at ON episodes
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_legacy_projection();

CREATE OR REPLACE FUNCTION graph_sync_refresh_source_job()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_fingerprint TEXT;
BEGIN
    source_fingerprint := graph_sync_source_fingerprint(NEW.text);

    INSERT INTO graph_sync_jobs (
        episode_id,
        desired_source_fingerprint,
        state,
        sync_profile_fingerprint,
        verified_source_fingerprint,
        verified_sync_profile_fingerprint,
        verified_at
    )
    VALUES (
        NEW.id,
        source_fingerprint,
        CASE WHEN NEW.graphiti_synced IS TRUE THEN 'synced' ELSE 'pending' END,
        'legacy:unversioned',
        CASE WHEN NEW.graphiti_synced IS TRUE THEN source_fingerprint ELSE NULL END,
        CASE WHEN NEW.graphiti_synced IS TRUE THEN 'legacy:unversioned' ELSE NULL END,
        CASE
            WHEN NEW.graphiti_synced IS TRUE
                THEN COALESCE(
                    NEW.graphiti_synced_at,
                    NEW.updated_at,
                    NEW.created_at,
                    clock_timestamp()
                )
            ELSE NULL
        END
    )
    ON CONFLICT (episode_id) DO UPDATE
    SET desired_source_fingerprint = EXCLUDED.desired_source_fingerprint,
        state = 'pending',
        next_attempt_at = NULL,
        lease_owner = NULL,
        lease_token = NULL,
        lease_expires_at = NULL,
        last_error_class = NULL,
        last_error_code = NULL,
        last_error_summary = NULL,
        verified_source_fingerprint = NULL,
        verified_sync_profile_fingerprint = NULL,
        verified_at = NULL
    WHERE graph_sync_jobs.desired_source_fingerprint
        IS DISTINCT FROM EXCLUDED.desired_source_fingerprint;

    RETURN NEW;
END;
$$;

CREATE TRIGGER episodes_refresh_graph_sync_job
    AFTER INSERT OR UPDATE OF text ON episodes
    FOR EACH ROW EXECUTE FUNCTION graph_sync_refresh_source_job();

DO $$
DECLARE
    episode_count BIGINT;
    job_count BIGINT;
    projection_mismatch_count BIGINT;
    fingerprint_mismatch_count BIGINT;
BEGIN
    SELECT count(*) INTO episode_count FROM episodes;
    SELECT count(*) INTO job_count FROM graph_sync_jobs;

    IF episode_count <> job_count THEN
        RAISE EXCEPTION 'graph_sync_jobs seed mismatch: episodes %, jobs %',
            episode_count, job_count;
    END IF;

    SELECT count(*)
    INTO projection_mismatch_count
    FROM episodes AS episode
    JOIN graph_sync_jobs AS job ON job.episode_id = episode.id
    WHERE episode.graphiti_synced IS DISTINCT FROM (job.state = 'synced');

    IF projection_mismatch_count <> 0 THEN
        RAISE EXCEPTION 'graph sync compatibility projection mismatches: %',
            projection_mismatch_count;
    END IF;

    SELECT count(*)
    INTO fingerprint_mismatch_count
    FROM episodes AS episode
    JOIN graph_sync_jobs AS job ON job.episode_id = episode.id
    WHERE job.desired_source_fingerprint
        IS DISTINCT FROM graph_sync_source_fingerprint(episode.text);

    IF fingerprint_mismatch_count <> 0 THEN
        RAISE EXCEPTION 'graph sync source fingerprint mismatches: %',
            fingerprint_mismatch_count;
    END IF;
END;
$$;

COMMENT ON TABLE graph_sync_runs IS
    'Run-level claim circuit for Graphiti workers; never stores prompts or credentials';
COMMENT ON TABLE graph_sync_jobs IS
    'Authoritative durable lifecycle for PostgreSQL episode to Neo4j synchronization';
COMMENT ON TABLE graph_sync_attempts IS
    'Immutable leased-attempt identity and captured source/profile provenance';
COMMENT ON TABLE graph_sync_attempt_results IS
    'Immutable terminal result for one graph sync attempt';
COMMENT ON TABLE graph_sync_provider_calls IS
    'Immutable sanitized provenance for every upstream inference request';
COMMENT ON COLUMN episodes.graphiti_synced IS
    'Deprecated compatibility projection of graph_sync_jobs.state = synced';
