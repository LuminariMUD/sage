#!/bin/bash
# Preload and warm up Ollama models

set -e

echo "🔥 Warming up Ollama models..."

# Check if Ollama container is running
if ! docker ps | grep -q luminari-ollama; then
    echo "❌ Error: Ollama container is not running"
    echo "   Run: docker compose up -d ollama"
    exit 1
fi

# Get model names from environment or use defaults
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen2.5:7b}"
REASONING_MODEL="${OLLAMA_REASONING_MODEL:-deepseek-r1:8b}"
EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

echo "📦 Chat model: $CHAT_MODEL"
echo "🧠 Reasoning model: $REASONING_MODEL"
echo "🔢 Embedding model: $EMBEDDING_MODEL"

# Preload chat model
echo "⏳ Warming up chat model ($CHAT_MODEL)..."
docker exec luminari-ollama ollama run "$CHAT_MODEL" "test" > /dev/null 2>&1 || echo "   ⚠️ Chat model not available"

# Preload reasoning model (if different from chat)
if [ "$REASONING_MODEL" != "$CHAT_MODEL" ]; then
    echo "⏳ Warming up reasoning model ($REASONING_MODEL)..."
    docker exec luminari-ollama ollama run "$REASONING_MODEL" "test" > /dev/null 2>&1 || echo "   ⚠️ Reasoning model not available"
fi

# Preload embedding model
echo "⏳ Warming up embedding model ($EMBEDDING_MODEL)..."
docker exec luminari-ollama ollama run "$EMBEDDING_MODEL" "test" > /dev/null 2>&1 || echo "   ⚠️ Embedding model not available"

echo ""
echo "✅ Models warmed up and ready"
echo ""
echo "📊 Loaded models:"
docker exec luminari-ollama ollama list
