-- Durable controls identified by the full canon ingestion run.
-- This migration is additive, preserves every attempt ledger row, and stores
-- only content fingerprints and content-free quality evidence.

-- ---------------------------------------------------------------------------
-- Content-addressed chunk manifests and incremental episode retirement.
-- ---------------------------------------------------------------------------

ALTER TABLE episodes
    ADD COLUMN chunk_profile_fingerprint TEXT,
    ADD COLUMN chunk_manifest_fingerprint TEXT,
    ADD COLUMN content_fingerprint TEXT,
    ADD COLUMN content_role TEXT NOT NULL DEFAULT 'world_lore',
    ADD COLUMN content_role_policy TEXT NOT NULL DEFAULT 'include_all_v1',
    ADD COLUMN graph_extraction_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN retired_at TIMESTAMPTZ,
    ADD COLUMN retirement_reason_code TEXT;

UPDATE episodes
SET content_fingerprint = graph_sync_source_fingerprint(text)
WHERE content_fingerprint IS NULL;

ALTER TABLE episodes
    ALTER COLUMN content_fingerprint SET NOT NULL,
    ADD CONSTRAINT episodes_content_fingerprint_check CHECK (
        content_fingerprint ~ '^sha256:v1:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT episodes_chunk_profile_fingerprint_check CHECK (
        chunk_profile_fingerprint IS NULL
        OR chunk_profile_fingerprint ~ '^chunk-profile:sha256:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT episodes_chunk_manifest_fingerprint_check CHECK (
        chunk_manifest_fingerprint IS NULL
        OR chunk_manifest_fingerprint ~ '^chunk-manifest:sha256:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT episodes_content_role_check CHECK (
        content_role IN (
            'world_lore',
            'runtime_contract',
            'presentation_guidance',
            'schema_guidance',
            'migration_guidance',
            'mixed'
        )
    ),
    ADD CONSTRAINT episodes_content_role_policy_check CHECK (
        content_role_policy IN ('include_all_v1', 'exclude_non_lore_v1')
    ),
    ADD CONSTRAINT episodes_retirement_check CHECK (
        (
            retired_at IS NULL
            AND retirement_reason_code IS NULL
        )
        OR (
            retired_at IS NOT NULL
            AND retirement_reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
            AND embedding IS NULL
        )
    );

