-- Append-only, content-free relationship-quality evidence for verified graph syncs.

CREATE TABLE graph_sync_relationship_quality (
    attempt_id UUID PRIMARY KEY
        REFERENCES graph_sync_attempt_results(attempt_id) ON DELETE RESTRICT,
    vocabulary_fingerprint TEXT NOT NULL,
    proposed_edge_count INTEGER NOT NULL,
    normalized_edge_count INTEGER NOT NULL,
    accepted_edge_count INTEGER NOT NULL,
    rejected_edge_count INTEGER NOT NULL,
    resolved_edge_count INTEGER NOT NULL,
    new_edge_count INTEGER NOT NULL,
    invalidated_edge_count INTEGER NOT NULL,
    rejected_unknown_type_count INTEGER NOT NULL,
    rejected_missing_endpoint_count INTEGER NOT NULL,
    rejected_ambiguous_endpoint_count INTEGER NOT NULL,
    rejected_self_edge_count INTEGER NOT NULL,
    rejected_empty_fact_count INTEGER NOT NULL,
    rejected_duplicate_count INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT graph_sync_relationship_quality_fingerprint_check CHECK (
        vocabulary_fingerprint ~ '^relationships:sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT graph_sync_relationship_quality_counts_check CHECK (
        proposed_edge_count >= 0
        AND normalized_edge_count >= 0
        AND accepted_edge_count >= 0
        AND rejected_edge_count >= 0
        AND resolved_edge_count >= 0
        AND new_edge_count >= 0
        AND invalidated_edge_count >= 0
        AND rejected_unknown_type_count >= 0
        AND rejected_missing_endpoint_count >= 0
        AND rejected_ambiguous_endpoint_count >= 0
        AND rejected_self_edge_count >= 0
        AND rejected_empty_fact_count >= 0
        AND rejected_duplicate_count >= 0
    ),
    CONSTRAINT graph_sync_relationship_quality_proposal_check CHECK (
        accepted_edge_count + rejected_edge_count = proposed_edge_count
        AND normalized_edge_count <= accepted_edge_count
    ),
    CONSTRAINT graph_sync_relationship_quality_rejection_check CHECK (
        rejected_unknown_type_count
        + rejected_missing_endpoint_count
        + rejected_ambiguous_endpoint_count
        + rejected_self_edge_count
        + rejected_empty_fact_count
        + rejected_duplicate_count = rejected_edge_count
    ),
    CONSTRAINT graph_sync_relationship_quality_maintenance_check CHECK (
        new_edge_count <= resolved_edge_count
    )
);

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

    IF attempt_result.outcome NOT IN ('primary_success', 'fallback_success') THEN
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

CREATE TRIGGER graph_sync_relationship_quality_guard
    BEFORE INSERT ON graph_sync_relationship_quality
    FOR EACH ROW EXECUTE FUNCTION graph_sync_guard_relationship_quality();

CREATE TRIGGER graph_sync_relationship_quality_append_only
    BEFORE UPDATE OR DELETE ON graph_sync_relationship_quality
    FOR EACH ROW EXECUTE FUNCTION graph_sync_reject_ledger_mutation();

COMMENT ON TABLE graph_sync_relationship_quality IS
    'Content-free relationship proposal, rejection-reason, and maintenance evidence';
COMMENT ON COLUMN graph_sync_relationship_quality.vocabulary_fingerprint IS
    'Versioned canonical relationship vocabulary and safe-alias policy identity';

DO $$
DECLARE
    invalid_quality_count BIGINT;
BEGIN
    SELECT count(*)
    INTO invalid_quality_count
    FROM graph_sync_relationship_quality AS quality
    JOIN graph_sync_attempt_results AS result
      ON result.attempt_id = quality.attempt_id
    WHERE result.outcome NOT IN ('primary_success', 'fallback_success')
       OR result.proposed_edge_count IS DISTINCT FROM quality.proposed_edge_count
       OR result.accepted_edge_count IS DISTINCT FROM quality.accepted_edge_count
       OR result.rejected_edge_count IS DISTINCT FROM quality.rejected_edge_count;

    IF invalid_quality_count <> 0 THEN
        RAISE EXCEPTION 'invalid graph relationship quality rows: %', invalid_quality_count;
    END IF;
END;
$$;
