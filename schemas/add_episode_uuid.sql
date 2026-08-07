-- RETIRED: this pre-migration helper used to drop and recreate the episode table.
-- Executing it would destroy durable graph-sync history and could replace the
-- supported 768-dimensional Nomic space with an incompatible vector width.
--
-- Use the immutable files in schemas/migrations/ through
-- src/scripts/migrate_database.py. Provider or dimension changes require shadow
-- storage; they must never drop or overwrite the active episode vector space.

DO $$
BEGIN
    RAISE EXCEPTION
        'schemas/add_episode_uuid.sql is retired; use the versioned migration runner';
END;
$$;
