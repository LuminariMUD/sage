#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

load_secret_file() {
    local name=$1
    local file_var=${name}_FILE
    local secret_file=${!file_var:-}
    local value
    local -a secret_lines=()

    if [[ -z "$secret_file" ]]; then
        return
    fi
    if [[ ! -f "$secret_file" || ! -r "$secret_file" ]]; then
        echo "Configured secret file is not readable: $file_var" >&2
        exit 1
    fi

    mapfile -t secret_lines < "$secret_file"
    value=${secret_lines[0]:-}
    if (( ${#secret_lines[@]} > 1 )) || [[ "$value" == *$'\r'* ]]; then
        echo "Configured secret contains a forbidden newline: $file_var" >&2
        exit 1
    fi
    printf -v "$name" '%s' "$value"
    export "${name?}"
    unset "$file_var"
}

for secret_name in \
    POSTGRES_PASSWORD \
    NEO4J_PASSWORD \
    OPENAI_API_KEY \
    OPENROUTER_API_KEY \
    LANGSMITH_API_KEY \
    SAGE_API_KEY \
    SAGE_MCP_KEY \
    SAGE_MCP_BACKEND_KEY
do
    load_secret_file "$secret_name"
done

# Refuse to broaden host-volume permissions from inside the container.
if [ -d "/app/lore" ] && [ ! -r "/app/lore" ]; then
    echo "Lore directory is not readable by the application user." >&2
    echo "Grant UID 1013 read access on the host, then restart the service." >&2
    exit 1
fi

# Start the application
exec "$@"