CREATE TABLE document_chunk_manifests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES lore_documents(id) ON DELETE RESTRICT,
    document_source_fingerprint TEXT NOT NULL,
    chunk_profile_fingerprint TEXT NOT NULL,
    content_role_policy TEXT NOT NULL,
    manifest_fingerprint TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    predecessor_id UUID REFERENCES document_chunk_manifests(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT document_chunk_manifests_source_check CHECK (
        document_source_fingerprint ~ '^sha256:v1:[0-9a-f]{64}$'
    ),
    CONSTRAINT document_chunk_manifests_profile_check CHECK (
        chunk_profile_fingerprint ~ '^chunk-profile:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT document_chunk_manifests_policy_check CHECK (
        content_role_policy IN ('include_all_v1', 'exclude_non_lore_v1')
    ),
    CONSTRAINT document_chunk_manifests_fingerprint_check CHECK (
        manifest_fingerprint ~ '^chunk-manifest:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT document_chunk_manifests_count_check CHECK (chunk_count >= 0),
    CONSTRAINT document_chunk_manifests_identity_unique UNIQUE (
        document_id,
        manifest_fingerprint
    )
);

CREATE TABLE document_chunk_manifest_items (
    manifest_id UUID NOT NULL
        REFERENCES document_chunk_manifests(id) ON DELETE RESTRICT,
    episode_index INTEGER NOT NULL,
    content_fingerprint TEXT NOT NULL,
    content_role TEXT NOT NULL,
    graph_extraction_eligible BOOLEAN NOT NULL,
    PRIMARY KEY (manifest_id, episode_index),
    CONSTRAINT document_chunk_manifest_items_index_check CHECK (episode_index >= 0),
    CONSTRAINT document_chunk_manifest_items_fingerprint_check CHECK (
        content_fingerprint ~ '^sha256:v1:[0-9a-f]{64}$'
    ),
    CONSTRAINT document_chunk_manifest_items_role_check CHECK (
        content_role IN (
            'world_lore',
            'runtime_contract',
            'presentation_guidance',
            'schema_guidance',
            'migration_guidance',
            'mixed'
        )
    )
);

ALTER TABLE lore_documents
    ADD COLUMN active_chunk_manifest_id UUID
        REFERENCES document_chunk_manifests(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX document_chunk_manifests_id_document_unique
    ON document_chunk_manifests(id, document_id);

ALTER TABLE episodes
    ADD COLUMN chunk_manifest_id UUID,
    ADD CONSTRAINT episodes_chunk_manifest_fk
        FOREIGN KEY (chunk_manifest_id, document_id)
        REFERENCES document_chunk_manifests(id, document_id)
        ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION lore_documents_validate_active_chunk_manifest()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.active_chunk_manifest_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM document_chunk_manifests AS manifest
        WHERE manifest.id = NEW.active_chunk_manifest_id
          AND manifest.document_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'active chunk manifest belongs to another document';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lore_documents_active_chunk_manifest_guard
    BEFORE INSERT OR UPDATE OF active_chunk_manifest_id ON lore_documents
    FOR EACH ROW EXECUTE FUNCTION lore_documents_validate_active_chunk_manifest();

CREATE TABLE episode_lifecycle_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    manifest_id UUID REFERENCES document_chunk_manifests(id) ON DELETE RESTRICT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT episode_lifecycle_events_type_check CHECK (
        event_type IN ('activated', 'retired')
    ),
    CONSTRAINT episode_lifecycle_events_reason_check CHECK (
        reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
    )
);

CREATE INDEX episode_lifecycle_events_episode_recorded
    ON episode_lifecycle_events(episode_id, recorded_at, id);

CREATE OR REPLACE FUNCTION full_run_reject_ledger_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'full-run evidence rows are append-only';
END;
$$;

CREATE TRIGGER document_chunk_manifests_append_only
    BEFORE UPDATE OR DELETE ON document_chunk_manifests
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TRIGGER document_chunk_manifest_items_append_only
    BEFORE UPDATE OR DELETE ON document_chunk_manifest_items
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TRIGGER episode_lifecycle_events_append_only
    BEFORE UPDATE OR DELETE ON episode_lifecycle_events
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE OR REPLACE FUNCTION episode_retirement_normalize()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.content_fingerprint := graph_sync_source_fingerprint(NEW.text);
    IF NEW.retired_at IS NOT NULL THEN
        NEW.embedding := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER episodes_normalize_retirement
    BEFORE INSERT OR UPDATE OF text, retired_at ON episodes
    FOR EACH ROW EXECUTE FUNCTION episode_retirement_normalize();

-- ---------------------------------------------------------------------------
-- Queue operation, priority, and database-level single-writer enforcement.
-- ---------------------------------------------------------------------------

ALTER TABLE graph_sync_jobs
    ADD COLUMN desired_operation TEXT NOT NULL DEFAULT 'sync',
    ADD COLUMN priority SMALLINT NOT NULL DEFAULT 0;

ALTER TABLE graph_sync_attempts
    ADD COLUMN operation TEXT NOT NULL DEFAULT 'sync',
    ADD CONSTRAINT graph_sync_attempts_operation_check CHECK (
        operation IN ('sync', 'retire')
    );

ALTER TABLE graph_sync_jobs
    DROP CONSTRAINT graph_sync_jobs_state_check,
    DROP CONSTRAINT graph_sync_jobs_verified_check,
    ADD CONSTRAINT graph_sync_jobs_state_check CHECK (
        state IN ('pending', 'leased', 'retry_wait', 'quarantined', 'synced', 'retired')
    ),
    ADD CONSTRAINT graph_sync_jobs_operation_check CHECK (
        desired_operation IN ('sync', 'retire')
    ),
    ADD CONSTRAINT graph_sync_jobs_priority_check CHECK (
        priority BETWEEN -100 AND 100
    ),
    ADD CONSTRAINT graph_sync_jobs_verified_check CHECK (
        (
            state IN ('synced', 'retired')
            AND verified_source_fingerprint IS NOT NULL
            AND verified_sync_profile_fingerprint IS NOT NULL
            AND verified_at IS NOT NULL
        )
        OR (
            state NOT IN ('synced', 'retired')
            AND verified_source_fingerprint IS NULL
            AND verified_sync_profile_fingerprint IS NULL
            AND verified_at IS NULL
        )
    ),
    ADD CONSTRAINT graph_sync_jobs_terminal_operation_check CHECK (
        state <> 'synced' OR desired_operation = 'sync'
    ),
    ADD CONSTRAINT graph_sync_jobs_retired_operation_check CHECK (
        state <> 'retired' OR desired_operation = 'retire'
    );

CREATE UNIQUE INDEX graph_sync_single_active_lease
    ON graph_sync_jobs ((TRUE))
    WHERE state = 'leased';

CREATE TABLE graph_sync_priority_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    episode_id UUID NOT NULL REFERENCES graph_sync_jobs(episode_id) ON DELETE RESTRICT,
    previous_priority SMALLINT NOT NULL,
    new_priority SMALLINT NOT NULL,
    reason_code TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_priority_events_previous_check CHECK (
        previous_priority BETWEEN -100 AND 100
    ),
    CONSTRAINT graph_sync_priority_events_new_check CHECK (
        new_priority BETWEEN -100 AND 100
    ),
    CONSTRAINT graph_sync_priority_events_changed_check CHECK (
        previous_priority <> new_priority
    ),
    CONSTRAINT graph_sync_priority_events_reason_check CHECK (
        reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
    )
);

