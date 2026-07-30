#!/usr/bin/env bash
# Run the API and MCP servers as direct container children.

set -Eeuo pipefail
umask 077

service_pids=()

# Called indirectly by the EXIT trap.
# shellcheck disable=SC2329
shutdown_services() {
    local pid

    trap - EXIT INT TERM HUP
    for pid in "${service_pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    for pid in "${service_pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

trap shutdown_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

python -m uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port "${API_PORT:-8003}" \
    --log-level "${UVICORN_LOG_LEVEL:-info}" &
service_pids+=("$!")

python -m uvicorn src.mcp.server:app \
    --host 0.0.0.0 \
    --port "${MCP_PORT:-8004}" \
    --log-level "${UVICORN_LOG_LEVEL:-info}" &
service_pids+=("$!")

set +e
wait -n "${service_pids[@]}"
status=$?
set -e
exit "$status"
