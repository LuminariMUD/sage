-- Add incremental processing tracking columns to lore_documents table

-- Add tracking columns for incremental processing
ALTER TABLE lore_documents
ADD COLUMN IF NOT EXISTS graphiti_processed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS graphiti_content_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS graphiti_status VARCHAR(20) DEFAULT 'pending';

-- Create index for efficient querying of pending documents
CREATE INDEX IF NOT EXISTS idx_lore_documents_graphiti_status
ON lore_documents(graphiti_status);

-- Create index for content hash lookups
CREATE INDEX IF NOT EXISTS idx_lore_documents_content_hash
ON lore_documents(graphiti_content_hash);

-- Update existing documents to pending status
UPDATE lore_documents
SET graphiti_status = 'pending'
WHERE graphiti_status IS NULL;
