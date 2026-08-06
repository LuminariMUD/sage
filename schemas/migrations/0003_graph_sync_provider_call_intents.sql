-- Reserve every provider request before network I/O so crashes cannot hide calls.

CREATE TABLE graph_sync_provider_call_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES graph_sync_attempts(id) ON DELETE RESTRICT,
    call_number INTEGER NOT NULL,
    logical_model_attempt INTEGER NOT NULL,
    transport_attempt INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_revision TEXT,
    candidate_fingerprint TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT graph_sync_provider_call_intents_number_unique
        UNIQUE (attempt_id, call_number),
    CONSTRAINT graph_sync_provider_call_intents_number_check CHECK (
        call_number > 0
        AND logical_model_attempt > 0
        AND transport_attempt > 0
    )
);

CREATE INDEX idx_graph_sync_provider_call_intents_candidate
    ON graph_sync_provider_call_intents(candidate_fingerprint, started_at);

-- Backfill reservations for any completed calls written between migrations 0002
-- and 0003. Production had none, but upgrades and test schemas may have them.
INSERT INTO graph_sync_provider_call_intents (
    attempt_id,
    call_number,
    logical_model_attempt,
    transport_attempt,
    provider,
    model,
    model_revision,
    candidate_fingerprint,
    prompt_version,
    schema_version,
    started_at
)
SELECT
    attempt_id,
    call_number,
    logical_model_attempt,
    transport_attempt,
    provider,
    model,
    model_revision,
    candidate_fingerprint,
    prompt_version,
    schema_version,
    started_at
FROM graph_sync_provider_calls;

ALTER TABLE graph_sync_provider_calls
    ADD CONSTRAINT graph_sync_provider_calls_intent_fk
    FOREIGN KEY (attempt_id, call_number)
    REFERENCES graph_sync_provider_call_intents(attempt_id, call_number)
    ON DELETE RESTRICT;

CREATE TRIGGER graph_sync_provider_call_intents_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_provider_call_intents
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

DROP TRIGGER graph_sync_provider_calls_budget ON graph_sync_provider_calls;

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
    FROM graph_sync_provider_call_intents
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

CREATE TRIGGER graph_sync_provider_call_intents_budget
    BEFORE INSERT ON graph_sync_provider_call_intents
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_provider_call_budget();

CREATE OR REPLACE FUNCTION graph_sync_guard_provider_call_result()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    intent graph_sync_provider_call_intents%ROWTYPE;
BEGIN
    SELECT provider_intent.*
    INTO intent
    FROM graph_sync_provider_call_intents AS provider_intent
    JOIN graph_sync_attempts AS attempt
      ON attempt.id = provider_intent.attempt_id
    WHERE provider_intent.attempt_id = NEW.attempt_id
      AND provider_intent.call_number = NEW.call_number
    FOR UPDATE OF attempt;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'provider call intent does not exist';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM graph_sync_attempt_results
        WHERE attempt_id = NEW.attempt_id
    ) THEN
        RAISE EXCEPTION 'provider call completion cannot follow a terminal result';
    END IF;

    IF NEW.logical_model_attempt IS DISTINCT FROM intent.logical_model_attempt
       OR NEW.transport_attempt IS DISTINCT FROM intent.transport_attempt
       OR NEW.provider IS DISTINCT FROM intent.provider
       OR NEW.model IS DISTINCT FROM intent.model
       OR NEW.model_revision IS DISTINCT FROM intent.model_revision
       OR NEW.candidate_fingerprint IS DISTINCT FROM intent.candidate_fingerprint
       OR NEW.prompt_version IS DISTINCT FROM intent.prompt_version
       OR NEW.schema_version IS DISTINCT FROM intent.schema_version
       OR NEW.started_at IS DISTINCT FROM intent.started_at THEN
        RAISE EXCEPTION 'provider call completion does not match its intent';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER graph_sync_provider_calls_match_intent
    BEFORE INSERT ON graph_sync_provider_calls
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_provider_call_result();

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

    IF NEW.outcome IN ('primary_success', 'fallback_success') THEN
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

COMMENT ON TABLE graph_sync_provider_call_intents IS
    'Immutable request reservations committed before provider network I/O';
COMMENT ON TABLE graph_sync_provider_calls IS
    'Immutable sanitized completion provenance for reserved provider requests';

DO $$
DECLARE
    invalid_intent_sequence_count BIGINT;
    unmatched_completion_count BIGINT;
    invalid_result_count BIGINT;
BEGIN
    SELECT count(*)
    INTO invalid_intent_sequence_count
    FROM (
        SELECT attempt_id
        FROM graph_sync_provider_call_intents
        GROUP BY attempt_id
        HAVING min(call_number) <> 1
            OR count(*) <> max(call_number)
    ) AS invalid_sequences;

    IF invalid_intent_sequence_count <> 0 THEN
        RAISE EXCEPTION 'invalid provider call intent sequences: %',
            invalid_intent_sequence_count;
    END IF;

    SELECT count(*)
    INTO unmatched_completion_count
    FROM graph_sync_provider_calls AS provider_call
    JOIN graph_sync_provider_call_intents AS intent
      ON intent.attempt_id = provider_call.attempt_id
     AND intent.call_number = provider_call.call_number
    WHERE provider_call.logical_model_attempt
            IS DISTINCT FROM intent.logical_model_attempt
       OR provider_call.transport_attempt
            IS DISTINCT FROM intent.transport_attempt
       OR provider_call.provider IS DISTINCT FROM intent.provider
       OR provider_call.model IS DISTINCT FROM intent.model
       OR provider_call.model_revision IS DISTINCT FROM intent.model_revision
       OR provider_call.candidate_fingerprint
            IS DISTINCT FROM intent.candidate_fingerprint
       OR provider_call.prompt_version IS DISTINCT FROM intent.prompt_version
       OR provider_call.schema_version IS DISTINCT FROM intent.schema_version
       OR provider_call.started_at IS DISTINCT FROM intent.started_at;

    IF unmatched_completion_count <> 0 THEN
        RAISE EXCEPTION 'provider call completions do not match intents: %',
            unmatched_completion_count;
    END IF;

    SELECT count(*)
    INTO invalid_result_count
    FROM graph_sync_attempt_results AS result
    WHERE result.provider_call_count <> (
        SELECT count(*)
        FROM graph_sync_provider_call_intents AS intent
        WHERE intent.attempt_id = result.attempt_id
    );

    IF invalid_result_count <> 0 THEN
        RAISE EXCEPTION 'invalid graph sync attempt intent counts: %',
            invalid_result_count;
    END IF;
END;
$$;
