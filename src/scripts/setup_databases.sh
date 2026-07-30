#!/usr/bin/env bash
# Bootstrap the local PostgreSQL and Neo4j services through Docker Compose.

set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/../.." && pwd)
cd "$project_dir"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Docker with the Compose plugin is required." >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "Create .env from .env.example and configure unique credentials first." >&2
    exit 1
fi

# Parse only the values this script needs. python-dotenv treats .env as data,
# unlike sourcing or xargs-based loaders, so shell syntax in a value is never
# executed. NUL delimiters preserve spaces and metacharacters.
while IFS= read -r -d '' name && IFS= read -r -d '' value; do
    printf -v "$name" '%s' "$value"
    export "${name?}"
done < <(
    python3 - "$project_dir/.env" <<'PY'
import os
import sys

from dotenv import dotenv_values

names = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
)
values = dotenv_values(sys.argv[1])
for name in names:
    value = os.environ.get(name, values.get(name) or "")
    sys.stdout.buffer.write(name.encode() + b"\0" + value.encode() + b"\0")
PY
)

for name in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB NEO4J_USER NEO4J_PASSWORD; do
    if [[ -z "${!name:-}" ]]; then
        echo "Required configuration is missing: $name" >&2
        exit 1
    fi
done

echo "Starting local database services..."
docker compose up -d --wait postgres neo4j

echo "Applying PostgreSQL schema..."
docker compose exec -T postgres \
    psql --set ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    < schemas/postgresql_schema.sql

echo "Applying Neo4j schema..."
export NEO4J_USERNAME=$NEO4J_USER
docker compose exec -T \
    --env NEO4J_USERNAME \
    --env NEO4J_PASSWORD \
    neo4j cypher-shell --non-interactive \
    < schemas/neo4j_schema.cypher

echo "Database setup complete."