CREATE TRIGGER graph_sync_priority_events_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_priority_events
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE OR REPLACE FUNCTION graph_sync_guard_attempt_owner()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    run_owner TEXT;
    job_operation TEXT;
BEGIN
    SELECT worker_id
    INTO run_owner
    FROM graph_sync_runs
    WHERE id = NEW.run_id
      AND state = 'running';

    IF NOT FOUND OR run_owner IS DISTINCT FROM NEW.lease_owner THEN
        RAISE EXCEPTION 'graph sync attempt does not match the active run owner';
    END IF;

    SELECT desired_operation
    INTO job_operation
    FROM graph_sync_jobs
    WHERE episode_id = NEW.episode_id;

    IF NOT FOUND OR job_operation IS DISTINCT FROM NEW.operation THEN
        RAISE EXCEPTION 'graph sync attempt operation does not match its job';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_attempts_owner_guard
    BEFORE INSERT ON graph_sync_attempts
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_attempt_owner();

ALTER TABLE graph_sync_attempt_results
    DROP CONSTRAINT graph_sync_attempt_results_outcome_check,
    DROP CONSTRAINT graph_sync_attempt_results_degraded_check,
    DROP CONSTRAINT graph_sync_attempt_results_failure_required_check,
    ADD CONSTRAINT graph_sync_attempt_results_outcome_check CHECK (
        outcome IN (
            'primary_success',
            'fallback_success',
            'degraded_success',
            'retire_success',
            'retry_wait',
            'quarantined',
            'paused_systemic',
            'cancelled',
            'shutdown'
        )
    ),
    ADD CONSTRAINT graph_sync_attempt_results_degraded_check CHECK (
        degraded = (outcome IN ('fallback_success', 'degraded_success'))
    ),
    ADD CONSTRAINT graph_sync_attempt_results_failure_required_check CHECK (
        (
            outcome IN (
                'primary_success',
                'fallback_success',
                'degraded_success',
                'retire_success'
            )
            AND failure_class IS NULL
        )
        OR (
            outcome NOT IN (
                'primary_success',
                'fallback_success',
                'degraded_success',
                'retire_success'
            )
            AND failure_class IS NOT NULL
        )
    );

CREATE OR REPLACE FUNCTION graph_sync_guard_attempt_result()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    observed_provider_calls INTEGER;
    completed_provider_calls INTEGER;
BEGIN
    PERFORM 1
    FROM graph_sync_attempts
    WHERE id = NEW.attempt_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'graph sync attempt does not exist';
    END IF;

    SELECT count(*)
    INTO observed_provider_calls
    FROM graph_sync_provider_call_intents
    WHERE attempt_id = NEW.attempt_id;

    IF NEW.provider_call_count <> observed_provider_calls THEN
        RAISE EXCEPTION 'attempt result provider-call count does not match intent ledger';
    END IF;

    IF NEW.outcome IN (
        'primary_success',
        'fallback_success',
        'degraded_success',
        'retire_success'
    ) THEN
        SELECT count(*)
        INTO completed_provider_calls
        FROM graph_sync_provider_calls
        WHERE attempt_id = NEW.attempt_id;

        IF completed_provider_calls <> observed_provider_calls THEN
            RAISE EXCEPTION 'successful attempt has incomplete provider calls';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION graph_sync_guard_relationship_quality()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    attempt_result graph_sync_attempt_results%ROWTYPE;
