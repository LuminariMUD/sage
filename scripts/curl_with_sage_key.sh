#!/usr/bin/env bash
# Invoke curl without placing SAGE_API_KEY in the process argument list.

set -Eeuo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/.." && pwd)

api_key=${SAGE_API_KEY:-}
if [[ -z "$api_key" && -f "$project_dir/.env" ]]; then
    IFS= read -r -d '' api_key < <(
        python3 - "$project_dir/.env" <<'PY'
import sys

from dotenv import dotenv_values

value = dotenv_values(sys.argv[1]).get("SAGE_API_KEY") or ""
sys.stdout.buffer.write(value.encode() + b"\0")
PY
    )
fi

if [[ -z "$api_key" ]]; then
    echo "SAGE_API_KEY is not configured in the environment or .env." >&2
    exit 1
fi

# curl's config format uses backslash escapes inside quoted header values.
escaped_key=${api_key//\\/\\\\}
escaped_key=${escaped_key//\"/\\\"}

curl --config <(printf 'header = "X-API-Key: %s"\n' "$escaped_key") "$@"
