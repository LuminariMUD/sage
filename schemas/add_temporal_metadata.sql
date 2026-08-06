-- Migration to add temporal metadata support to episodes table
-- Adds fields to support two-stage temporal preprocessing

-- Add temporal metadata flag
ALTER TABLE episodes
ADD COLUMN IF NOT EXISTS is_temporal_metadata BOOLEAN DEFAULT FALSE;

-- Add temporal ordering field
ALTER TABLE episodes
ADD COLUMN IF NOT EXISTS temporal_order INTEGER;

-- Create index for temporal queries
CREATE INDEX IF NOT EXISTS idx_episodes_temporal_order
ON episodes(temporal_order)
WHERE temporal_order IS NOT NULL;

-- Create index for temporal metadata episodes
CREATE INDEX IF NOT EXISTS idx_episodes_temporal_metadata
ON episodes(is_temporal_metadata)
WHERE is_temporal_metadata = TRUE;

-- Create compound index for temporal document queries
CREATE INDEX IF NOT EXISTS idx_episodes_temporal_compound
ON episodes(document_id, temporal_order, episode_index)
WHERE temporal_order IS NOT NULL;

-- Update existing episodes metadata to ensure JSONB structure
-- This is safe - won't overwrite existing metadata
UPDATE episodes
SET metadata = COALESCE(metadata, '{}')::jsonb
WHERE metadata IS NULL;

-- Add comment to explain temporal fields
COMMENT ON COLUMN episodes.is_temporal_metadata IS
'Flag indicating this episode contains extracted temporal metadata (timeline, events, causal chains)';

COMMENT ON COLUMN episodes.temporal_order IS
'Global chronological ordering value - lower numbers are earlier in timeline';

-- Function to get temporal context for a document
CREATE OR REPLACE FUNCTION get_temporal_context(doc_id UUID)
RETURNS TABLE(
    temporal_order INTEGER,
    temporal_type TEXT,
    eras JSONB,
    event_count INTEGER,
    causal_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (e.metadata->>'temporal_order')::INTEGER as temporal_order,
        e.metadata->>'temporal_type' as temporal_type,
        e.metadata->'eras' as eras,
        (e.metadata->>'event_count')::INTEGER as event_count,
        (e.metadata->>'causal_count')::INTEGER as causal_count
    FROM episodes e
    WHERE e.document_id = doc_id
      AND e.is_temporal_metadata = TRUE
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get documents in chronological order
CREATE OR REPLACE FUNCTION get_documents_chronological()
RETURNS TABLE(
    document_id UUID,
    title TEXT,
    temporal_order INTEGER,
    temporal_type TEXT,
    eras JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        d.id as document_id,
        d.title,
        (e.metadata->>'temporal_order')::INTEGER as temporal_order,
        e.metadata->>'temporal_type' as temporal_type,
        e.metadata->'eras' as eras
    FROM lore_documents d
    JOIN episodes e ON d.id = e.document_id
    WHERE e.is_temporal_metadata = TRUE
    ORDER BY (e.metadata->>'temporal_order')::INTEGER NULLS LAST;
END;
$$ LANGUAGE plpgsql;

-- View for temporal documents
CREATE OR REPLACE VIEW temporal_documents AS
SELECT
    d.id,
    d.title,
    d.source_file,
    (e.metadata->>'temporal_order')::INTEGER as temporal_order,
    e.metadata->>'temporal_type' as temporal_type,
    e.metadata->'eras' as eras,
    (e.metadata->>'event_count')::INTEGER as event_count,
    (e.metadata->>'causal_count')::INTEGER as causal_count,
    e.created_at as temporal_extracted_at
FROM lore_documents d
JOIN episodes e ON d.id = e.document_id
WHERE e.is_temporal_metadata = TRUE;

-- Grant permissions
GRANT SELECT ON temporal_documents TO PUBLIC;

-- Migration completion message
DO $$
BEGIN
    RAISE NOTICE 'Temporal metadata migration completed successfully';
    RAISE NOTICE 'New fields: is_temporal_metadata, temporal_order';
    RAISE NOTICE 'New indexes: temporal_order, temporal_metadata, temporal_compound';
    RAISE NOTICE 'New functions: get_temporal_context(), get_documents_chronological()';
    RAISE NOTICE 'New view: temporal_documents';
END $$;