BEGIN
    SELECT *
    INTO attempt_result
    FROM graph_sync_attempt_results
    WHERE attempt_id = NEW.attempt_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'graph sync attempt result does not exist';
    END IF;

    IF attempt_result.outcome NOT IN (
        'primary_success',
        'fallback_success',
        'degraded_success'
    ) THEN
        RAISE EXCEPTION 'relationship quality requires a successful attempt result';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM graph_sync_attempts AS attempt
        JOIN graph_sync_jobs AS job
          ON job.episode_id = attempt.episode_id
        WHERE attempt.id = NEW.attempt_id
          AND job.state = 'leased'
          AND job.last_attempt_id = attempt.id
          AND job.lease_token = attempt.lease_token
          AND job.lease_owner = attempt.lease_owner
    ) THEN
        RAISE EXCEPTION 'relationship quality requires the current leased attempt';
    END IF;

    IF attempt_result.proposed_edge_count
            IS DISTINCT FROM NEW.proposed_edge_count
       OR attempt_result.accepted_edge_count
            IS DISTINCT FROM NEW.accepted_edge_count
       OR attempt_result.rejected_edge_count
            IS DISTINCT FROM NEW.rejected_edge_count THEN
        RAISE EXCEPTION 'relationship quality does not match attempt graph counts';
    END IF;

    RETURN NEW;
END;
$$;

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

CREATE OR REPLACE FUNCTION graph_sync_refresh_source_job()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_fingerprint TEXT;
    desired_sync_profile TEXT;
    desired_graph_operation TEXT;
    managed_profile BOOLEAN := FALSE;
