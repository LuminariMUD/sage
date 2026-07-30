# Local LLM Quick Start Guide

Get up and running with local LLM inference in 5-10 minutes.

---

## Prerequisites

- Docker with GPU support (nvidia-docker2)
- NVIDIA GPU with 8GB+ VRAM (recommended)
- NVIDIA drivers installed and working
- 16GB+ RAM
- 20GB+ free disk space

### Verify GPU Access

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker can access GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

---

## Quick Setup (5 minutes)

### 1. Start Ollama Service

```bash
# Start just Ollama first
docker compose up -d ollama

# Wait for it to be ready
docker logs -f luminari-ollama
# (Press Ctrl+C once you see "Ollama is running")
```

### 2. Pull Required Models

```bash
# Use the setup script (recommended)
./scripts/setup_ollama_models.sh

# Or manually:
docker exec luminari-ollama ollama pull qwen2.5:7b
docker exec luminari-ollama ollama pull deepseek-r1:8b
docker exec luminari-ollama ollama pull nomic-embed-text
```

This will download ~8GB of models. Takes 3-10 minutes depending on connection.

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env
chmod 600 .env

# Edit .env to use Ollama
# Change: LLM_PROVIDER=openai
# To:     LLM_PROVIDER=ollama
```

Or use `sed`:

```bash
sed -i 's/LLM_PROVIDER=openai/LLM_PROVIDER=ollama/' .env
```

### 4. Start All Services

```bash
# Start everything
docker compose up -d

# Check status
docker compose ps

# View API logs
docker compose logs -f api
```

### 5. Validate Setup

```bash
# Run validation script
./scripts/validate_migration.sh
```

Should see all green checkmarks ✅

---

## Testing Your Setup

### Quick API Test

```bash
# Test ping endpoint
curl http://localhost:8003/ping

# Test health endpoint
curl http://localhost:8003/api/v1/health
```

### Test RAG Query

```bash
# Simple RAG query
curl -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who are the crystal dwarves?",
    "limit": 5
  }' | jq
```

### Test LLM Generation

```bash
# Inside API container
docker exec -it luminari-api python3 -c "
import asyncio
from src.llm.providers.factory import get_llm_provider

async def test():
    provider = get_llm_provider()
    response = await provider.generate('Say hello!', temperature=0.7)
    print(response)

asyncio.run(test())
"
```

### Run Test Suite

```bash
# Unit tests (fast)
docker exec luminari-api pytest tests/llm/test_providers.py -v

# Integration tests (requires running services)
docker exec luminari-api pytest tests/llm/test_ollama_integration.py -v

# All tests
docker exec luminari-api pytest tests/ -v
```

---

## Usage

### Switching Between Providers

```bash
# Set LLM_PROVIDER=ollama or LLM_PROVIDER=openai in the mode-600 .env file.
# For OpenAI, add the key with a password manager or hidden-input editor.
python3 scripts/check_secret_config.py OPENAI_API_KEY

# Restart API to apply changes
docker compose restart api
```

### Running the Data Pipeline

If you need to process lore documents:

```bash
# Complete pipeline
make semantic-pipeline

# Or step by step:
make load-canon              # Load lore documents
make create-episodes         # Create semantic chunks
make generate-embeddings     # Generate embeddings (uses LLM)
make sync-to-graphiti        # Extract entities to Neo4j
```

### Performance Testing

```bash
# Benchmark performance
docker exec luminari-api pytest tests/performance/ -v -s

# Quality comparison (if you have OpenAI key)
docker exec luminari-api pytest tests/quality/ -v -s

# Stress testing
docker exec luminari-api pytest tests/stress/ -v -s
```

---

## Troubleshooting

### Slow Responses

**Problem**: Queries take 10+ seconds

**Solutions**:

- Check GPU usage: `nvidia-smi`
- Reduce batch size in config
- Use smaller/quantized models
- Keep Ollama warm: `./scripts/warmup_models.sh`

### Out of Memory Errors

**Problem**: CUDA OOM or container crashes

**Solutions**:

```bash
# Use smaller model
docker exec luminari-ollama ollama pull qwen2.5:3b

# Reduce concurrent requests in config
# Edit docker-compose.yml: OLLAMA_NUM_PARALLEL=1

# Restart Ollama
docker compose restart ollama
```

### Models Not Found

**Problem**: "model not found" errors

**Solutions**:

```bash
# List installed models
docker exec luminari-ollama ollama list

# Pull missing models
docker exec luminari-ollama ollama pull qwen2.5:7b

# Or run setup script again
./scripts/setup_ollama_models.sh
```

### API Can't Reach Ollama

**Problem**: Connection errors to Ollama

**Solutions**:

```bash
# Check Ollama is running
docker ps | grep ollama

