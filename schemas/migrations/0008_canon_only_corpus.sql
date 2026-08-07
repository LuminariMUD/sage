-- Fail-closed database boundary for the production lore corpus.
-- Documents may exist for administrative purposes, but only canon documents
-- can ever acquire episodes, embeddings, or durable graph-sync jobs.

DO $$
DECLARE
    excluded_episode_count BIGINT;
BEGIN
    SELECT count(*)
    INTO excluded_episode_count
    FROM episodes AS episode
    LEFT JOIN lore_documents AS document ON document.id = episode.document_id
    WHERE document.id IS NULL
       OR document.canonical IS NOT TRUE
       OR COALESCE(document.source_file, '') NOT LIKE 'canon/%';

    IF excluded_episode_count <> 0 THEN
        RAISE EXCEPTION
            'canon-only corpus migration found % excluded episode rows',
            excluded_episode_count;
    END IF;
END;
$$;

ALTER TABLE lore_documents
    ADD CONSTRAINT lore_documents_canonical_source_check
    CHECK (canonical IS NOT TRUE OR source_file LIKE 'canon/%')
    NOT VALID;

ALTER TABLE lore_documents
    VALIDATE CONSTRAINT lore_documents_canonical_source_check;

CREATE OR REPLACE FUNCTION canon_corpus_require_episode_document()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM lore_documents AS document
        WHERE document.id = NEW.document_id
          AND document.canonical IS TRUE
          AND document.source_file LIKE 'canon/%'
    ) THEN
        RAISE EXCEPTION
            'episodes may reference only documents from lore_docs/canon';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER episodes_require_canon_document
    BEFORE INSERT OR UPDATE OF document_id ON episodes
    FOR EACH ROW EXECUTE FUNCTION canon_corpus_require_episode_document();

CREATE OR REPLACE FUNCTION canon_corpus_guard_document_scope()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF (
        NEW.canonical IS NOT TRUE
        OR NEW.source_file NOT LIKE 'canon/%'
    ) AND EXISTS (
        SELECT 1
        FROM episodes AS episode
        WHERE episode.document_id = NEW.id
    ) THEN
        RAISE EXCEPTION
            'documents with episodes must remain in lore_docs/canon';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER lore_documents_guard_canon_episode_scope
    BEFORE UPDATE OF canonical, source_file ON lore_documents
    FOR EACH ROW EXECUTE FUNCTION canon_corpus_guard_document_scope();

COMMENT ON CONSTRAINT lore_documents_canonical_source_check ON lore_documents IS
    'Canonical documents must be rooted at lore_docs/canon';
COMMENT ON FUNCTION canon_corpus_require_episode_document() IS
    'Rejects episode creation outside the production canon corpus';