BEGIN
    source_fingerprint := graph_sync_source_fingerprint(NEW.text);
    desired_graph_operation := CASE
        WHEN NEW.retired_at IS NOT NULL OR NEW.graph_extraction_eligible IS FALSE
            THEN 'retire'
        ELSE 'sync'
    END;

    SELECT rebuild.target_sync_profile_fingerprint
    INTO desired_sync_profile
    FROM graph_rebuild_operations AS rebuild
    WHERE rebuild.state NOT IN ('completed', 'aborted')
    ORDER BY rebuild.created_at
    LIMIT 1;
    managed_profile := FOUND;

    IF desired_sync_profile IS NULL THEN
        SELECT profile.sync_profile_fingerprint
        INTO desired_sync_profile
        FROM graph_sync_profile_state AS profile
        WHERE profile.scope = 'graphiti';
        managed_profile := FOUND;
    END IF;
    desired_sync_profile := COALESCE(desired_sync_profile, 'legacy:unversioned');

    INSERT INTO graph_sync_jobs (
        episode_id,
        desired_source_fingerprint,
        desired_operation,
        state,
        sync_profile_fingerprint,
        verified_source_fingerprint,
        verified_sync_profile_fingerprint,
        verified_at
    )
    VALUES (
        NEW.id,
        source_fingerprint,
        desired_graph_operation,
        CASE
            WHEN desired_graph_operation = 'sync'
                 AND NOT managed_profile
                 AND NEW.graphiti_synced IS TRUE THEN 'synced'
            ELSE 'pending'
        END,
        desired_sync_profile,
        CASE
            WHEN desired_graph_operation = 'sync'
                 AND NOT managed_profile
                 AND NEW.graphiti_synced IS TRUE THEN source_fingerprint
            ELSE NULL
        END,
        CASE
            WHEN desired_graph_operation = 'sync'
                 AND NOT managed_profile
                 AND NEW.graphiti_synced IS TRUE THEN desired_sync_profile
            ELSE NULL
        END,
        CASE
            WHEN desired_graph_operation = 'sync'
                 AND NOT managed_profile
                 AND NEW.graphiti_synced IS TRUE THEN COALESCE(
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
        desired_operation = EXCLUDED.desired_operation,
        state = 'pending',
        attempt_budget_count = 0,
        retry_generation = graph_sync_jobs.retry_generation + 1,
        next_attempt_at = NULL,
        lease_owner = NULL,
        lease_token = NULL,
        lease_expires_at = NULL,
        last_error_class = NULL,
        last_error_code = NULL,
        last_error_summary = NULL,
        sync_profile_fingerprint = desired_sync_profile,
        verified_source_fingerprint = NULL,
        verified_sync_profile_fingerprint = NULL,
        verified_at = NULL
    WHERE graph_sync_jobs.desired_source_fingerprint
              IS DISTINCT FROM EXCLUDED.desired_source_fingerprint
       OR graph_sync_jobs.desired_operation
              IS DISTINCT FROM EXCLUDED.desired_operation;

    RETURN NEW;
END;
$$;

DROP TRIGGER episodes_refresh_graph_sync_job ON episodes;
CREATE TRIGGER episodes_refresh_graph_sync_job
    AFTER INSERT OR UPDATE OF text, retired_at, graph_extraction_eligible ON episodes
    FOR EACH ROW EXECUTE FUNCTION graph_sync_refresh_source_job();

-- ---------------------------------------------------------------------------
-- First-class operator pause and append-only run events.
-- ---------------------------------------------------------------------------

ALTER TABLE graph_sync_runs
    ADD COLUMN operator_pause_reason_code TEXT,
    ADD COLUMN operator_paused_at TIMESTAMPTZ;

ALTER TABLE graph_sync_runs
    DROP CONSTRAINT graph_sync_runs_state_check,
    ADD CONSTRAINT graph_sync_runs_state_check CHECK (
        state IN ('running', 'draining', 'paused_systemic', 'paused_operator', 'stopped')
    ),
    ADD CONSTRAINT graph_sync_runs_operator_pause_check CHECK (
        (
            state = 'paused_operator'
            AND operator_pause_reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
            AND operator_paused_at IS NOT NULL
        )
        OR (
            state <> 'paused_operator'
            AND operator_pause_reason_code IS NULL
            AND operator_paused_at IS NULL
        )
    );

CREATE TABLE graph_sync_run_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES graph_sync_runs(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_run_events_type_check CHECK (
        event_type IN ('operator_paused', 'operator_resumed')
    ),
    CONSTRAINT graph_sync_run_events_reason_check CHECK (
        reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
    )
);

CREATE TRIGGER graph_sync_run_events_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_run_events
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

-- ---------------------------------------------------------------------------
-- Explicit terminal abort evidence for incomplete graph rebuilds.
-- ---------------------------------------------------------------------------

ALTER TABLE graph_rebuild_operations
    ADD COLUMN abort_reason_code TEXT,
    ADD COLUMN aborted_at TIMESTAMPTZ;

ALTER TABLE graph_rebuild_operations
    DROP CONSTRAINT graph_rebuild_operations_state_check,
    DROP CONSTRAINT graph_rebuild_operations_clear_check,
    DROP CONSTRAINT graph_rebuild_operations_timestamp_check,
    ADD CONSTRAINT graph_rebuild_operations_state_check CHECK (
        state IN (
            'jobs_requeued',
            'ready',
            'running',
            'awaiting_audit',
            'completed',
            'aborted'
        )
    ),
    ADD CONSTRAINT graph_rebuild_operations_clear_check CHECK (
        (
            graph_cleared_at IS NULL
            AND state IN ('jobs_requeued', 'aborted')
            AND ready_job_count IS NULL
            AND cleared_node_count IS NULL
            AND cleared_relationship_count IS NULL
            AND post_clear_audit_fingerprint IS NULL
        )
        OR (
            graph_cleared_at IS NOT NULL
            AND state <> 'jobs_requeued'
            AND ready_job_count IS NOT NULL
            AND cleared_node_count IS NOT NULL
            AND cleared_relationship_count IS NOT NULL
            AND post_clear_audit_fingerprint IS NOT NULL
        )
    ),
    ADD CONSTRAINT graph_rebuild_operations_abort_check CHECK (
        (
            state = 'aborted'
            AND abort_reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
            AND aborted_at IS NOT NULL
        )
        OR (
            state <> 'aborted'
            AND abort_reason_code IS NULL
            AND aborted_at IS NULL
        )
    ),
    ADD CONSTRAINT graph_rebuild_operations_timestamp_check CHECK (
        updated_at >= created_at
        AND backup_created_at >= created_at - interval '24 hours'
        AND backup_created_at <= created_at + interval '5 minutes'
        AND (graph_cleared_at IS NULL OR graph_cleared_at >= created_at)
        AND (completed_at IS NULL OR completed_at >= graph_cleared_at)
        AND (aborted_at IS NULL OR aborted_at >= created_at)
    );

DROP INDEX graph_rebuild_operations_one_active;
CREATE UNIQUE INDEX graph_rebuild_operations_one_active
    ON graph_rebuild_operations ((TRUE))
    WHERE state NOT IN ('completed', 'aborted');

CREATE TABLE graph_rebuild_abort_events (
    rebuild_operation_id UUID PRIMARY KEY
        REFERENCES graph_rebuild_operations(id) ON DELETE RESTRICT,
    prior_state TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    remaining_job_count BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_rebuild_abort_events_state_check CHECK (
        prior_state IN ('jobs_requeued', 'ready', 'running', 'awaiting_audit')
    ),
    CONSTRAINT graph_rebuild_abort_events_reason_check CHECK (
        reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    CONSTRAINT graph_rebuild_abort_events_count_check CHECK (
        remaining_job_count >= 0
    )
);

CREATE OR REPLACE FUNCTION graph_rebuild_validate_abort_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    operation graph_rebuild_operations%ROWTYPE;
BEGIN
    SELECT rebuild.*
    INTO operation
    FROM graph_rebuild_operations AS rebuild
    WHERE rebuild.id = NEW.rebuild_operation_id;

    IF NOT FOUND
       OR operation.state <> 'aborted'
       OR operation.abort_reason_code IS DISTINCT FROM NEW.reason_code
       OR NEW.recorded_at < operation.created_at
       OR NEW.recorded_at > clock_timestamp() + interval '5 minutes' THEN
        RAISE EXCEPTION 'graph rebuild abort event does not match terminal operation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_rebuild_abort_events_guard
    BEFORE INSERT ON graph_rebuild_abort_events
    FOR EACH ROW EXECUTE FUNCTION graph_rebuild_validate_abort_event();

CREATE TRIGGER graph_rebuild_abort_events_append_only
    BEFORE UPDATE OR DELETE ON graph_rebuild_abort_events
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE OR REPLACE FUNCTION graph_rebuild_validate_operation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'graph rebuild operations cannot be deleted';
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.target_sync_profile_fingerprint
            IS DISTINCT FROM OLD.target_sync_profile_fingerprint
       OR NEW.target_embedding_profile_fingerprint
            IS DISTINCT FROM OLD.target_embedding_profile_fingerprint
       OR NEW.backup_reference IS DISTINCT FROM OLD.backup_reference
       OR NEW.backup_created_at IS DISTINCT FROM OLD.backup_created_at
       OR NEW.pre_audit_fingerprint IS DISTINCT FROM OLD.pre_audit_fingerprint
       OR NEW.pre_postgres_episode_count IS DISTINCT FROM OLD.pre_postgres_episode_count
       OR NEW.pre_neo4j_node_count IS DISTINCT FROM OLD.pre_neo4j_node_count
       OR NEW.pre_neo4j_relationship_count
            IS DISTINCT FROM OLD.pre_neo4j_relationship_count
       OR NEW.initial_requeued_job_count IS DISTINCT FROM OLD.initial_requeued_job_count
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'graph rebuild operation identity is immutable';
    END IF;

    IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
        NEW.state = 'aborted'
        OR (OLD.state = 'jobs_requeued' AND NEW.state IN ('ready', 'awaiting_audit'))
        OR (OLD.state = 'ready' AND NEW.state = 'running')
        OR (OLD.state = 'running' AND NEW.state IN ('ready', 'awaiting_audit'))
        OR (OLD.state = 'awaiting_audit' AND NEW.state IN ('running', 'completed'))
    ) THEN
        RAISE EXCEPTION 'invalid graph rebuild state transition';
    END IF;

    IF NEW.run_count IS DISTINCT FROM OLD.run_count AND NOT (
        OLD.state IN ('ready', 'awaiting_audit')
        AND NEW.state = 'running'
        AND NEW.run_count = OLD.run_count + 1
    ) THEN
        RAISE EXCEPTION 'graph rebuild run count can advance only when a run starts';
    END IF;
    IF NEW.state = 'running'
       AND OLD.state <> 'running'
       AND NEW.run_count <> OLD.run_count + 1 THEN
        RAISE EXCEPTION 'graph rebuild run start must advance the run count';
    END IF;

    IF OLD.state <> 'jobs_requeued' AND (
        NEW.ready_job_count IS DISTINCT FROM OLD.ready_job_count
        OR NEW.cleared_node_count IS DISTINCT FROM OLD.cleared_node_count
        OR NEW.cleared_relationship_count IS DISTINCT FROM OLD.cleared_relationship_count
        OR NEW.post_clear_audit_fingerprint
            IS DISTINCT FROM OLD.post_clear_audit_fingerprint
        OR NEW.graph_cleared_at IS DISTINCT FROM OLD.graph_cleared_at
    ) THEN
        RAISE EXCEPTION 'graph rebuild clear evidence is immutable';
    END IF;

    IF NEW.state = 'aborted' AND OLD.state <> 'aborted' THEN
        IF NEW.abort_reason_code IS NULL OR NEW.aborted_at IS NULL THEN
            RAISE EXCEPTION 'aborted graph rebuild requires terminal evidence';
        END IF;
    ELSIF NEW.abort_reason_code IS DISTINCT FROM OLD.abort_reason_code
          OR NEW.aborted_at IS DISTINCT FROM OLD.aborted_at THEN
        RAISE EXCEPTION 'graph rebuild abort evidence is immutable';
    END IF;

    IF OLD.state IN ('completed', 'aborted') THEN
        RAISE EXCEPTION 'terminal graph rebuild operations are immutable';
    END IF;

    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Entity-stage response evidence and semantic-audit snapshots.
-- ---------------------------------------------------------------------------

CREATE TABLE graph_sync_entity_stage_quality (
    attempt_id UUID PRIMARY KEY
        REFERENCES graph_sync_attempt_results(attempt_id) ON DELETE RESTRICT,
    policy TEXT NOT NULL,
    dedupe_expected_count INTEGER NOT NULL,
    dedupe_returned_count INTEGER NOT NULL,
    dedupe_missing_count INTEGER NOT NULL,
    dedupe_duplicate_id_count INTEGER NOT NULL,
    dedupe_out_of_range_count INTEGER NOT NULL,
    dedupe_invalid_candidate_count INTEGER NOT NULL,
    summary_expected_count INTEGER NOT NULL,
    summary_returned_count INTEGER NOT NULL,
    summary_missing_count INTEGER NOT NULL,
    summary_unknown_count INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_entity_stage_quality_policy_check CHECK (
        policy IN ('observe_v1', 'strict_v1')
    ),
    CONSTRAINT graph_sync_entity_stage_quality_counts_check CHECK (
        dedupe_expected_count >= 0
        AND dedupe_returned_count >= 0
        AND dedupe_missing_count >= 0
        AND dedupe_duplicate_id_count >= 0
        AND dedupe_out_of_range_count >= 0
        AND dedupe_invalid_candidate_count >= 0
        AND summary_expected_count >= 0
        AND summary_returned_count >= 0
        AND summary_missing_count >= 0
        AND summary_unknown_count >= 0
    )
);

CREATE OR REPLACE FUNCTION graph_sync_guard_entity_stage_quality()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    attempt_outcome TEXT;
BEGIN
    SELECT outcome
    INTO attempt_outcome
    FROM graph_sync_attempt_results
    WHERE attempt_id = NEW.attempt_id;

    IF NOT FOUND OR attempt_outcome = 'retire_success' THEN
        RAISE EXCEPTION 'entity-stage quality requires an extraction attempt result';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_entity_stage_quality_guard
    BEFORE INSERT ON graph_sync_entity_stage_quality
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_entity_stage_quality();

CREATE TRIGGER graph_sync_entity_stage_quality_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_entity_stage_quality
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TABLE graph_semantic_audit_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES graph_sync_runs(id) ON DELETE RESTRICT,
    report_fingerprint TEXT NOT NULL UNIQUE,
    normalization_policy TEXT NOT NULL,
    status TEXT NOT NULL,
    counts JSONB NOT NULL,
    rates_percent JSONB NOT NULL,
    entity_stage_quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_semantic_audit_snapshots_fingerprint_check CHECK (
        report_fingerprint ~ '^semantic-audit:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT graph_semantic_audit_snapshots_status_check CHECK (
        status IN ('clean', 'review_required')
    )
);

CREATE TABLE graph_semantic_audit_findings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id UUID NOT NULL
        REFERENCES graph_semantic_audit_snapshots(id) ON DELETE RESTRICT,
    category TEXT NOT NULL,
    entity_uuid TEXT,
    episode_id UUID,
    group_fingerprint TEXT,
    CONSTRAINT graph_semantic_audit_findings_category_check CHECK (
        category ~ '^[a-z][a-z0-9_]{0,127}$'
    ),
    CONSTRAINT graph_semantic_audit_findings_group_check CHECK (
        group_fingerprint IS NULL
        OR group_fingerprint ~ '^semantic-group:sha256:[0-9a-f]{64}$'
    )
);

