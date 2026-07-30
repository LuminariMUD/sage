#!/usr/bin/env bash
# Run the episodic stable_id migration inside the API container.
# Usage: ./scripts/run_neo4j_stable_id_migration.sh [--dry-run|--verify] [container]

set -euo pipefail

MODE=""
CONTAINER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--verify)
      MODE="$1"
      shift
      ;;
    *)
      CONTAINER="$1"
      shift
      ;;
  esac
done

CONTAINER=${CONTAINER:-luminari-sage-api-1}

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Container '$CONTAINER' is not running." >&2
  exit 1
fi

CMD=("docker" "exec" "-it" "$CONTAINER" "python" "/app/scripts/migrate_episodic_stable_ids.py")

if [[ -n "$MODE" ]]; then
  CMD+=("$MODE")
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"
