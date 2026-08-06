# Provider Upgrade Backup and Restore Runbook

**Last updated**: 2026-08-07
**Scope**: PostgreSQL and Neo4j data required by the provider and graph-sync upgrade

## Safety contract

- Keep graph workers stopped before backup, migration, or restore work.
- Store backup sets only below the repository `backups/` directory. That directory is ignored by Git.
- Never apply a database migration until `make verify-provider-upgrade-backup` succeeds for the exact backup reference.
- Treat restore as a maintenance operation. Stop API and worker writes before replacing either database.
- Preserve the old backup through migration validation, rollout, and the full rollback bake period.

## Create a backup set

Choose a unique reference containing only letters, digits, `.`, `_`, `/`, `:`, `+`, or `-`:

```bash
make backup-provider-upgrade \
  BACKUP_REFERENCE=backups/provider-upgrade-YYYYMMDDTHHMMSSZ
```

The command performs all of these gates before it writes `BACKUP_COMPLETE`:

1. Creates a PostgreSQL custom-format dump.
2. Restores that dump into a generated scratch database and records episode and table counts.
3. Briefly stops Neo4j Community Edition.
4. Dumps both the `neo4j` and `system` databases while they are offline.
5. Inspects both Neo4j archives and runs full archive consistency checks.
6. Restarts Neo4j and waits for its health check.
7. Computes SHA-256 hashes and verifies the complete private backup set.

The legacy graph worker is not started by this command.

## Verify a backup set

Run this immediately before any migration or restore:

```bash
make verify-provider-upgrade-backup \
  BACKUP_REFERENCE=backups/provider-upgrade-YYYYMMDDTHHMMSSZ
```

Verification fails closed for an escaped path, missing marker, altered dump, symlink, broad permissions, malformed evidence, failed scratch-restore counts, or incomplete Neo4j archive evidence.

## PostgreSQL restore

This replaces the active application database. Use it only during an approved rollback or recovery window.

```bash
backup_reference=backups/provider-upgrade-YYYYMMDDTHHMMSSZ

make verify-provider-upgrade-backup BACKUP_REFERENCE="$backup_reference"
docker compose stop api
docker compose exec -T postgres sh -lc '
  dropdb --if-exists --force -U "$POSTGRES_USER" "$POSTGRES_DB"
  createdb -T template0 -U "$POSTGRES_USER" "$POSTGRES_DB"
'
docker compose exec -T postgres sh -lc '
  pg_restore --exit-on-error --no-owner --no-privileges \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' < "$backup_reference/postgres.dump"
docker compose start api
```

Then wait for API health, confirm the graph worker is still absent, and run `make graph-audit`.

## Neo4j restore

Neo4j Community Edition must remain stopped while both databases are loaded. The helper container copies private host artifacts into an exact temporary directory on the Neo4j data volume so `neo4j-admin` can read them as the `neo4j` user.

```bash
backup_reference=backups/provider-upgrade-YYYYMMDDTHHMMSSZ
neo4j_container=luminari-neo4j
restore_dir=/data/dumps/sage-provider-restore

make verify-provider-upgrade-backup BACKUP_REFERENCE="$backup_reference"
docker compose stop api neo4j
neo4j_image=$(docker inspect --format '{{.Config.Image}}' "$neo4j_container")

docker run --rm \
  --network none \
  --volumes-from "$neo4j_container" \
  --volume "$(realpath "$backup_reference"):/backup:ro" \
  --entrypoint bash \
  "$neo4j_image" \
  -lc '
    set -Eeuo pipefail
    target=$1
    case "$target" in /data/dumps/sage-provider-restore) ;; *) exit 2 ;; esac
    install -d -o neo4j -g neo4j -m 700 "$target"
    install -o neo4j -g neo4j -m 600 /backup/neo4j.dump "$target/neo4j.dump"
    install -o neo4j -g neo4j -m 600 /backup/system.dump "$target/system.dump"
  ' bash "$restore_dir"

docker run --rm --network none --user neo4j \
  --volumes-from "$neo4j_container" --entrypoint neo4j-admin "$neo4j_image" \
  database load --from-path="$restore_dir" --overwrite-destination=true neo4j
docker run --rm --network none --user neo4j \
  --volumes-from "$neo4j_container" --entrypoint neo4j-admin "$neo4j_image" \
  database load --from-path="$restore_dir" --overwrite-destination=true system

docker run --rm \
  --network none \
  --volumes-from "$neo4j_container" \
  --entrypoint bash \
  "$neo4j_image" \
  -lc '
    set -Eeuo pipefail
    target=$1
    case "$target" in /data/dumps/sage-provider-restore) ;; *) exit 2 ;; esac
    find "$target" -depth -mindepth 1 -delete
    rmdir -- "$target"
  ' bash "$restore_dir"

docker compose start neo4j
docker compose up -d api
```

Wait for both services to become healthy. Confirm the graph worker remains stopped, then run `make graph-audit`. A clean audit is required before any write traffic resumes.

## Migration gate

The additive migration target repeats backup verification and refuses a dirty worktree:

```bash
make db-migrate \
  BACKUP_REFERENCE=backups/provider-upgrade-YYYYMMDDTHHMMSSZ
make db-migrate-check
make graph-audit
```

Do not delete the backup after these commands succeed. Migration success is not the end of the rollback retention period.