CREATE UNIQUE INDEX graph_semantic_audit_findings_identity
    ON graph_semantic_audit_findings (
        snapshot_id,
        category,
        COALESCE(entity_uuid, ''),
        COALESCE(episode_id::text, ''),
        COALESCE(group_fingerprint, '')
    );

CREATE TABLE graph_entity_observations (
    snapshot_id UUID NOT NULL
        REFERENCES graph_semantic_audit_snapshots(id) ON DELETE RESTRICT,
    entity_uuid TEXT NOT NULL,
    name_fingerprint TEXT NOT NULL,
    type_fingerprint TEXT NOT NULL,
    entity_types TEXT[] NOT NULL,
    linked_episode_count INTEGER NOT NULL,
    PRIMARY KEY (snapshot_id, entity_uuid),
    CONSTRAINT graph_entity_observations_name_check CHECK (
        name_fingerprint ~ '^entity-name:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT graph_entity_observations_type_check CHECK (
        type_fingerprint ~ '^entity-types:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT graph_entity_observations_count_check CHECK (
        linked_episode_count >= 0
    )
);

CREATE TABLE graph_entity_transitions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    previous_snapshot_id UUID NOT NULL
        REFERENCES graph_semantic_audit_snapshots(id) ON DELETE RESTRICT,
    snapshot_id UUID NOT NULL
        REFERENCES graph_semantic_audit_snapshots(id) ON DELETE RESTRICT,
    entity_uuid TEXT NOT NULL,
    transition_type TEXT NOT NULL,
    previous_name_fingerprint TEXT,
    name_fingerprint TEXT,
    previous_type_fingerprint TEXT,
    type_fingerprint TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_entity_transitions_type_check CHECK (
        transition_type IN ('created', 'removed', 'name_changed', 'types_changed')
    ),
    CONSTRAINT graph_entity_transitions_snapshot_check CHECK (
        previous_snapshot_id <> snapshot_id
    )
);

