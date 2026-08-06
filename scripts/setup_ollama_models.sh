#!/bin/bash
# Setup script for Ollama models

echo "🚀 Setting up Ollama models for Luminari Sage..."

# Check if Ollama container is running
if ! docker ps | grep -q luminari-ollama; then
    echo "❌ Ollama container not running. Start with: docker compose up -d ollama"
    exit 1
fi

# Pull essential models
echo "📥 Pulling nomic-embed-text (embeddings)..."
docker exec luminari-ollama ollama pull nomic-embed-text

echo "📥 Pulling qwen2.5:7b (chat/creative)..."
docker exec luminari-ollama ollama pull qwen2.5:7b

echo "📥 Pulling qwen2.5:3b (Graphiti extraction)..."
docker exec luminari-ollama ollama pull qwen2.5:3b

# Verify models
echo ""
echo "✅ Installed models:"
docker exec luminari-ollama ollama list

echo ""
echo "🧪 Testing qwen2.5:7b performance..."
time docker exec luminari-ollama ollama run qwen2.5:7b "Write one sentence about crystal dwarves."

echo ""
echo "✅ Setup complete! All models ready."
