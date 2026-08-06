-- PostgreSQL schema for relationship corrections audit trail
-- This stores complete relationship data before modifications for full rollback capability

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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

-- Indexes for efficient queries
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

-- Add comments for documentation
COMMENT ON TABLE relationship_corrections IS 'Audit trail for all relationship corrections with complete backup data for rollback';
COMMENT ON COLUMN relationship_corrections.correction_batch_id IS 'Groups all corrections made in a single validation run';
COMMENT ON COLUMN relationship_corrections.original_properties IS 'Complete Neo4j relationship properties including embeddings before correction';
COMMENT ON COLUMN relationship_corrections.new_properties IS 'Updated properties after correction (NULL for deletions)';
COMMENT ON COLUMN relationship_corrections.duplicate_count IS 'For deduplication corrections: total number of duplicates found';

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
