#!/bin/sh
# Resolve and optionally pull only the Ollama models selected by active capabilities.

set -eu

action=${1:-list}
records=

lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

validate_text_provider() {
    name=$1
    provider=$2
    case "$provider" in
        ollama | openrouter | openai) ;;
        *)
            echo "$name must be ollama, openrouter, or openai." >&2
            exit 2
            ;;
    esac
}

validate_embedding_provider() {
    name=$1
    provider=$2
    case "$provider" in
        ollama | openrouter | openai | sentence-transformers) ;;
        *)
            echo "$name is not a supported embedding provider." >&2
            exit 2
            ;;
    esac
}

validate_model() {
    name=$1
    model=$2
    case "$model" in
        "" | *[!A-Za-z0-9._:/+@-]* | [!A-Za-z0-9]*)
            echo "$name is missing or invalid." >&2
            exit 2
            ;;
    esac
}

add_model() {
    role=$1
    model=$2
    name=$3
    validate_model "$name" "$model"
    record="${role}:${model}"
    case " $records " in
        *" $record "*) ;;
        *) records="${records:+$records }$record" ;;
    esac
}

llm_provider=$(lower "${LLM_PROVIDER:-ollama}")
text_provider=$(lower "${TEXT_PROVIDER:-$llm_provider}")
validate_text_provider TEXT_PROVIDER "$text_provider"

if [ -n "${EMBEDDING_PROVIDER:-}" ]; then
    embedding_provider=$(lower "$EMBEDDING_PROVIDER")
else
    use_local=$(lower "${USE_LOCAL_EMBEDDINGS:-false}")
    case "$use_local" in
        1 | true | yes | on)
            if [ "$llm_provider" = ollama ]; then
                embedding_provider=ollama
            else
                embedding_provider=sentence-transformers
            fi
            ;;
        0 | false | no | off) embedding_provider=openai ;;
        *)
            echo "USE_LOCAL_EMBEDDINGS must be a boolean." >&2
            exit 2
            ;;
    esac
fi
validate_embedding_provider EMBEDDING_PROVIDER "$embedding_provider"

if [ -n "${GRAPHITI_TEXT_PROVIDER:-}" ]; then
    graphiti_text_provider=$(lower "$GRAPHITI_TEXT_PROVIDER")
elif [ -n "${GRAPHITI_PROVIDER:-}" ]; then
    graphiti_text_provider=$(lower "$GRAPHITI_PROVIDER")
else
    graphiti_text_provider=$text_provider
fi
validate_text_provider GRAPHITI_TEXT_PROVIDER "$graphiti_text_provider"

if [ -n "${GRAPHITI_EMBEDDING_PROVIDER:-}" ]; then
    graphiti_embedding_provider=$(lower "$GRAPHITI_EMBEDDING_PROVIDER")
elif [ -n "${GRAPHITI_PROVIDER:-}" ]; then
    graphiti_embedding_provider=$(lower "$GRAPHITI_PROVIDER")
else
    graphiti_embedding_provider=$embedding_provider
fi
validate_embedding_provider GRAPHITI_EMBEDDING_PROVIDER "$graphiti_embedding_provider"

fallback_provider=$(lower "${GRAPHITI_EXTRACTION_FALLBACK_PROVIDER:-}")
if [ -n "$fallback_provider" ]; then
    validate_text_provider GRAPHITI_EXTRACTION_FALLBACK_PROVIDER "$fallback_provider"
    if [ -z "${GRAPHITI_EXTRACTION_FALLBACK_MODEL:-}" ]; then
        echo "GRAPHITI_EXTRACTION_FALLBACK_MODEL is required when fallback is selected." >&2
        exit 2
    fi
fi

ollama_chat_model=${OLLAMA_CHAT_MODEL:-qwen2.5:7b}
ollama_creative_model=${OLLAMA_CREATIVE_MODEL:-$ollama_chat_model}
ollama_reasoning_model=${OLLAMA_REASONING_MODEL:-qwen2.5:3b}
ollama_extraction_model=${OLLAMA_EXTRACTION_MODEL:-$ollama_chat_model}
ollama_tools_model=${OLLAMA_TOOLS_MODEL:-$ollama_chat_model}
ollama_embedding_model=${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}

if [ "$text_provider" = ollama ]; then
    add_model text "$ollama_chat_model" OLLAMA_CHAT_MODEL
    add_model text "$ollama_creative_model" OLLAMA_CREATIVE_MODEL
    add_model text "$ollama_reasoning_model" OLLAMA_REASONING_MODEL
    add_model text "$ollama_extraction_model" OLLAMA_EXTRACTION_MODEL
    add_model text "$ollama_tools_model" OLLAMA_TOOLS_MODEL
fi
if [ "$graphiti_text_provider" = ollama ]; then
    add_model text "${GRAPHITI_TEXT_MODEL:-$ollama_extraction_model}" GRAPHITI_TEXT_MODEL
fi
if [ "$fallback_provider" = ollama ]; then
    add_model text "$GRAPHITI_EXTRACTION_FALLBACK_MODEL" GRAPHITI_EXTRACTION_FALLBACK_MODEL
fi
if [ "$embedding_provider" = ollama ]; then
    add_model embedding "$ollama_embedding_model" OLLAMA_EMBEDDING_MODEL
fi
if [ "$graphiti_embedding_provider" = ollama ]; then
    add_model \
        embedding \
        "${GRAPHITI_EMBEDDING_MODEL:-$ollama_embedding_model}" \
        GRAPHITI_EMBEDDING_MODEL
fi

case "$action" in
    list)
        for record in $records; do
            printf '%s\n' "$record"
        done
        ;;
    pull)
        if [ -z "$records" ]; then
            echo "[ollama-init] No Ollama capability selected; skipping model pulls."
            exit 0
        fi
        if ! command -v ollama >/dev/null 2>&1; then
            echo "The ollama CLI is required for model pulls." >&2
            exit 2
        fi
        pulled=
        for record in $records; do
            model=${record#*:}
            case " $pulled " in
                *" $model "*) continue ;;
            esac
            echo "[ollama-init] Ensuring model is installed: $model"
            ollama pull "$model"
            pulled="${pulled:+$pulled }$model"
        done
        ;;
    *)
        echo "Usage: ollama_model_profile.sh [list|pull]" >&2
        exit 2
        ;;
esac
