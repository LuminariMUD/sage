#!/usr/bin/env bash
# Create and consistency-check offline Neo4j Community dumps.

set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/../.." && pwd)
container_name=${1:-luminari-neo4j}
requested_destination=${2:-"backups/neo4j-$(date -u +%Y%m%dT%H%M%SZ)"}

if [[ ${CONFIRM_NEO4J_OFFLINE_BACKUP:-} != 1 ]]; then
    echo "Set CONFIRM_NEO4J_OFFLINE_BACKUP=1 to allow the required brief outage." >&2
    exit 2
fi
if [[ ! $container_name =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Invalid Neo4j container name." >&2
    exit 2
fi

if [[ $requested_destination = /* ]]; then
    backup_dir=$(realpath -m -- "$requested_destination")
else
    backup_dir=$(realpath -m -- "$project_dir/$requested_destination")
fi
case "$backup_dir" in
    "$project_dir"/backups/*) ;;
    *)
        echo "Neo4j backup destination must be below $project_dir/backups/." >&2
        exit 2
        ;;
esac

if ! docker inspect "$container_name" >/dev/null 2>&1; then
    echo "Neo4j container does not exist: $container_name" >&2
    exit 1
fi
if [[ $(docker inspect --format '{{.State.Running}}' "$container_name") != true ]]; then
    echo "Neo4j container is not running: $container_name" >&2
    exit 1
fi

mkdir -p -- "$backup_dir"
chmod 700 -- "$backup_dir"
outputs=(
    neo4j.dump
    system.dump
    neo4j-restore-info.txt
    system-restore-info.txt
    neo4j-consistency-check.txt
    system-consistency-check.txt
    neo4j-SHA256SUMS
)
for output in "${outputs[@]}"; do
    if [[ -e $backup_dir/$output ]]; then
        echo "Refusing to overwrite existing backup artifact: $backup_dir/$output" >&2
        exit 1
    fi
done

image=$(docker inspect --format '{{.Config.Image}}' "$container_name")
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
container_dump_dir="/data/dumps/sage-offline-$timestamp-$$"
restart_required=0
dump_dir_created=0

remove_dump_dir() {
    if [[ $dump_dir_created != 1 ]]; then
        return 0
    fi

    docker run --rm \
        --network none \
        --user neo4j \
        --volumes-from "$container_name" \
        --entrypoint bash \
        "$image" \
        -lc '
            set -Eeuo pipefail
            target=$1
            case "$target" in
                /data/dumps/sage-offline-*) ;;
                *)
                    echo "Refusing unsafe cleanup target." >&2
                    exit 2
                    ;;
            esac
            if [[ -e $target ]]; then
                find "$target" -depth -mindepth 1 -delete
                rmdir -- "$target"
            fi
        ' bash "$container_dump_dir"
    dump_dir_created=0
}

cleanup() {
    status=$?
    trap - EXIT INT TERM

    if ! remove_dump_dir; then
        echo "Warning: temporary Neo4j dump cleanup failed." >&2
        if [[ $status == 0 ]]; then
            status=1
        fi
    fi
    if [[ $restart_required == 1 ]]; then
        echo "Restarting Neo4j container after offline backup attempt..." >&2
        if ! docker start "$container_name" >/dev/null; then
            echo "Failed to restart Neo4j container: $container_name" >&2
            status=1
        fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Stopping Neo4j for a consistent Community Edition dump..."
restart_required=1
docker stop --time 60 "$container_name" >/dev/null

dump_dir_created=1
docker run --rm \
    --network none \
    --user neo4j \
    --volumes-from "$container_name" \
    --entrypoint bash \
    "$image" \
    -lc '
        set -Eeuo pipefail
        umask 077
        target=$1
        mkdir -p -- "$target"
        chmod 700 -- "$target"
        neo4j-admin database dump neo4j \
            --to-path="$target" \
            --overwrite-destination=true
        neo4j-admin database dump system \
            --to-path="$target" \
            --overwrite-destination=true
    ' bash "$container_dump_dir"

docker run --rm \
    --network none \
    --user neo4j \
    --volumes-from "$container_name" \
    --entrypoint neo4j-admin \
    "$image" \
    database load --info --from-path="$container_dump_dir" neo4j \
    > "$backup_dir/neo4j-restore-info.txt"
docker run --rm \
    --network none \
    --user neo4j \
    --volumes-from "$container_name" \
    --entrypoint neo4j-admin \
    "$image" \
    database load --info --from-path="$container_dump_dir" system \
    > "$backup_dir/system-restore-info.txt"

docker run --rm \
    --network none \
    --user neo4j \
    --volumes-from "$container_name" \
    --entrypoint neo4j-admin \
    "$image" \
    database check \
    --from-path="$container_dump_dir/neo4j.dump" \
    --temp-path="$container_dump_dir/check-neo4j" \
    --report-path="$container_dump_dir/neo4j-consistency.report" \
    --max-off-heap-memory=512m \
    --threads=2 \
    neo4j \
    > "$backup_dir/neo4j-consistency-check.txt"
docker run --rm \
    --network none \
    --user neo4j \
    --volumes-from "$container_name" \
    --entrypoint neo4j-admin \
    "$image" \
    database check \
    --from-path="$container_dump_dir/system.dump" \
    --temp-path="$container_dump_dir/check-system" \
    --report-path="$container_dump_dir/system-consistency.report" \
    --max-off-heap-memory=512m \
    --threads=2 \
    system \
    > "$backup_dir/system-consistency-check.txt"

docker cp "$container_name:$container_dump_dir/neo4j.dump" \
    "$backup_dir/neo4j.dump" >/dev/null
docker cp "$container_name:$container_dump_dir/system.dump" \
    "$backup_dir/system.dump" >/dev/null

remove_dump_dir
docker start "$container_name" >/dev/null
restart_required=0

health=starting
for _ in $(seq 1 60); do
    health=$(docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$container_name")
    if [[ $health == healthy || $health == running ]]; then
        break
    fi
    sleep 1
done
if [[ $health != healthy && $health != running ]]; then
    echo "Neo4j did not become healthy after restart (status: $health)." >&2
    exit 1
fi

(
    cd -- "$backup_dir"
    sha256sum neo4j.dump system.dump > neo4j-SHA256SUMS
)
chmod 600 -- "$backup_dir"/*

echo "Neo4j offline dumps created and consistency-checked: $backup_dir"
