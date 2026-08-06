-- Runtime policy fields and database enforcement for durable Graphiti workers.

ALTER TABLE graph_sync_jobs
    ADD COLUMN attempt_budget_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN retry_generation INTEGER NOT NULL DEFAULT 0;

UPDATE graph_sync_jobs
SET attempt_budget_count = job_attempt_count
WHERE job_attempt_count > 0;

ALTER TABLE graph_sync_jobs
    ADD CONSTRAINT graph_sync_jobs_attempt_budget_check CHECK (
        attempt_budget_count >= 0
        AND attempt_budget_count <= job_attempt_count
    ),
    ADD CONSTRAINT graph_sync_jobs_retry_generation_check CHECK (
        retry_generation >= 0
    );

ALTER TABLE graph_sync_runs
    ADD COLUMN heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp();

CREATE INDEX idx_graph_sync_runs_heartbeat
    ON graph_sync_runs(state, heartbeat_at)
    WHERE state <> 'stopped';

ALTER TABLE graph_sync_attempts
    ADD COLUMN retry_generation INTEGER,
    ADD COLUMN budget_attempt_number INTEGER,
    ADD COLUMN job_attempt_limit INTEGER,
    ADD COLUMN provider_call_limit INTEGER,
    ADD COLUMN retry_delay_seconds INTEGER;

-- Migration 0001 protects attempts with an append-only trigger. Temporarily
-- remove that trigger inside this migration transaction so existing rows can
-- receive the new required policy fields, then restore it before commit.
DROP TRIGGER graph_sync_attempts_append_only ON graph_sync_attempts;

UPDATE graph_sync_attempts AS attempt
SET retry_generation = 0,
    budget_attempt_number = attempt.attempt_number,
    job_attempt_limit = GREATEST(attempt.attempt_number, 3),
    provider_call_limit = GREATEST(
        1,
        COALESCE(
            (
                SELECT max(provider_call.call_number)
                FROM graph_sync_provider_calls AS provider_call
                WHERE provider_call.attempt_id = attempt.id
            ),
            1
        )
    ),
    retry_delay_seconds = 60;

ALTER TABLE graph_sync_attempts
    ALTER COLUMN retry_generation SET NOT NULL,
    ALTER COLUMN budget_attempt_number SET NOT NULL,
    ALTER COLUMN job_attempt_limit SET NOT NULL,
    ALTER COLUMN provider_call_limit SET NOT NULL,
    ALTER COLUMN retry_delay_seconds SET NOT NULL,
    ADD CONSTRAINT graph_sync_attempts_retry_generation_check CHECK (
        retry_generation >= 0
    ),
    ADD CONSTRAINT graph_sync_attempts_budget_number_check CHECK (
        budget_attempt_number > 0
        AND budget_attempt_number <= attempt_number
    ),
    ADD CONSTRAINT graph_sync_attempts_job_limit_check CHECK (
        job_attempt_limit > 0
        AND budget_attempt_number <= job_attempt_limit
    ),
    ADD CONSTRAINT graph_sync_attempts_provider_limit_check CHECK (
        provider_call_limit > 0
    ),
    ADD CONSTRAINT graph_sync_attempts_retry_delay_check CHECK (
        retry_delay_seconds > 0
    );

CREATE TRIGGER graph_sync_attempts_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_attempts
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

CREATE OR REPLACE FUNCTION graph_sync_guard_provider_call_budget()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    allowed_calls INTEGER;
    expected_call_number INTEGER;
BEGIN
    SELECT provider_call_limit
    INTO allowed_calls
    FROM graph_sync_attempts
    WHERE id = NEW.attempt_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'graph sync attempt does not exist';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM graph_sync_attempt_results
        WHERE attempt_id = NEW.attempt_id
    ) THEN
        RAISE EXCEPTION 'provider calls cannot follow a terminal attempt result';
    END IF;

    SELECT COALESCE(max(call_number), 0) + 1
    INTO expected_call_number
    FROM graph_sync_provider_calls
    WHERE attempt_id = NEW.attempt_id;

    IF NEW.call_number <> expected_call_number THEN
        RAISE EXCEPTION 'provider call number must be the next append-only value';
    END IF;

    IF NEW.call_number > allowed_calls THEN
        RAISE EXCEPTION 'provider call limit exceeded for graph sync attempt';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_provider_calls_budget
    BEFORE INSERT ON graph_sync_provider_calls
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_provider_call_budget();

CREATE OR REPLACE FUNCTION graph_sync_guard_attempt_result()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    observed_provider_calls INTEGER;
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
    FROM graph_sync_provider_calls
    WHERE attempt_id = NEW.attempt_id;

    IF NEW.provider_call_count <> observed_provider_calls THEN
        RAISE EXCEPTION 'attempt result provider-call count does not match ledger';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_attempt_results_provider_count
    BEFORE INSERT ON graph_sync_attempt_results
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_attempt_result();

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
        attempt_budget_count = 0,
        retry_generation = graph_sync_jobs.retry_generation + 1,
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

COMMENT ON COLUMN graph_sync_jobs.job_attempt_count IS
    'Immutable total attempt sequence across source revisions and operator retries';
COMMENT ON COLUMN graph_sync_jobs.attempt_budget_count IS
    'Attempts consumed in the current retry generation';
COMMENT ON COLUMN graph_sync_jobs.retry_generation IS
    'Monotonic generation incremented by source changes or explicit retry';
COMMENT ON COLUMN graph_sync_attempts.provider_call_limit IS
    'Hard upstream request ceiling captured when the lease is claimed';
COMMENT ON COLUMN graph_sync_attempts.retry_delay_seconds IS
    'Deterministic retry delay captured when the lease is claimed';

DO $$
DECLARE
    invalid_job_count BIGINT;
    invalid_attempt_count BIGINT;
    invalid_result_count BIGINT;
BEGIN
    SELECT count(*)
    INTO invalid_job_count
    FROM graph_sync_jobs
    WHERE attempt_budget_count < 0
       OR attempt_budget_count > job_attempt_count
       OR retry_generation < 0;

    IF invalid_job_count <> 0 THEN
        RAISE EXCEPTION 'invalid graph sync runtime jobs: %', invalid_job_count;
    END IF;

    SELECT count(*)
    INTO invalid_attempt_count
    FROM graph_sync_attempts
    WHERE retry_generation < 0
       OR budget_attempt_number <= 0
       OR budget_attempt_number > attempt_number
       OR budget_attempt_number > job_attempt_limit
       OR provider_call_limit <= 0
       OR retry_delay_seconds <= 0;

    IF invalid_attempt_count <> 0 THEN
        RAISE EXCEPTION 'invalid graph sync runtime attempts: %', invalid_attempt_count;
    END IF;

    SELECT count(*)
    INTO invalid_result_count
    FROM graph_sync_attempt_results AS result
    WHERE result.provider_call_count <> (
        SELECT count(*)
        FROM graph_sync_provider_calls AS provider_call
        WHERE provider_call.attempt_id = result.attempt_id
    );

    IF invalid_result_count <> 0 THEN
        RAISE EXCEPTION 'invalid graph sync attempt result counts: %',
            invalid_result_count;
    END IF;
END;
$$;
