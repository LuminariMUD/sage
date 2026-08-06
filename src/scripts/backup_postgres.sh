#!/usr/bin/env bash
# Create a PostgreSQL custom-format backup and prove it restores to a scratch DB.

set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/../.." && pwd)
requested_destination=${1:-"backups/postgres-$(date -u +%Y%m%dT%H%M%SZ)"}

if [[ $requested_destination = /* ]]; then
    backup_dir=$(realpath -m -- "$requested_destination")
else
    backup_dir=$(realpath -m -- "$project_dir/$requested_destination")
fi
case "$backup_dir" in
    "$project_dir"/backups/*) ;;
    *)
        echo "PostgreSQL backup destination must be below $project_dir/backups/." >&2
        exit 2
        ;;
esac

cd -- "$project_dir"
postgres_container=$(docker compose ps -q postgres)
if [[ -z $postgres_container ]]; then
    echo "PostgreSQL Compose service is not running." >&2
    exit 1
fi
if [[ $(docker inspect --format '{{.State.Running}}' "$postgres_container") != true ]]; then
    echo "PostgreSQL Compose service is not running." >&2
    exit 1
fi

mkdir -p -- "$backup_dir"
chmod 700 -- "$backup_dir"
dump_path="$backup_dir/postgres.dump"
partial_path="$backup_dir/postgres.dump.partial"
restore_list_path="$backup_dir/postgres-restore-list.txt"
verification_path="$backup_dir/postgres-restore-verification.txt"
checksum_path="$backup_dir/postgres-SHA256SUMS"
for output in \
    "$dump_path" \
    "$partial_path" \
    "$restore_list_path" \
    "$verification_path" \
    "$checksum_path"; do
    if [[ -e $output ]]; then
        echo "Refusing to overwrite existing backup artifact: $output" >&2
        exit 1
    fi
done

verify_db="sage_restore_verify_$(date -u +%Y%m%d%H%M%S)_$$"
verify_db_created=0

cleanup() {
    status=$?
    trap - EXIT INT TERM

    if [[ $verify_db_created == 1 ]]; then
        docker compose exec -T postgres sh -lc '
            dropdb --if-exists --force -U "$POSTGRES_USER" "$1"
        ' sh "$verify_db" >/dev/null 2>&1 || true
    fi
    if [[ -f $partial_path ]]; then
        rm -f -- "$partial_path"
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Creating PostgreSQL custom-format backup..."
docker compose exec -T postgres sh -lc '
    pg_dump --format=custom --no-owner --no-privileges \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' > "$partial_path"
mv -- "$partial_path" "$dump_path"
chmod 600 -- "$dump_path"

docker compose exec -T postgres pg_restore --list \
    < "$dump_path" > "$restore_list_path"

docker compose exec -T postgres sh -lc '
    createdb -T template0 -U "$POSTGRES_USER" "$1"
' sh "$verify_db"
verify_db_created=1

docker compose exec -T postgres sh -lc '
    pg_restore --exit-on-error --no-owner --no-privileges \
        -U "$POSTGRES_USER" -d "$1"
' sh "$verify_db" < "$dump_path"

docker compose exec -T postgres sh -lc '
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At \
        -c "SELECT '\''episodes_total='\'' || count(*) FROM episodes" \
        -c "SELECT '\''episodes_synced='\'' || count(*) FILTER (WHERE graphiti_synced) FROM episodes" \
        -c "SELECT '\''public_tables='\'' || count(*) FROM information_schema.tables WHERE table_schema = '\''public'\'' AND table_type = '\''BASE TABLE'\''"
' sh "$verify_db" > "$verification_path"

docker compose exec -T postgres sh -lc '
    dropdb --if-exists --force -U "$POSTGRES_USER" "$1"
' sh "$verify_db" >/dev/null
verify_db_created=0

(
    cd -- "$backup_dir"
    sha256sum postgres.dump > postgres-SHA256SUMS
)
chmod 600 -- "$backup_dir"/*

echo "PostgreSQL backup created and scratch-restored: $backup_dir"
