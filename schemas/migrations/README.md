# PostgreSQL Migrations

Migration files in this directory are immutable, ordered SQL inputs for
`src/scripts/migrate_database.py`.

## Rules

- File names use `NNNN_lowercase_description.sql`.
- Applied file checksums are stored in `schema_migrations`.
- Never edit an applied migration. Add the next numbered file instead.
- Run `python src/scripts/migrate_database.py --status` before applying.
- Capture and verify PostgreSQL and Neo4j backups before a state or vector migration.
- Apply with `python src/scripts/migrate_database.py --apply` only after preflight passes.
- Migrations run one at a time in transactions under a PostgreSQL advisory lock.
- Migration SQL and ledger metadata must never contain credentials or source lore text.

The graph-sync ledger is intentionally evidence-preserving. There is no automated
down migration that drops attempt history. Rollback uses the verified pre-migration
database backup and the documented application rollback procedure.
