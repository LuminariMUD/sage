#!/usr/bin/env bash
# Pull only the Ollama models selected by the active capability profile.

set -Eeuo pipefail

echo "Resolving active Ollama model requirements..."
model_records=$(
    docker compose run --rm --no-deps --entrypoint /bin/sh ollama-init \
        /usr/local/bin/ollama_model_profile.sh list
)

if [[ -z "$model_records" ]]; then
    echo "No Ollama capability is selected; no local model is required."
    exit 0
fi

echo "Selected local models:"
while IFS= read -r record; do
    [[ -n "$record" ]] && printf '  - %s\n' "$record"
done <<< "$model_records"

docker compose run --rm ollama-init

echo "Installed Ollama models:"
docker compose exec -T ollama ollama list
echo "Ollama model setup is complete."
