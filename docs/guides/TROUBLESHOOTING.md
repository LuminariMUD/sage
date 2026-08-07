# Troubleshooting Guide

**Version**: 0.7.15
**Status**: Production Ready
**Last Updated**: 2025-11-12

This guide provides solutions to common issues when working with Luminari Sage.

---

## Table of Contents

- [Database Issues](#database-issues)
- [Docker Issues](#docker-issues)
- [API Issues](#api-issues)
- [Pipeline Issues](#pipeline-issues)
- [Authentication Issues](#authentication-issues)
- [Performance Issues](#performance-issues)
- [Neo4j Issues](#neo4j-issues)
- [MCP Issues](#mcp-issues)
- [Agent Issues](#agent-issues)
- [Testing Issues](#testing-issues)

---

## Database Issues

### PostgreSQL Connection Failed

**Symptoms:**

- `Connection refused` errors
- `FATAL: password authentication failed` errors
- API fails to start with database errors

**Solutions:**

1. **Check if PostgreSQL is running:**

   ```bash
   docker ps | grep postgres
   docker compose logs postgres
   ```

2. **Verify credentials in `.env`:**

   ```bash
   grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env
   python3 scripts/check_secret_config.py POSTGRES_PASSWORD
   ```

   Ensure `POSTGRES_PASSWORD`, `POSTGRES_USER`, and `POSTGRES_DB` match docker-compose.yml

3. **Check database initialization:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "\dt"
   ```

4. **Reset database (destructive):**

   ```bash
   docker compose down -v
   docker compose up -d
   # Wait 10 seconds for initialization
   make semantic-pipeline
   ```

5. **Check pgvector extension:**
   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "SELECT * FROM pg_extension WHERE extname='vector';"
   ```

### Database Schema Missing

**Symptoms:**

- `relation "lore_documents" does not exist`
- `relation "episodes" does not exist`

**Solutions:**

1. **Apply database schema:**

   ```bash
   docker exec -i luminari-postgres psql -U luminari -d luminari_lore < schemas/postgres_schema.sql
   ```

2. **Verify tables exist:**
   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "\dt"
   ```

### pgvector Extension Issues

**Symptoms:**

- `type "vector" does not exist`
- Embedding queries fail

**Solutions:**

1. **Install pgvector extension:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

2. **Verify extension:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "SELECT * FROM pg_extension WHERE extname='vector';"
   ```

3. **Rebuild database (if extension still fails):**
   ```bash
   docker compose down -v
   # Ensure docker-compose.yml has pgvector image
   docker compose up -d postgres
   ```

---

## Docker Issues

### Container Won't Start

**Symptoms:**

- `docker compose up` fails
- Container exits immediately
- Health checks fail

**Solutions:**

1. **Check logs:**

   ```bash
   docker compose logs api
   docker compose logs postgres
   docker compose logs neo4j
   ```

2. **Check disk space:**

   ```bash
   df -h
   docker system df
   ```

3. **Clean up Docker resources:**

   ```bash
   docker compose down
   docker system prune -a --volumes  # Warning: removes unused images/volumes
   docker compose up -d
   ```

4. **Rebuild from scratch:**
   ```bash
   docker compose down -v
   docker compose build --no-cache
   docker compose up -d
   ```

### Port Already in Use

**Symptoms:**

- `bind: address already in use`
- `Error starting userland proxy`

**Solutions:**

1. **Find what's using the port:**

   ```bash
   sudo lsof -i :8003  # API port
   sudo lsof -i :5432  # PostgreSQL port
   sudo lsof -i :7687  # Neo4j port
   ```

2. **Stop conflicting service:**

   ```bash
   sudo systemctl stop postgresql  # If system PostgreSQL is running
   # Or kill specific process
   kill -9 <PID>
   ```

3. **Change port in docker-compose.yml:**
   ```yaml
   ports:
     - "8004:8003" # Use different external port
   ```

### Volume Permissions Issues

**Symptoms:**

- `Permission denied` errors in logs
- Database won't initialize

**Solutions:**

1. **Fix volume permissions:**

   ```bash
   sudo chown -R $(id -u):$(id -g) .
   ```

2. **Check volume mounts:**

   ```bash
   docker volume ls
   docker volume inspect luminari-sage_postgres_data
   ```

3. **Remove and recreate volumes:**
   ```bash
   docker compose down -v
   docker compose up -d
   ```

---

## API Issues

### API Won't Start

**Symptoms:**

- Container starts but API doesn't respond
- Health check fails
- Import errors in logs

**Solutions:**

1. **Check API logs:**

   ```bash
   docker compose logs -f api
   ```

2. **Check dependencies installed:**

   ```bash
   docker exec -it luminari-api pip list
   ```

3. **Rebuild API container:**

   ```bash
   docker compose build --no-cache api
   docker compose up -d api
   ```

4. **Check environment variables:**
   ```bash
   docker exec luminari-api python -c \
     "import os; names=('POSTGRES_PASSWORD','NEO4J_PASSWORD','OPENAI_API_KEY'); print(*(name + ': ' + ('SET' if os.getenv(name) else 'MISSING') for name in names), sep='\n')"
   ```

### API Returns 500 Errors

**Symptoms:**

- Internal server errors
- Unhandled exceptions in logs

**Solutions:**

1. **Check detailed logs:**

   ```bash
   docker compose logs api | tail -n 100
   ```

2. **Test database connections:**

   ```bash
   curl http://localhost:8003/api/v1/health
   ```

3. **Check OpenAI API key:**

   ```bash
   docker exec -it luminari-api python -c "import os; print('OPENAI_API_KEY' in os.environ)"
   ```

4. **Restart API:**
   ```bash
   docker compose restart api
   ```

### Slow API Responses

**Symptoms:**

- Queries take >10 seconds
- Timeouts on complex queries

**Solutions:**

1. **Check database indexes:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "\di"
   ```

2. **Monitor resource usage:**

   ```bash
   docker stats
   ```

3. **Check Neo4j query performance:**
   - Visit http://localhost:7474
   - Run query with `PROFILE` or `EXPLAIN`

4. **Increase container resources:**
   - Edit docker-compose.yml to increase memory limits
   - Restart services

---

## Pipeline Issues

### Pipeline Fails to Load Documents

**Symptoms:**

- `make load-canon` fails
- No documents in database

**Solutions:**

1. **Check lore_docs directory:**

   ```bash
   ls -la lore_docs/canon/
   ```

2. **Verify directory mounted in container:**

   ```bash
   docker exec -it luminari-api ls -la /app/lore_docs/canon/
   ```

3. **Check file permissions:**

   ```bash
   chmod -R 755 lore_docs/
   ```

4. **Run with verbose output:**
   ```bash
   make load-canon VERBOSE=true
   ```

### Episode Creation Fails

**Symptoms:**

- `make create-episodes` fails
- Episodes table is empty

**Solutions:**

1. **Ensure documents are loaded first:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "SELECT COUNT(*) FROM lore_documents;"
   ```

2. **Check episode creation logs:**

   ```bash
   docker exec -it luminari-api python src/scripts/create_episodes_from_documents.py --verbose
   ```

3. **Clear processing flags and retry:**
   ```bash
   make reset-all
   make create-episodes
   ```

### Embedding Generation Fails

**Symptoms:**

- `make generate-embeddings` fails
- OpenAI API errors

**Solutions:**

1. **Verify OpenAI API key:**

   ```bash
   docker exec luminari-api python -c \
     "import os; print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING')"
   ```

2. **Check OpenAI account status:**
   - Visit https://platform.openai.com/usage
   - Ensure you have available credits

3. **Use alternative embedding model:**
   - Edit `.env` to set `USE_OPENAI_EMBEDDINGS=false`
   - Use sentence-transformers model (local)

4. **Retry with rate limiting:**
   ```bash
   # Edit src/scripts/generate_embeddings.py to add delays
   docker exec -it luminari-api python src/scripts/generate_embeddings.py --batch-size 10
   ```

### Graphiti Sync Fails

**Symptoms:**

- `make sync-to-graphiti` fails
- No entities in Neo4j

**Solutions:**

1. **Check Neo4j connection:**

   ```bash
   docker compose exec neo4j neo4j status
   ```

2. **Verify episodes have embeddings:**

   ```bash
   docker exec -it luminari-postgres psql -U luminari -d luminari_lore -c "SELECT COUNT(*) FROM episodes WHERE embedding IS NOT NULL;"
   ```

3. **Check Graphiti logs:**

   ```bash
   docker exec -it luminari-api python src/scripts/extract_entities.py --verbose --limit 10
   ```

4. **Clear Neo4j and retry:**
   ```bash
   make clear-graph
   make sync-to-graphiti
   ```

---

## Authentication Issues

### API Key Not Working

**Symptoms:**

- 401 Unauthorized errors
- `Invalid API key` messages

**Solutions:**

1. **Check that the API key is configured:**

   ```bash
   python3 scripts/check_secret_config.py SAGE_API_KEY
   ```

2. **Test a protected endpoint without putting the key in process arguments:**

   ```bash
   ./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
   ```

3. **For loopback-only development, temporarily disable authentication:**
   ```bash
   # In .env
   DISABLE_AUTH=true
   docker compose restart api
   ```

### Authentication Environment Variables Not Loaded

**Symptoms:**

- Auth always fails or always succeeds
- Protected endpoints reject a configured key

**Solutions:**

1. **Check environment variables in container:**

   ```bash
   docker exec luminari-api python -c \
     "import os; names=('SAGE_API_KEY','SAGE_MCP_KEY','SAGE_MCP_BACKEND_KEY'); print(*(name + ': ' + ('SET' if os.getenv(name) else 'MISSING') for name in names), sep='\n')"
   ```

2. **Verify .env file is correct:**

   ```bash
   python3 scripts/check_secret_config.py \
     SAGE_API_KEY SAGE_MCP_KEY SAGE_MCP_BACKEND_KEY
   ```

3. **Restart with fresh environment:**
   ```bash
   docker compose down
   docker compose up -d
   ```

---

## Performance Issues

### High Memory Usage

**Symptoms:**

- Container using >4GB memory
- Out of memory errors

**Solutions:**

1. **Check memory usage:**

   ```bash
   docker stats --no-stream
   ```

2. **Reduce batch sizes:**
   - Edit pipeline scripts to use smaller batches
   - Process in multiple runs

3. **Increase Docker memory limit:**
   - Docker Desktop: Settings → Resources → Memory
   - Or in docker-compose.yml:
     ```yaml
     services:
       api:
         mem_limit: 4g
     ```

4. **Clear caches:**
   ```bash
   docker exec -it luminari-api python -c "import gc; gc.collect()"
   ```

### Slow Queries

**Symptoms:**

- Search takes >5 seconds
- RAG queries timeout

**Solutions:**

1. **Add database indexes:**

   ```sql
   CREATE INDEX IF NOT EXISTS idx_episodes_embedding ON episodes USING ivfflat (embedding vector_cosine_ops);
   ```

2. **Check Neo4j indexes:**

   ```cypher
   SHOW INDEXES;
   ```

3. **Reduce query limits:**

   ```bash
   curl -X POST http://localhost:8003/api/v1/rag/query \
     -H "Content-Type: application/json" \
     -d '{"query": "test", "limit": 5}'  # Reduce from 10 to 5
   ```

4. **Profile queries:**
   ```bash
   docker exec -it luminari-api python -c "import time; start=time.time(); # your query; print(time.time()-start)"
   ```

---

## Neo4j Issues

### Neo4j Browser Won't Load

**Symptoms:**

- http://localhost:7474 doesn't load
- Connection refused

**Solutions:**

1. **Check Neo4j container:**

   ```bash
   docker compose logs neo4j
   docker ps | grep neo4j
   ```

2. **Verify port mapping:**

   ```bash
   docker compose ps neo4j
   ```

3. **Check Neo4j authentication:**
   - Default: neo4j/luminari123
   - Check docker-compose.yml for NEO4J_AUTH

4. **Restart Neo4j:**
   ```bash
   docker compose restart neo4j
   ```

### Cypher Query Fails

**Symptoms:**

- Invalid syntax errors
- Relationship not found

**Solutions:**

1. **Test query in browser:**
   - Visit http://localhost:7474
   - Run query manually

2. **Check node labels:**

   ```cypher
   CALL db.labels();
   ```

3. **Check relationship types:**

   ```cypher
   CALL db.relationshipTypes();
   ```

4. **Verify data exists:**
   ```cypher
   MATCH (n) RETURN count(n);
   ```

### Neo4j Out of Memory

**Symptoms:**

- Java heap space errors
- Neo4j container crashes

**Solutions:**

1. **Increase heap size:**

   ```yaml
   # In docker-compose.yml
   environment:
     - NEO4J_dbms_memory_heap_max__size=2G
   ```

2. **Clear unused data:**

   ```cypher
   MATCH (n) WHERE NOT (n)--() DELETE n;
   ```

3. **Restart Neo4j:**
   ```bash
   docker compose restart neo4j
   ```

---

## MCP Issues

### MCP Server Won't Connect

**Symptoms:**

- Claude Desktop can't connect
- Connection timeout

**Solutions:**

1. **Verify MCP server is running:**

   ```bash
   docker exec -it luminari-api ps aux | grep mcp
   ```

2. **Check Claude Desktop config:**

   ```json
   {
     "mcpServers": {
       "luminari-sage": {
         "command": "docker",
         "args": [
           "exec",
           "-i",
           "luminari-api",
           "python",
           "-m",
           "src.mcp.server"
         ]
       }
     }
   }
   ```

3. **Check logs:**

   ```bash
   tail -f ~/Library/Logs/Claude/mcp*.log  # macOS
   ```

4. **Test MCP connection:**
   ```bash
   docker exec -i luminari-api python -m src.mcp.server
   ```

### MCP Tools Not Working

**Symptoms:**

- Tools not appearing in Claude
- Tool calls fail

**Solutions:**

1. **Verify tools are registered:**

   ```bash
   docker exec -it luminari-api python -c "from src.mcp.server import list_tools; print(list_tools())"
   ```

2. **Check API connection:**

   ```bash
   curl http://localhost:8003/api/v1/health
   ```

3. **Restart Claude Desktop:**
   - Quit Claude Desktop completely
   - Restart and reconnect

---

## Agent Issues

### Agent Returns Generic Responses

**Symptoms:**

- Responses don't reference lore
- No entity mentions

**Solutions:**

1. **Verify data pipeline completed:**

   ```bash
   make status
   ```

2. **Check retrieval is working:**

   ```bash
   curl "http://localhost:8003/api/v1/lore/search?query=test"
   ```

3. **Increase retrieval limit:**
   - Edit agent configuration to retrieve more context

### Agent Streaming Fails

**Symptoms:**

- SSE connection drops
- No streaming output

**Solutions:**

1. **Check SSE headers:**

   ```bash
   curl -N -H "Accept: text/event-stream" http://localhost:8003/api/v1/chat/stream
   ```

2. **Test with small query:**

   ```bash
   curl -X POST -H "Content-Type: application/json" \
     -d '{"query": "hi", "stream": true}' \
     http://localhost:8003/api/v1/chat/stream
   ```

3. **Check timeout settings:**
   - Ensure reverse proxy (if any) supports long-lived connections

---

## Testing Issues

### Tests Fail to Run

**Symptoms:**

- `pytest` command fails
- Import errors

**Solutions:**

1. **Install test dependencies:**

   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio pytest-cov
   ```

2. **Check Python path:**

   ```bash
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   pytest
   ```

3. **Run inside container:**
   ```bash
   docker exec -it luminari-api pytest
   ```

### Integration Tests Fail

**Symptoms:**

- Integration tests timeout
- Connection errors

**Solutions:**

1. **Ensure services are running:**

   ```bash
   docker compose ps
   ```

2. **Run only unit tests:**

   ```bash
   pytest -m unit
   ```

3. **Skip integration tests:**
   ```bash
   pytest -m "not integration"
   ```

### Data-Dependent Tests Fail

**Symptoms:**

- Tests expect data that doesn't exist
- Empty result errors

**Solutions:**

1. **Load test data:**

   ```bash
   make semantic-pipeline
   ```

2. **Skip data-dependent tests:**

   ```bash
   pytest -m "not data_dependent"
   ```

3. **Create test fixtures:**
   - Add test data to `tests/fixtures/`

---

## Getting More Help

If these solutions don't resolve your issue:

1. **Check logs in detail:**

   ```bash
   docker compose logs -f --tail=200
   ```

2. **Enable debug mode:**

   ```bash
   # In .env
   LOG_LEVEL=DEBUG
   docker compose restart api
   ```

3. **Check documentation:**
   - [API Reference](../reference/API_REFERENCE.md)
   - [Developer Guide](../development/DEVELOPER_GUIDE.md)
   - [Architecture](../reference/ARCHITECTURE.md)

4. **Check GitHub issues:**
   - Search existing issues for similar problems
   - Create new issue with:
     - Exact error message
     - Steps to reproduce
     - System information (OS, Docker version)
     - Relevant log excerpts

5. **Community support:**
   - LuminariMUD Discord server
   - Project contributors

---

## Preventive Measures

### Regular Maintenance

```bash
# Weekly tasks
docker system prune -a  # Clean unused images
make status             # Check system health
make logs               # Review logs for errors

# Monthly tasks
docker compose down -v  # Full reset
docker compose up -d
make semantic-pipeline  # Rebuild from scratch
```

### Backup Before Changes

```bash
# Backup databases before major changes
docker exec luminari-postgres pg_dump -U luminari luminari_lore > backup.sql
# Backup Neo4j
docker exec luminari-neo4j neo4j-admin dump --to=/tmp/neo4j-backup.dump
docker cp luminari-neo4j:/tmp/neo4j-backup.dump ./neo4j-backup.dump
```

### Monitoring

Set up health check monitoring:

```bash
# Add to crontab
*/5 * * * * curl -f http://localhost:8003/api/v1/health || echo "Health check failed"
```

---

**Related Documentation:**

- [Quickstart Guide](QUICKSTART.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Developer Guide](../development/DEVELOPER_GUIDE.md)
- [API Reference](../reference/API_REFERENCE.md)