CREATE UNIQUE INDEX graph_entity_transitions_identity
    ON graph_entity_transitions (
        previous_snapshot_id,
        snapshot_id,
        entity_uuid,
        transition_type
    );

CREATE TRIGGER graph_semantic_audit_snapshots_append_only
    BEFORE UPDATE OR DELETE ON graph_semantic_audit_snapshots
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TRIGGER graph_semantic_audit_findings_append_only
    BEFORE UPDATE OR DELETE ON graph_semantic_audit_findings
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TRIGGER graph_entity_observations_append_only
    BEFORE UPDATE OR DELETE ON graph_entity_observations
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

CREATE TRIGGER graph_entity_transitions_append_only
    BEFORE UPDATE OR DELETE ON graph_entity_transitions
    FOR EACH ROW EXECUTE FUNCTION full_run_reject_ledger_mutation();

COMMENT ON TABLE document_chunk_manifests IS
    'Content-addressed expected chunk sets for deterministic document reconciliation';
COMMENT ON TABLE episode_lifecycle_events IS
    'Append-only activation and retirement evidence for durable episodes';
COMMENT ON TABLE graph_sync_priority_events IS
    'Audited operator changes to durable graph queue priority';
COMMENT ON TABLE graph_sync_entity_stage_quality IS
    'Content-free dedupe and summary response completeness evidence per attempt';
COMMENT ON TABLE graph_semantic_audit_snapshots IS
    'Persisted aggregate semantic audit checkpoints without source text';
COMMENT ON TABLE graph_entity_transitions IS
    'Snapshot-observed entity identity and type transitions';
