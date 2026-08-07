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
    unset OPENAI_API_KEY_ENV OPENROUTER_API_KEY_ENV LANGSMITH_API_KEY_ENV
    unset SAGE_API_KEY_ENV SAGE_MCP_KEY_ENV SAGE_MCP_BACKEND_KEY_ENV
    unset GHCR_ACTOR_ENV GHCR_TOKEN_ENV SAGE_IMAGE_ENV
    unset TEXT_PROVIDER_ENV EMBEDDING_PROVIDER_ENV
    unset GRAPHITI_TEXT_PROVIDER_ENV GRAPHITI_EMBEDDING_PROVIDER_ENV
    unset GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV
    unset GRAPHITI_EXTRACTION_FALLBACK_MODEL_ENV
    unset OPENROUTER_CHAT_MODEL_ENV OPENROUTER_GRAPHITI_MODEL_ENV
    unset OPENROUTER_EMBEDDING_MODEL_ENV OLLAMA_BASE_URL_ENV
}
trap cleanup EXIT

read_secret() {
    local name=$1
    if ! IFS= read -r -d '' "$name"; then
        echo "Incomplete deployment input: $name" >&2
        exit 1
    fi
}

read_secret POSTGRES_USER_ENV
read_secret POSTGRES_PASSWORD_ENV
read_secret POSTGRES_DB_ENV
read_secret NEO4J_USER_ENV
read_secret NEO4J_PASSWORD_ENV
read_secret OPENAI_API_KEY_ENV
read_secret OPENROUTER_API_KEY_ENV
read_secret LANGSMITH_API_KEY_ENV
read_secret SAGE_API_KEY_ENV
read_secret SAGE_MCP_KEY_ENV
read_secret SAGE_MCP_BACKEND_KEY_ENV
read_secret GHCR_ACTOR_ENV
read_secret GHCR_TOKEN_ENV
read_secret SAGE_IMAGE_ENV
read_secret TEXT_PROVIDER_ENV
read_secret EMBEDDING_PROVIDER_ENV
read_secret GRAPHITI_TEXT_PROVIDER_ENV
read_secret GRAPHITI_EMBEDDING_PROVIDER_ENV
read_secret GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV
read_secret GRAPHITI_EXTRACTION_FALLBACK_MODEL_ENV
read_secret OPENROUTER_CHAT_MODEL_ENV
read_secret OPENROUTER_GRAPHITI_MODEL_ENV
read_secret OPENROUTER_EMBEDDING_MODEL_ENV
read_secret OLLAMA_BASE_URL_ENV

if [[ ! "$SAGE_IMAGE_ENV" =~ ^ghcr\.io/luminarimud/sage@sha256:[a-f0-9]{64}$ ]]; then
    echo "SAGE_IMAGE must be the expected GHCR repository at an immutable digest." >&2
    exit 1
fi

TEXT_PROVIDER_ENV=${TEXT_PROVIDER_ENV:-openai}
EMBEDDING_PROVIDER_ENV=${EMBEDDING_PROVIDER_ENV:-openai}
GRAPHITI_TEXT_PROVIDER_ENV=${GRAPHITI_TEXT_PROVIDER_ENV:-$TEXT_PROVIDER_ENV}
GRAPHITI_EMBEDDING_PROVIDER_ENV=${GRAPHITI_EMBEDDING_PROVIDER_ENV:-$EMBEDDING_PROVIDER_ENV}

validate_provider() {
    local selector=$1
    local provider=$2

    case "$provider" in
        ollama | openrouter | openai) ;;
        *)
            echo "$selector must be ollama, openrouter, or openai." >&2
            exit 1
            ;;
    esac
}

validate_provider TEXT_PROVIDER "$TEXT_PROVIDER_ENV"
validate_provider EMBEDDING_PROVIDER "$EMBEDDING_PROVIDER_ENV"
validate_provider GRAPHITI_TEXT_PROVIDER "$GRAPHITI_TEXT_PROVIDER_ENV"
validate_provider GRAPHITI_EMBEDDING_PROVIDER "$GRAPHITI_EMBEDDING_PROVIDER_ENV"
if [[ -n "$GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV" ]]; then
    validate_provider \
        GRAPHITI_EXTRACTION_FALLBACK_PROVIDER \
        "$GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV"
    if [[ -z "$GRAPHITI_EXTRACTION_FALLBACK_MODEL_ENV" ]]; then
        echo "GRAPHITI_EXTRACTION_FALLBACK_MODEL is required when fallback is selected." >&2
        exit 1
    fi
fi

needs_openai=
needs_openrouter=
needs_ollama=
selected_providers=(
    "$TEXT_PROVIDER_ENV"
    "$EMBEDDING_PROVIDER_ENV"
    "$GRAPHITI_TEXT_PROVIDER_ENV"
    "$GRAPHITI_EMBEDDING_PROVIDER_ENV"
)
if [[ -n "$GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV" ]]; then
    selected_providers+=("$GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV")
fi
for provider in "${selected_providers[@]}"; do
    case "$provider" in
        openai) needs_openai=1 ;;
        openrouter) needs_openrouter=1 ;;
        ollama) needs_ollama=1 ;;
    esac
done

if [[ -n "$needs_openai" && -z "$OPENAI_API_KEY_ENV" ]]; then
    echo "OPENAI_API_KEY is required by the selected production providers." >&2
    exit 1
