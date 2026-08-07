-- Durable, backup-gated Graphiti rebuild operations and active profile state.

CREATE TABLE graph_rebuild_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state TEXT NOT NULL DEFAULT 'jobs_requeued',
    target_sync_profile_fingerprint TEXT NOT NULL,
    target_embedding_profile_fingerprint TEXT NOT NULL,
    backup_reference TEXT NOT NULL,
    backup_created_at TIMESTAMPTZ NOT NULL,
    pre_audit_fingerprint TEXT NOT NULL,
    pre_postgres_episode_count BIGINT NOT NULL,
    pre_neo4j_node_count BIGINT NOT NULL,
    pre_neo4j_relationship_count BIGINT NOT NULL,
    initial_requeued_job_count BIGINT NOT NULL,
    ready_job_count BIGINT,
    cleared_node_count BIGINT,
    cleared_relationship_count BIGINT,
    post_clear_audit_fingerprint TEXT,
    final_audit_fingerprint TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    graph_cleared_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT graph_rebuild_operations_state_check CHECK (
        state IN ('jobs_requeued', 'ready', 'running', 'awaiting_audit', 'completed')
    ),
    CONSTRAINT graph_rebuild_operations_profile_check CHECK (
        length(target_sync_profile_fingerprint) BETWEEN 1 AND 255
        AND target_sync_profile_fingerprint !~ '[[:cntrl:]]'
        AND length(target_embedding_profile_fingerprint) BETWEEN 1 AND 255
        AND target_embedding_profile_fingerprint !~ '[[:cntrl:]]'
    ),
    CONSTRAINT graph_rebuild_operations_backup_check CHECK (
        backup_reference ~ '^backups/[A-Za-z0-9._/:+-]{1,247}$'
        AND backup_reference !~ '(^|/)[.]{1,2}(/|$)'
        AND backup_reference !~ '//|/$'
    ),
    CONSTRAINT graph_rebuild_operations_audit_check CHECK (
        pre_audit_fingerprint ~ '^graph-audit:sha256:[0-9a-f]{64}$'
        AND (
            post_clear_audit_fingerprint IS NULL
            OR post_clear_audit_fingerprint ~ '^graph-audit:sha256:[0-9a-f]{64}$'
        )
        AND (
            final_audit_fingerprint IS NULL
            OR final_audit_fingerprint ~ '^graph-audit:sha256:[0-9a-f]{64}$'
        )
    ),
    CONSTRAINT graph_rebuild_operations_counts_check CHECK (
        pre_postgres_episode_count >= 0
        AND pre_neo4j_node_count >= 0
        AND pre_neo4j_relationship_count >= 0
        AND initial_requeued_job_count >= 0
        AND (ready_job_count IS NULL OR ready_job_count >= 0)
        AND (cleared_node_count IS NULL OR cleared_node_count >= 0)
        AND (cleared_relationship_count IS NULL OR cleared_relationship_count >= 0)
        AND run_count >= 0
    ),
    CONSTRAINT graph_rebuild_operations_clear_check CHECK (
        (
            state = 'jobs_requeued'
            AND ready_job_count IS NULL
            AND cleared_node_count IS NULL
            AND cleared_relationship_count IS NULL
            AND post_clear_audit_fingerprint IS NULL
            AND graph_cleared_at IS NULL
        )
        OR (
            state <> 'jobs_requeued'
            AND ready_job_count IS NOT NULL
            AND cleared_node_count IS NOT NULL
            AND cleared_relationship_count IS NOT NULL
            AND post_clear_audit_fingerprint IS NOT NULL
            AND graph_cleared_at IS NOT NULL
        )
    ),
    CONSTRAINT graph_rebuild_operations_completion_check CHECK (
        (
            state = 'completed'
            AND final_audit_fingerprint IS NOT NULL
            AND completed_at IS NOT NULL
        )
        OR (
            state <> 'completed'
            AND final_audit_fingerprint IS NULL
            AND completed_at IS NULL
        )
    ),
    CONSTRAINT graph_rebuild_operations_timestamp_check CHECK (
        updated_at >= created_at
        AND backup_created_at >= created_at - interval '24 hours'
        AND backup_created_at <= created_at + interval '5 minutes'
        AND (graph_cleared_at IS NULL OR graph_cleared_at >= created_at)
        AND (completed_at IS NULL OR completed_at >= graph_cleared_at)
    )
);

