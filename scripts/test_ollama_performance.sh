#!/bin/bash
# Performance test for Ollama models

echo "🧪 Testing Ollama Performance..."
echo ""

# Test qwen2.5:7b
echo "Testing qwen2.5:7b (expect 40-50 tok/s)..."
time docker exec luminari-ollama ollama run qwen2.5:7b "Write a 100-word description of a fantasy crystal mine."

echo ""
echo "Testing deepseek-r1:8b (expect 35-45 tok/s)..."
time docker exec luminari-ollama ollama run deepseek-r1:8b "Calculate the factorial of 10 and explain the steps."

echo ""
echo "✅ Performance test complete. Review times above."
