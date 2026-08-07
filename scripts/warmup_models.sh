#!/usr/bin/env bash
# Warm only active Ollama capabilities, using the embedding endpoint for vectors.

set -Eeuo pipefail

model_records=$(
    docker compose run --rm --no-deps --entrypoint /bin/sh ollama-init \
        /usr/local/bin/ollama_model_profile.sh list
)

if [[ -z "$model_records" ]]; then
    echo "No Ollama capability is selected; warmup is not required."
    exit 0
fi

if [[ $(docker inspect --format '{{.State.Running}}' luminari-ollama 2>/dev/null || true) != true ]]; then
    echo "Ollama is not running. Start it with: docker compose up -d ollama" >&2
    exit 1
fi

ollama_endpoint=$(docker compose port ollama 11434 | head -n 1)
if [[ -z "$ollama_endpoint" ]]; then
    echo "Could not resolve the published Ollama endpoint." >&2
    exit 1
fi

while IFS= read -r record; do
    [[ -n "$record" ]] || continue
    role=${record%%:*}
    model=${record#*:}
    case "$role" in
        text)
            echo "Warming text model: $model"
            docker exec luminari-ollama ollama run "$model" "Reply with ready." >/dev/null
            ;;
        embedding)
            echo "Warming embedding model through /api/embed: $model"
            payload=$(printf '{"model":"%s","input":"readiness probe","truncate":false}' "$model")
            curl --fail --silent --show-error --max-time 120 \
                -H 'Content-Type: application/json' \
                --data-binary "$payload" \
                "http://${ollama_endpoint}/api/embed" >/dev/null
            ;;
        *)
            echo "Unexpected Ollama model role: $role" >&2
            exit 2
            ;;
    esac
done <<< "$model_records"

echo "Active Ollama models are warm:"
docker exec luminari-ollama ollama ps