CREATE UNIQUE INDEX graph_rebuild_operations_one_active
    ON graph_rebuild_operations ((TRUE))
    WHERE state <> 'completed';

CREATE INDEX graph_rebuild_operations_created
    ON graph_rebuild_operations(created_at DESC);

CREATE TABLE graph_sync_profile_state (
    scope TEXT PRIMARY KEY DEFAULT 'graphiti',
    sync_profile_fingerprint TEXT NOT NULL,
    embedding_profile_fingerprint TEXT NOT NULL,
    rebuild_operation_id UUID NOT NULL
        REFERENCES graph_rebuild_operations(id) ON DELETE RESTRICT,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_profile_state_scope_check CHECK (scope = 'graphiti'),
    CONSTRAINT graph_sync_profile_state_profile_check CHECK (
        length(sync_profile_fingerprint) BETWEEN 1 AND 255
        AND sync_profile_fingerprint !~ '[[:cntrl:]]'
        AND length(embedding_profile_fingerprint) BETWEEN 1 AND 255
        AND embedding_profile_fingerprint !~ '[[:cntrl:]]'
    )
);

ALTER TABLE graph_sync_runs
    ADD COLUMN rebuild_operation_id UUID
        REFERENCES graph_rebuild_operations(id) ON DELETE RESTRICT;

CREATE INDEX graph_sync_runs_rebuild_operation
    ON graph_sync_runs(rebuild_operation_id, started_at)
    WHERE rebuild_operation_id IS NOT NULL;