# Check network connectivity
docker exec luminari-api curl -s http://ollama:11434/api/tags

# Restart both services
docker compose restart ollama api
```

### Poor Quality Responses

**Problem**: Responses are incoherent or wrong

**Solutions**:

- Adjust temperature (lower = more deterministic)
- Try different model (DeepSeek-R1 for reasoning)
- Switch to OpenAI for critical queries
- Check if model is properly loaded

```bash
# Test model directly
docker exec luminari-ollama ollama run qwen2.5:7b "Test prompt"
```

---

## Performance Tips

### Speed Optimization

1. **Keep Ollama Running**: Don't stop the container
2. **Warm Up Models**: Run `./scripts/warmup_models.sh`
3. **Use Streaming**: Better perceived performance
4. **Batch Embeddings**: Use batch API when possible
5. **GPU Optimization**: Ensure exclusive GPU access

### Quality Optimization

1. **Lower Temperature**: Use 0.3-0.5 for factual queries
2. **Higher Temperature**: Use 0.7-0.9 for creative content
3. **Model Selection**: DeepSeek-R1 for reasoning, Qwen2.5 for general
4. **Context Management**: Provide relevant context in prompts
5. **Hybrid Approach**: Use OpenAI for critical queries

### Cost Optimization

1. **Local Development**: Always use Ollama (zero cost)
2. **Batch Processing**: Run overnight on local machine
3. **Caching**: Cache embeddings and common queries
4. **Smart Routing**: Ollama for routine, OpenAI for critical

---

## Common Workflows

### Daily Development

```bash
# Morning: Start services
docker compose up -d

# Check everything is ready
./scripts/validate_migration.sh

# Run your code/tests
pytest tests/

# Evening: Keep running or stop
docker compose stop  # (optional)
```

### Processing New Lore

```bash
# Add new markdown files to lore_docs/

# Run pipeline
make semantic-pipeline

# Validate
./scripts/validate_migration.sh
```

### Switching to OpenAI for Production

```bash
# Update .env
sed -i 's/LLM_PROVIDER=ollama/LLM_PROVIDER=openai/' .env

# Add the key with a password manager or hidden-input editor, then verify
# presence without displaying it
python3 scripts/check_secret_config.py OPENAI_API_KEY

# Restart
docker compose restart api

# Verify the non-secret provider setting
docker exec luminari-api python -c \
  "import os; print('LLM_PROVIDER=' + os.getenv('LLM_PROVIDER', 'not-set'))"
```

---

## Resources

### Documentation

- Full migration docs: `docs/ongoing_projects/phases/`
- Phase 1: Ollama Setup
- Phase 2: Provider Abstraction
- Phase 3: LangChain Integration
- Phase 4: Embeddings Migration
- Phase 5: Graphiti Integration
- Phase 6: Performance Optimization
- Phase 7: Testing & Validation (this phase)

### Scripts

- `scripts/setup_ollama_models.sh` - Install models
- `scripts/validate_migration.sh` - Validate setup
- `scripts/warmup_models.sh` - Warm up models
- `scripts/test_ollama_performance.sh` - Performance test

### Key Files

- `.env` - Environment configuration
- `docker-compose.yml` - Service definitions
- `src/llm/config.py` - LLM configuration
- `src/llm/providers/` - Provider implementations

---

## Getting Help

### Check Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f ollama

# Last 100 lines
docker compose logs --tail=100 api
```

### Debug Mode

```bash
# Check the non-secret log-level setting
docker exec luminari-api python -c \
  "import os; print('LOG_LEVEL=' + os.getenv('LOG_LEVEL', 'INFO'))"

# Run tests with verbose output
docker exec luminari-api pytest tests/ -vv -s
```

### Health Checks

```bash
# API health
curl http://localhost:8003/api/v1/health | jq

# Ollama health
docker exec luminari-ollama ollama list

# Database connections
docker compose ps
```

### Report Issues

If you encounter issues:

1. Run validation script: `./scripts/validate_migration.sh`
2. Collect logs: `docker compose logs > debug.log`
3. Check documentation in `docs/`
4. Review phase completion summaries

---

## Next Steps

After successful setup:

1. **Explore the API**: Try different queries and endpoints
2. **Run the Test Suite**: Understand system capabilities
3. **Process Your Data**: Run the semantic pipeline
4. **Benchmark Performance**: Run performance tests
5. **Compare Quality**: Run quality tests (if you have OpenAI key)
6. **Read Migration Results**: See `docs/MIGRATION_RESULTS.md`

---

**Setup Time**: 5-10 minutes
**Difficulty**: Easy (with prerequisites met)
**Cost**: $0 for local usage

**Questions?** Check the full documentation or run `./scripts/validate_migration.sh` to verify your setup.

---

**Last Updated**: 2025-01-13
