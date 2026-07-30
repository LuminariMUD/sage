#!/usr/bin/env bash
# Validate the local LLM deployment without displaying or passing credentials.

set -uo pipefail

exit_code=0

container_running() {
    docker ps --format '{{.Names}}' | grep -qx "$1"
}

echo "🔍 Validating Local LLM Migration..."
echo ""

echo "1. Checking Ollama service..."
if container_running luminari-ollama; then
    echo "  ✅ Ollama running"
else
    echo "  ❌ Ollama not running"
    exit_code=1
fi

echo "2. Checking models..."
models=$(docker exec luminari-ollama ollama list 2>/dev/null | tail -n +2 | wc -l)
if [[ "$models" -ge 3 ]]; then
    echo "  ✅ Models installed: $models"
    docker exec luminari-ollama ollama list | tail -n +2 | head -5
else
    echo "  ❌ Missing models (need at least 3)"
    exit_code=1
fi

echo "3. Checking PostgreSQL..."
if container_running luminari-postgres; then
    echo "  ✅ PostgreSQL running"
    postgres_user=$(docker exec luminari-postgres sh -c 'printf %s "$POSTGRES_USER"')
    postgres_db=$(docker exec luminari-postgres sh -c 'printf %s "$POSTGRES_DB"')
    episodes=$(
        docker exec luminari-postgres \
            psql -U "$postgres_user" -d "$postgres_db" -tAc \
            "SELECT COUNT(*) FROM episodes;" 2>/dev/null || echo "0"
    )
    echo "  📊 Episodes in database: $episodes"

    if [[ "$episodes" -gt 0 ]]; then
        embeddings=$(
            docker exec luminari-postgres \
                psql -U "$postgres_user" -d "$postgres_db" -tAc \
                "SELECT COUNT(*) FROM episodes WHERE embedding IS NOT NULL;" \
                2>/dev/null || echo "0"
        )
        percent=$((embeddings * 100 / episodes))
        if [[ "$embeddings" -eq "$episodes" ]]; then
            echo "  ✅ All episodes have embeddings ($embeddings/$episodes)"
        elif [[ "$percent" -ge 90 ]]; then
            echo "  ⚠️  Most episodes have embeddings ($embeddings/$episodes - ${percent}%)"
        else
            echo "  ⚠️  Some episodes missing embeddings ($embeddings/$episodes - ${percent}%)"
        fi
    fi
else
    echo "  ❌ PostgreSQL not running"
    exit_code=1
fi

echo "4. Checking Neo4j knowledge graph..."
if container_running luminari-neo4j; then
    echo "  ✅ Neo4j running"
    entities=$(
        docker exec luminari-neo4j bash -c '
            if [[ -n "${NEO4J_AUTH_FILE:-}" ]]; then
                auth=$(< "$NEO4J_AUTH_FILE")
            else
                auth=${NEO4J_AUTH:-}
            fi
            export NEO4J_USERNAME=${auth%%/*}
            export NEO4J_PASSWORD=${auth#*/}
            cypher-shell --format plain \
                "MATCH (e:Entity) RETURN count(e);"
        ' 2>/dev/null | tail -1 || echo "0"
    )
    if [[ "$entities" -gt 0 ]]; then
        echo "  ✅ Entities extracted: $entities"
    else
        echo "  ⚠️  No entities in graph (the extraction pipeline may still be pending)"
    fi
else
    echo "  ❌ Neo4j not running"
    exit_code=1
fi

echo "5. Checking API..."
if container_running luminari-api; then
    echo "  ✅ API container running"
    ping_status=$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            http://127.0.0.1:8003/ping 2>/dev/null || echo "000"
    )
    if [[ "$ping_status" == "200" ]]; then
        echo "  ✅ API responding"
    else
        echo "  ❌ API not responding (status: $ping_status)"
        exit_code=1
    fi
else
    echo "  ❌ API container not running"
    exit_code=1
fi

echo "6. Checking provider configuration..."
provider=$(
    docker exec luminari-api python -c \
        "import os; print(os.getenv('LLM_PROVIDER', 'not-set'))" 2>/dev/null ||
        echo "unavailable"
)
if [[ "$provider" == "ollama" ]]; then
    echo "  ✅ LLM provider set to Ollama"
elif [[ "$provider" == "openai" ]]; then
    echo "  ⚠️  LLM provider set to OpenAI"
else
    echo "  ⚠️  LLM provider: $provider"
fi

echo "7. Checking Ollama connectivity from API..."
ollama_check=$(
    docker exec luminari-api \
        curl --silent http://ollama:11434/api/tags 2>/dev/null |
        grep -c '"models"' || true
)
if [[ "$ollama_check" -gt 0 ]]; then
    echo "  ✅ API can reach Ollama service"
else
    echo "  ⚠️  API cannot reach Ollama service"
fi

echo "8. Checking provider imports..."
if docker exec luminari-api python -c \
    "from src.llm.config import get_llm_config; get_llm_config()" >/dev/null 2>&1
then
    echo "  ✅ Provider configuration imports successfully"
else
    echo "  ⚠️  Provider configuration import failed"
    exit_code=1
fi

echo ""
echo "=================================================="
if [[ "$exit_code" -eq 0 ]]; then
    echo "✅ Validation PASSED!"
else
    echo "⚠️  Validation completed with warnings/errors"
fi
echo "=================================================="
echo ""

exit "$exit_code"
