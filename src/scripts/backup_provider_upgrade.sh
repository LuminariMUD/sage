#!/usr/bin/env bash
# Create one verified PostgreSQL and Neo4j backup set before provider migrations.

set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/../.." && pwd)
backup_reference=${1:-"backups/provider-upgrade-$(date -u +%Y%m%dT%H%M%SZ)"}

if [[ ${CONFIRM_NEO4J_OFFLINE_BACKUP:-} != 1 ]]; then
    echo "Set CONFIRM_NEO4J_OFFLINE_BACKUP=1 to permit the Neo4j offline dump." >&2
    exit 2
fi

if [[ $backup_reference = /* ]]; then
    backup_dir=$(realpath -m -- "$backup_reference")
else
    backup_dir=$(realpath -m -- "$project_dir/$backup_reference")
fi
case "$backup_dir" in
    "$project_dir"/backups/*) ;;
    *)
        echo "Backup set must be below $project_dir/backups/." >&2
        exit 2
        ;;
esac

relative_reference=${backup_dir#"$project_dir"/}
if [[ ! $relative_reference =~ ^[A-Za-z0-9._/:+-]{1,255}$ ]]; then
    echo "Backup reference contains unsupported characters." >&2
    exit 2
fi

mkdir -p -- "$backup_dir"
chmod 700 -- "$backup_dir"
if [[ -e $backup_dir/BACKUP_COMPLETE || -e $backup_dir/BACKUP_COMPLETE.partial ]]; then
    echo "Refusing to overwrite an existing backup completion marker." >&2
    exit 1
fi

bash "$script_dir/backup_postgres.sh" "$backup_dir"
CONFIRM_NEO4J_OFFLINE_BACKUP=1 \
    bash "$script_dir/backup_neo4j.sh" luminari-neo4j "$backup_dir"

(
    cd -- "$backup_dir"
    sha256sum --check postgres-SHA256SUMS
    sha256sum --check neo4j-SHA256SUMS

    postgres_sha256=$(sha256sum postgres.dump | awk '{print $1}')
    neo4j_sha256=$(sha256sum neo4j.dump | awk '{print $1}')
    system_sha256=$(sha256sum system.dump | awk '{print $1}')
    printf '%s\n' \
        'format=sage-provider-upgrade-backup-v1' \
        "backup_reference=$relative_reference" \
        "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "postgres_sha256=$postgres_sha256" \
        "neo4j_sha256=$neo4j_sha256" \
        "system_sha256=$system_sha256" \
        > BACKUP_COMPLETE.partial
    chmod 600 BACKUP_COMPLETE.partial
    mv -- BACKUP_COMPLETE.partial BACKUP_COMPLETE
)

python3 "$script_dir/verify_provider_upgrade_backup.py" "$relative_reference"
echo "Verified backup reference: $relative_reference"
