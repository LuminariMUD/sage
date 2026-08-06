-- Hybrid Graph RAG Episodes Schema Extension
-- This schema extends the existing episodes table for the hybrid architecture
-- Run this AFTER the main postgresql_schema.sql

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The existing episodes table structure from main schema:
-- CREATE TABLE episodes (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     episode_id VARCHAR(50) UNIQUE NOT NULL,    -- This conflicts with our needs
--     content TEXT NOT NULL,
--     embedding vector(384),                     -- Different dimension than needed
--     entity_refs JSONB DEFAULT '[]',
--     previous_episode VARCHAR(50),
--     metadata JSONB DEFAULT '{}',
--     created_at TIMESTAMPTZ DEFAULT NOW()
-- );

-- Drop existing episodes table if it exists with old structure
DROP TABLE IF EXISTS episodes CASCADE;

-- Create new episodes table for hybrid Graph RAG architecture
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES lore_documents(id) ON DELETE CASCADE,
    episode_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension (change to 384 for sentence-transformers)
    graphiti_synced BOOLEAN DEFAULT FALSE,
    graphiti_synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Optional fields for compatibility
    entity_refs JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',

    -- Ensure unique episodes per document
    CONSTRAINT episodes_document_episode_unique UNIQUE(document_id, episode_index)
);

-- Create indexes for efficient querying
CREATE INDEX idx_episodes_document_id ON episodes(document_id);
CREATE INDEX idx_episodes_graphiti_synced ON episodes(graphiti_synced) WHERE graphiti_synced = FALSE;
CREATE INDEX idx_episodes_embedding ON episodes USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_episodes_entity_refs ON episodes USING GIN(entity_refs);

-- Link chunks to episodes if needed (optional relationship)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL;

-- Update trigger for updated_at timestamp
-- (Reuse existing function if available)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for episodes table
CREATE TRIGGER update_episodes_updated_at
    BEFORE UPDATE ON episodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add processing status tracking for document processing pipeline
ALTER TABLE lore_documents ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE lore_documents ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE;
