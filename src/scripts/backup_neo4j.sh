#!/usr/bin/env bash
# Backup the Neo4j database from the running docker container.
# Usage: ./scripts/backup_neo4j.sh [container_name]

set -euo pipefail

CONTAINER_NAME="${1:-luminari-neo4j}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR%/scripts}/backups/neo4j"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
CONTAINER_TMP_DIR="/tmp/neo4j-backups"
DUMP_NAME="neo4j.dump"
LOCAL_DUMP_PATH="${BACKUP_DIR}/neo4j-${TIMESTAMP}.dump"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "Neo4j container '${CONTAINER_NAME}' is not running." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "Creating dump inside container '${CONTAINER_NAME}'..."
docker exec "${CONTAINER_NAME}" bash -lc "mkdir -p '${CONTAINER_TMP_DIR}'"
docker exec "${CONTAINER_NAME}" bash -lc "neo4j-admin database dump neo4j --to-path='${CONTAINER_TMP_DIR}' --overwrite"

echo "Copying dump to host: ${LOCAL_DUMP_PATH}"
docker cp "${CONTAINER_NAME}:${CONTAINER_TMP_DIR}/${DUMP_NAME}" "${LOCAL_DUMP_PATH}"

echo "Cleaning up temporary files inside container..."
docker exec "${CONTAINER_NAME}" bash -lc "rm -f '${CONTAINER_TMP_DIR}/${DUMP_NAME}'"

echo "Backup complete: ${LOCAL_DUMP_PATH}"