CREATE TABLE graph_rebuild_events (
    rebuild_operation_id UUID NOT NULL
        REFERENCES graph_rebuild_operations(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    run_id UUID REFERENCES graph_sync_runs(id) ON DELETE RESTRICT,
    audit_fingerprint TEXT,
    job_count BIGINT,
    node_count BIGINT,
    relationship_count BIGINT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (rebuild_operation_id, sequence),
    CONSTRAINT graph_rebuild_events_type_check CHECK (
        event_type IN (
            'jobs_requeued',
            'graph_cleared',
            'run_started',
            'run_stopped',
            'final_audit_passed'
        )
    ),
    CONSTRAINT graph_rebuild_events_audit_check CHECK (
        audit_fingerprint IS NULL
        OR audit_fingerprint ~ '^graph-audit:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT graph_rebuild_events_counts_check CHECK (
        sequence > 0
        AND (job_count IS NULL OR job_count >= 0)
        AND (node_count IS NULL OR node_count >= 0)
        AND (relationship_count IS NULL OR relationship_count >= 0)
    ),
    CONSTRAINT graph_rebuild_events_shape_check CHECK (
        (
            event_type IN ('jobs_requeued', 'graph_cleared')
            AND run_id IS NULL
            AND audit_fingerprint IS NOT NULL
            AND job_count IS NOT NULL
            AND node_count IS NOT NULL
            AND relationship_count IS NOT NULL
        )
        OR (
            event_type = 'run_started'
            AND run_id IS NOT NULL
            AND audit_fingerprint IS NULL
            AND job_count IS NULL
            AND node_count IS NULL
            AND relationship_count IS NULL
        )
        OR (
            event_type = 'run_stopped'
            AND run_id IS NOT NULL
            AND audit_fingerprint IS NULL
            AND job_count IS NOT NULL
            AND node_count IS NULL
            AND relationship_count IS NULL
        )
        OR (
            event_type = 'final_audit_passed'
            AND run_id IS NULL
            AND audit_fingerprint IS NOT NULL
            AND job_count IS NOT NULL
            AND node_count IS NULL
            AND relationship_count IS NULL
        )
    )
);

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
        (OLD.state = 'jobs_requeued' AND NEW.state IN ('ready', 'awaiting_audit'))
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

    IF OLD.state = 'completed' THEN
        RAISE EXCEPTION 'completed graph rebuild operations are immutable';
    END IF;

    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_rebuild_operations_validate
    BEFORE UPDATE OR DELETE ON graph_rebuild_operations
    FOR EACH ROW EXECUTE FUNCTION graph_rebuild_validate_operation();

CREATE OR REPLACE FUNCTION graph_sync_profile_state_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    rebuild graph_rebuild_operations%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'active graph sync profile state cannot be deleted';
    END IF;

    SELECT operation.*
    INTO rebuild
    FROM graph_rebuild_operations AS operation
    WHERE operation.id = NEW.rebuild_operation_id
      AND operation.state = 'completed';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'active graph sync profile requires a completed rebuild';
    END IF;
    IF NEW.sync_profile_fingerprint
            IS DISTINCT FROM rebuild.target_sync_profile_fingerprint
       OR NEW.embedding_profile_fingerprint
            IS DISTINCT FROM rebuild.target_embedding_profile_fingerprint THEN
        RAISE EXCEPTION 'active graph sync profile does not match its rebuild';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_profile_state_validate
    BEFORE INSERT OR UPDATE OR DELETE ON graph_sync_profile_state
    FOR EACH ROW EXECUTE FUNCTION graph_sync_profile_state_validate();

CREATE OR REPLACE FUNCTION graph_rebuild_validate_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    operation graph_rebuild_operations%ROWTYPE;
    previous_event graph_rebuild_events%ROWTYPE;
    linked_run graph_sync_runs%ROWTYPE;
    expected_sequence INTEGER;
    existing_run_starts INTEGER;
BEGIN
    SELECT rebuild.*
    INTO operation
    FROM graph_rebuild_operations AS rebuild
    WHERE rebuild.id = NEW.rebuild_operation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'graph rebuild event requires an existing operation';
    END IF;

    SELECT COALESCE(max(sequence), 0) + 1,
           count(*) FILTER (WHERE event_type = 'run_started')
    INTO expected_sequence, existing_run_starts
    FROM graph_rebuild_events
    WHERE rebuild_operation_id = NEW.rebuild_operation_id;
    IF NEW.sequence <> expected_sequence THEN
        RAISE EXCEPTION 'graph rebuild event sequence is not contiguous';
    END IF;
    IF operation.run_count <> existing_run_starts
            + (CASE WHEN NEW.event_type = 'run_started' THEN 1 ELSE 0 END) THEN
        RAISE EXCEPTION 'graph rebuild event run count does not reconcile';
    END IF;
    IF NEW.recorded_at < operation.created_at
       OR NEW.recorded_at > clock_timestamp() + interval '5 minutes' THEN
        RAISE EXCEPTION 'graph rebuild event timestamp is invalid';
    END IF;

    IF NEW.sequence > 1 THEN
        SELECT event.*
        INTO previous_event
        FROM graph_rebuild_events AS event
        WHERE event.rebuild_operation_id = NEW.rebuild_operation_id
          AND event.sequence = NEW.sequence - 1;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'graph rebuild event predecessor is missing';
        END IF;
    END IF;

    IF NEW.event_type = 'jobs_requeued' THEN
        IF NEW.sequence <> 1
           OR operation.state <> 'jobs_requeued'
           OR NEW.audit_fingerprint IS DISTINCT FROM operation.pre_audit_fingerprint
           OR NEW.job_count IS DISTINCT FROM operation.initial_requeued_job_count
           OR NEW.node_count IS DISTINCT FROM operation.pre_neo4j_node_count
           OR NEW.relationship_count
                IS DISTINCT FROM operation.pre_neo4j_relationship_count THEN
            RAISE EXCEPTION 'jobs-requeued event does not match operation state';
        END IF;
    ELSIF NEW.event_type = 'graph_cleared' THEN
        IF previous_event.event_type <> 'jobs_requeued'
           OR operation.state NOT IN ('ready', 'awaiting_audit')
           OR NEW.audit_fingerprint
                IS DISTINCT FROM operation.post_clear_audit_fingerprint
           OR NEW.job_count IS DISTINCT FROM operation.ready_job_count
           OR NEW.node_count <> 0
           OR NEW.relationship_count <> 0 THEN
            RAISE EXCEPTION 'graph-cleared event does not match operation state';
        END IF;
    ELSIF NEW.event_type = 'run_started' THEN
        IF previous_event.event_type NOT IN ('graph_cleared', 'run_stopped')
           OR operation.state <> 'running' THEN
            RAISE EXCEPTION 'run-started event does not match operation state';
        END IF;
    ELSIF NEW.event_type = 'run_stopped' THEN
        IF previous_event.event_type <> 'run_started'
           OR previous_event.run_id IS DISTINCT FROM NEW.run_id
           OR operation.state NOT IN ('ready', 'awaiting_audit') THEN
            RAISE EXCEPTION 'run-stopped event does not match operation state';
        END IF;
    ELSIF NEW.event_type = 'final_audit_passed' THEN
        IF previous_event.event_type NOT IN ('graph_cleared', 'run_stopped')
           OR operation.state <> 'completed'
           OR NEW.audit_fingerprint IS DISTINCT FROM operation.final_audit_fingerprint THEN
            RAISE EXCEPTION 'final-audit event does not match operation state';
        END IF;
    END IF;

    IF NEW.run_id IS NOT NULL THEN
        SELECT run.*
        INTO linked_run
        FROM graph_sync_runs AS run
        WHERE run.id = NEW.run_id;
        IF NOT FOUND
           OR linked_run.rebuild_operation_id IS DISTINCT FROM NEW.rebuild_operation_id
           OR (
               NEW.event_type = 'run_started'
               AND linked_run.state <> 'running'
           )
           OR (
               NEW.event_type = 'run_stopped'
               AND linked_run.state <> 'stopped'
           ) THEN
            RAISE EXCEPTION 'graph rebuild event run does not reconcile';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_rebuild_events_validate
    BEFORE INSERT ON graph_rebuild_events
    FOR EACH ROW EXECUTE FUNCTION graph_rebuild_validate_event();

CREATE TRIGGER graph_rebuild_events_append_only
    BEFORE UPDATE OR DELETE ON graph_rebuild_events
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

CREATE OR REPLACE FUNCTION graph_rebuild_lock_sync_run_statement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(731047850174);
    RETURN NULL;
END;
$$;

-- Acquire the lifecycle lock before PostgreSQL locates or locks any run row.
-- A row-level lock here would invert the order used by rebuild preparation and
-- could deadlock with run stop/pause transitions.
CREATE TRIGGER graph_sync_runs_rebuild_lock
    BEFORE INSERT OR UPDATE ON graph_sync_runs
    FOR EACH STATEMENT EXECUTE FUNCTION graph_rebuild_lock_sync_run_statement();

CREATE OR REPLACE FUNCTION graph_rebuild_guard_sync_run()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    active_rebuild graph_rebuild_operations%ROWTYPE;
BEGIN
    SELECT rebuild.*
    INTO active_rebuild
    FROM graph_rebuild_operations AS rebuild
    WHERE rebuild.state <> 'completed'
    ORDER BY rebuild.created_at
    LIMIT 1
    FOR UPDATE;

    IF FOUND THEN
        IF active_rebuild.state <> 'running' THEN
            RAISE EXCEPTION 'active graph rebuild is not accepting sync runs';
        END IF;
        IF NEW.rebuild_operation_id IS DISTINCT FROM active_rebuild.id THEN
            RAISE EXCEPTION 'sync run must be associated with the active graph rebuild';
        END IF;
        IF NEW.sync_profile_fingerprint
                IS DISTINCT FROM active_rebuild.target_sync_profile_fingerprint THEN
            RAISE EXCEPTION 'sync run profile does not match the active graph rebuild';
        END IF;
    ELSIF NEW.rebuild_operation_id IS NOT NULL THEN
        RAISE EXCEPTION 'sync run references an inactive graph rebuild';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_runs_rebuild_guard
    BEFORE INSERT OR UPDATE OF state, sync_profile_fingerprint, rebuild_operation_id
    ON graph_sync_runs
    FOR EACH ROW EXECUTE FUNCTION graph_rebuild_guard_sync_run();

-- New and revised source rows inherit the current rebuild target, then the last
-- successfully audited graph profile. This prevents legacy-profile jobs from
-- appearing while a rebuild is in progress or after it completes.
CREATE OR REPLACE FUNCTION graph_sync_refresh_source_job()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_fingerprint TEXT;
    desired_sync_profile TEXT;
    managed_profile BOOLEAN := FALSE;
BEGIN
    source_fingerprint := graph_sync_source_fingerprint(NEW.text);

    SELECT rebuild.target_sync_profile_fingerprint
    INTO desired_sync_profile
    FROM graph_rebuild_operations AS rebuild
    WHERE rebuild.state <> 'completed'
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
        state,
        sync_profile_fingerprint,
        verified_source_fingerprint,
        verified_sync_profile_fingerprint,
        verified_at
    )
    VALUES (
        NEW.id,
        source_fingerprint,
        CASE
            WHEN NOT managed_profile AND NEW.graphiti_synced IS TRUE THEN 'synced'
            ELSE 'pending'
        END,
        desired_sync_profile,
        CASE
            WHEN NOT managed_profile AND NEW.graphiti_synced IS TRUE
                THEN source_fingerprint
            ELSE NULL
        END,
        CASE
            WHEN NOT managed_profile AND NEW.graphiti_synced IS TRUE
                THEN desired_sync_profile
            ELSE NULL
        END,
        CASE
            WHEN NOT managed_profile AND NEW.graphiti_synced IS TRUE
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
        IS DISTINCT FROM EXCLUDED.desired_source_fingerprint;

    RETURN NEW;
END;
$$;

COMMENT ON TABLE graph_rebuild_operations IS
    'Crash-recoverable, backup-gated whole-graph rebuild state and profile evidence';
COMMENT ON TABLE graph_rebuild_events IS
    'Append-only content-free event history for graph rebuild transitions';
COMMENT ON TABLE graph_sync_profile_state IS
    'Last graph sync and embedding profile accepted by a clean final audit';
COMMENT ON COLUMN graph_sync_runs.rebuild_operation_id IS
    'Optional rebuild whose pending jobs this durable run is processing';

DO $$
DECLARE
    orphan_job_count BIGINT;
    stale_source_count BIGINT;
BEGIN
    SELECT count(*)
    INTO orphan_job_count
    FROM graph_sync_jobs AS job
    FULL OUTER JOIN episodes AS episode ON episode.id = job.episode_id
    WHERE job.episode_id IS NULL OR episode.id IS NULL;

    IF orphan_job_count <> 0 THEN
        RAISE EXCEPTION 'graph rebuild migration found orphan episode/job rows: %',
            orphan_job_count;
    END IF;

    SELECT count(*)
    INTO stale_source_count
    FROM graph_sync_jobs AS job
    JOIN episodes AS episode ON episode.id = job.episode_id
    WHERE job.desired_source_fingerprint
        IS DISTINCT FROM graph_sync_source_fingerprint(episode.text);

    IF stale_source_count <> 0 THEN
        RAISE EXCEPTION 'graph rebuild migration found stale source fingerprints: %',
            stale_source_count;
    END IF;
END;
$$;
