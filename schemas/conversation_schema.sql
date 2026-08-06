-- Conversation storage schema for Luminari Lore Chat Agent
-- Stores conversation history with metadata for context management

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255),  -- Optional user identifier
    title VARCHAR(500),    -- Auto-generated conversation title
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,  -- User preferences, settings, etc.
    message_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_type VARCHAR(50) NOT NULL CHECK (message_type IN ('user', 'assistant')),
    content TEXT NOT NULL,
    tools_used JSONB DEFAULT '[]'::jsonb,  -- Array of tools called for this message
    sources JSONB DEFAULT '[]'::jsonb,     -- Array of source documents/episodes
    entities_discovered JSONB DEFAULT '[]'::jsonb,  -- Entities found during processing
    metadata JSONB DEFAULT '{}'::jsonb,    -- Token count, processing time, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_streams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    stream_id VARCHAR(255) NOT NULL UNIQUE,  -- For SSE connection tracking
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'error')),
    current_message_id UUID REFERENCES conversation_messages(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 hour')
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_created_at ON conversation_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_conversation_streams_stream_id ON conversation_streams(stream_id);
CREATE INDEX IF NOT EXISTS idx_conversation_streams_expires_at ON conversation_streams(expires_at);

-- Add sequence column for message ordering
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS sequence_number SERIAL;
CREATE INDEX IF NOT EXISTS idx_conversation_messages_sequence ON conversation_messages(conversation_id, sequence_number);

-- Update trigger for conversations.updated_at
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    NEW.message_count = (
        SELECT COUNT(*)
        FROM conversation_messages
        WHERE conversation_id = NEW.id
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_conversation_timestamp
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_timestamp();

-- Auto-generate conversation titles based on first user message
CREATE OR REPLACE FUNCTION generate_conversation_title()
RETURNS TRIGGER AS $$
DECLARE
    first_message TEXT;
    generated_title TEXT;
BEGIN
    -- Only generate title for first user message
    IF NEW.message_type = 'user' AND
       (SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = NEW.conversation_id AND message_type = 'user') = 1 THEN

        first_message := NEW.content;

        -- Generate title from first 50 characters, truncate at word boundary
        generated_title := LEFT(first_message, 50);
        IF LENGTH(first_message) > 50 THEN
            generated_title := LEFT(generated_title, LENGTH(generated_title) - LENGTH(SPLIT_PART(generated_title, ' ', -1))) || '...';
        END IF;

        -- Update conversation title
        UPDATE conversations
        SET title = generated_title
        WHERE id = NEW.conversation_id AND (title IS NULL OR title = '');
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_generate_conversation_title
    AFTER INSERT ON conversation_messages
    FOR EACH ROW
    EXECUTE FUNCTION generate_conversation_title();

-- Cleanup expired streams
CREATE OR REPLACE FUNCTION cleanup_expired_streams()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversation_streams
    WHERE expires_at < CURRENT_TIMESTAMP;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE conversations IS 'Stores chat conversation metadata and settings';
COMMENT ON TABLE conversation_messages IS 'Individual messages within conversations with tool usage tracking';
COMMENT ON TABLE conversation_streams IS 'Active SSE stream connections for real-time chat';
COMMENT ON COLUMN conversation_messages.tools_used IS 'JSON array of tools called: [{"tool": "search_entities", "args": {...}, "execution_time": 1.2}]';
COMMENT ON COLUMN conversation_messages.sources IS 'JSON array of source documents: [{"type": "episode", "id": "123", "title": "...", "relevance": 0.95}]';
COMMENT ON COLUMN conversation_messages.entities_discovered IS 'JSON array of entities found: [{"id": "uuid", "name": "Paladine", "type": "Deity", "relevance": 0.9}]';
