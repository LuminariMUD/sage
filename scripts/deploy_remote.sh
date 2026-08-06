#!/usr/bin/env bash
# Run the production Compose deployment from NUL-delimited stdin values.

set -Eeuo pipefail
umask 077

transfer_dir=${SAGE_TRANSFER_DIR:-/tmp/luminari-sage-deploy}
deploy_dir=${SAGE_DEPLOY_DIR:-"$HOME/luminari-sage"}
compose_project=luminari-sage
docker_bin=${SAGE_DOCKER_BIN:-docker}
curl_bin=${SAGE_CURL_BIN:-curl}
secret_temps=()

cleanup() {
    if [[ -n "${registry_logged_in:-}" ]]; then
        "${docker_cmd[@]}" logout ghcr.io >/dev/null 2>&1 || true
    fi
    if [[ -n "${env_tmp:-}" ]]; then
        rm -f -- "$env_tmp"
    fi
    if (( ${#secret_temps[@]} )); then
        for secret_tmp in "${secret_temps[@]}"; do
            rm -f -- "$secret_tmp"
        done
    fi
    rm -rf -- "$transfer_dir"
    unset POSTGRES_USER_ENV POSTGRES_PASSWORD_ENV POSTGRES_DB_ENV
    unset NEO4J_USER_ENV NEO4J_PASSWORD_ENV
    unset OPENAI_API_KEY_ENV LANGSMITH_API_KEY_ENV
    unset SAGE_API_KEY_ENV SAGE_MCP_KEY_ENV SAGE_MCP_BACKEND_KEY_ENV
    unset GHCR_ACTOR_ENV GHCR_TOKEN_ENV SAGE_IMAGE_ENV
}
trap cleanup EXIT

read_secret() {
    local name=$1
    if ! IFS= read -r -d '' "$name"; then
        echo "Incomplete deployment input: $name" >&2
        exit 1
    fi
    export "${name?}"
}

read_secret POSTGRES_USER_ENV
read_secret POSTGRES_PASSWORD_ENV
read_secret POSTGRES_DB_ENV
read_secret NEO4J_USER_ENV
read_secret NEO4J_PASSWORD_ENV
read_secret OPENAI_API_KEY_ENV
read_secret LANGSMITH_API_KEY_ENV
read_secret SAGE_API_KEY_ENV
read_secret SAGE_MCP_KEY_ENV
read_secret SAGE_MCP_BACKEND_KEY_ENV
read_secret GHCR_ACTOR_ENV
read_secret GHCR_TOKEN_ENV
read_secret SAGE_IMAGE_ENV

if [[ ! "$SAGE_IMAGE_ENV" =~ ^ghcr\.io/luminarimud/sage@sha256:[a-f0-9]{64}$ ]]; then
    echo "SAGE_IMAGE must be the expected GHCR repository at an immutable digest." >&2
    exit 1
fi

expected_uid=${SAGE_EXPECTED_UID:-1013}
if [[ ! "$expected_uid" =~ ^[0-9]+$ ]] || (( $(id -u) != expected_uid )); then
    echo "Deployment user must have UID $expected_uid so owner-only secrets are readable only by the application UID." >&2
    exit 1
fi

if [[ -n "${SAGE_DOCKER_BIN:-}" ]]; then
    # An explicit binary is used by the isolated deployment contract test and
    # by operators who provide a Docker-compatible wrapper.
    docker_cmd=("$docker_bin")
elif groups | grep -qw docker; then
    docker_cmd=("$docker_bin")
elif sudo -n true 2>/dev/null; then
    docker_cmd=(sudo "$docker_bin")
else
    echo "Deployment user needs Docker group access or passwordless sudo." >&2
    exit 1
fi
compose_cmd=("${docker_cmd[@]}" compose)

install -d -m 0700 "$deploy_dir"
install -d -m 0700 "$deploy_dir/logs" "$deploy_dir/backups"
install -d -m 0700 "$deploy_dir/backups/postgres" "$deploy_dir/backups/neo4j"
install -d -m 0700 "$deploy_dir/schemas"
install -d -m 0700 "$deploy_dir/secrets"
install -m 0600 "$transfer_dir/docker-compose.yml" "$deploy_dir/docker-compose.yml"
install -m 0600 \
    "$transfer_dir/postgresql_schema.sql" \
    "$deploy_dir/schemas/postgresql_schema.sql"

write_env() {
    local name=$1
    local value=$2
    if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        echo "Deployment value contains a forbidden newline: $name" >&2
        exit 1
    fi
    value=${value//\'/\\\'}
    printf "%s='%s'\n" "$name" "$value"
}

write_secret() {
    local name=$1
    local value=$2
    local secret_tmp

    if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        echo "Deployment secret contains a forbidden newline: $name" >&2
        exit 1
    fi
    secret_tmp=$(mktemp "$deploy_dir/secrets/.${name}.XXXXXX")
    secret_temps+=("$secret_tmp")
    chmod 0600 "$secret_tmp"
    printf '%s' "$value" > "$secret_tmp"
    mv -f -- "$secret_tmp" "$deploy_dir/secrets/$name"
}

write_secret postgres_password "$POSTGRES_PASSWORD_ENV"
write_secret neo4j_auth "${NEO4J_USER_ENV}/${NEO4J_PASSWORD_ENV}"
write_secret neo4j_password "$NEO4J_PASSWORD_ENV"
write_secret openai_api_key "$OPENAI_API_KEY_ENV"
write_secret langsmith_api_key "$LANGSMITH_API_KEY_ENV"
write_secret sage_api_key "$SAGE_API_KEY_ENV"
write_secret sage_mcp_key "$SAGE_MCP_KEY_ENV"
write_secret sage_mcp_backend_key "$SAGE_MCP_BACKEND_KEY_ENV"

env_tmp=$deploy_dir/.env.new
: > "$env_tmp"
chmod 0600 "$env_tmp"
{
    write_env POSTGRES_USER "$POSTGRES_USER_ENV"
    write_env POSTGRES_DB "$POSTGRES_DB_ENV"
    write_env NEO4J_USER "$NEO4J_USER_ENV"
    write_env SAGE_IMAGE "$SAGE_IMAGE_ENV"
    echo "DISABLE_AUTH='false'"
    echo "LANGCHAIN_TRACING_V2='false'"
    echo "ALLOWED_ORIGINS='https://luminarimud.com'"
    echo "ALLOWED_HOSTS='luminarimud.com,localhost,127.0.0.1,api,luminari-api'"
} >> "$env_tmp"
mv -f -- "$env_tmp" "$deploy_dir/.env"

printf '%s' "$GHCR_TOKEN_ENV" |
    "${docker_cmd[@]}" login ghcr.io -u "$GHCR_ACTOR_ENV" --password-stdin
registry_logged_in=1

cd "$deploy_dir"
"${compose_cmd[@]}" -p "$compose_project" pull
"${compose_cmd[@]}" -p "$compose_project" up -d --remove-orphans

for attempt in {1..60}; do
    if "$curl_bin" --fail --silent --show-error \
        --connect-timeout 5 --max-time 10 \
        http://127.0.0.1:8003/api/v1/health >/dev/null; then
        echo "Deployment health check passed."
        exit 0
    fi
    if [[ "$attempt" == 60 ]]; then
        echo "Services did not become healthy within two minutes." >&2
        "${compose_cmd[@]}" -p "$compose_project" ps >&2
        exit 1
    fi
    sleep 2
done