fi
if [[ -n "$needs_openrouter" && -z "$OPENROUTER_API_KEY_ENV" ]]; then
    echo "OPENROUTER_API_KEY is required by the selected production providers." >&2
    exit 1
fi
if [[ "$TEXT_PROVIDER_ENV" == "openrouter" && -z "$OPENROUTER_CHAT_MODEL_ENV" ]]; then
    echo "OPENROUTER_CHAT_MODEL is required when OpenRouter provides application text." >&2
    exit 1
fi
if [[ "$GRAPHITI_TEXT_PROVIDER_ENV" == "openrouter" \
    && -z "$OPENROUTER_GRAPHITI_MODEL_ENV" \
    && -z "$OPENROUTER_CHAT_MODEL_ENV" ]]; then
    echo "OPENROUTER_GRAPHITI_MODEL or OPENROUTER_CHAT_MODEL is required for Graphiti text." >&2
    exit 1
fi
if [[ ( "$EMBEDDING_PROVIDER_ENV" == "openrouter" \
    || "$GRAPHITI_EMBEDDING_PROVIDER_ENV" == "openrouter" ) \
    && -z "$OPENROUTER_EMBEDDING_MODEL_ENV" ]]; then
    echo "OPENROUTER_EMBEDDING_MODEL is required for OpenRouter embeddings." >&2
    exit 1
fi
if [[ -n "$needs_ollama" ]]; then
    if [[ ! "$OLLAMA_BASE_URL_ENV" =~ ^https?://[^[:space:]]+$ ]]; then
        echo "OLLAMA_BASE_URL must be an explicit HTTP(S) URL for production Ollama use." >&2
        exit 1
    fi
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
    "$transfer_dir/docker-compose.openai.yml" \
    "$deploy_dir/docker-compose.openai.yml"
install -m 0600 \
    "$transfer_dir/docker-compose.openrouter.yml" \
    "$deploy_dir/docker-compose.openrouter.yml"
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
if [[ -n "$needs_openai" ]]; then
    write_secret openai_api_key "$OPENAI_API_KEY_ENV"
else
    rm -f -- "$deploy_dir/secrets/openai_api_key"
fi
if [[ -n "$needs_openrouter" ]]; then
    write_secret openrouter_api_key "$OPENROUTER_API_KEY_ENV"
else
    rm -f -- "$deploy_dir/secrets/openrouter_api_key"
fi
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
    write_env LLM_PROVIDER "$TEXT_PROVIDER_ENV"
    write_env TEXT_PROVIDER "$TEXT_PROVIDER_ENV"
    write_env EMBEDDING_PROVIDER "$EMBEDDING_PROVIDER_ENV"
    write_env GRAPHITI_PROVIDER "$GRAPHITI_TEXT_PROVIDER_ENV"
    write_env GRAPHITI_TEXT_PROVIDER "$GRAPHITI_TEXT_PROVIDER_ENV"
    write_env GRAPHITI_EMBEDDING_PROVIDER "$GRAPHITI_EMBEDDING_PROVIDER_ENV"
    write_env \
        GRAPHITI_EXTRACTION_FALLBACK_PROVIDER \
        "$GRAPHITI_EXTRACTION_FALLBACK_PROVIDER_ENV"
    write_env \
        GRAPHITI_EXTRACTION_FALLBACK_MODEL \
        "$GRAPHITI_EXTRACTION_FALLBACK_MODEL_ENV"
    write_env OPENROUTER_CHAT_MODEL "$OPENROUTER_CHAT_MODEL_ENV"
    write_env OPENROUTER_GRAPHITI_MODEL "$OPENROUTER_GRAPHITI_MODEL_ENV"
    write_env OPENROUTER_EMBEDDING_MODEL "$OPENROUTER_EMBEDDING_MODEL_ENV"
    write_env OLLAMA_BASE_URL "$OLLAMA_BASE_URL_ENV"
    if [[ "$EMBEDDING_PROVIDER_ENV" == "ollama" ]]; then
        echo "USE_LOCAL_EMBEDDINGS='true'"
    else
        echo "USE_LOCAL_EMBEDDINGS='false'"
    fi
    if [[ "$EMBEDDING_PROVIDER_ENV" == "openai" ]]; then
        echo "USE_OPENAI_EMBEDDINGS='true'"
    else
        echo "USE_OPENAI_EMBEDDINGS='false'"
    fi
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
compose_files=(-f docker-compose.yml)
if [[ -n "$needs_openai" ]]; then
    compose_files+=(-f docker-compose.openai.yml)
fi
if [[ -n "$needs_openrouter" ]]; then
    compose_files+=(-f docker-compose.openrouter.yml)
fi
"${compose_cmd[@]}" "${compose_files[@]}" -p "$compose_project" pull
"${compose_cmd[@]}" "${compose_files[@]}" -p "$compose_project" up -d --remove-orphans

for attempt in {1..60}; do
    if "$curl_bin" --fail --silent --show-error \
        --connect-timeout 5 --max-time 10 \
        http://127.0.0.1:8003/api/v1/health >/dev/null; then
        echo "Deployment health check passed."
        exit 0
    fi
    if [[ "$attempt" == 60 ]]; then
        echo "Services did not become healthy within two minutes." >&2
        "${compose_cmd[@]}" "${compose_files[@]}" -p "$compose_project" ps >&2
        exit 1
    fi
    sleep 2
done
