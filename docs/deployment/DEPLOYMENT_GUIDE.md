# Luminari Sage Deployment Guide

**Last Updated**: November 12, 2025
**Version**: 0.7.0
**Status**: Production Ready

## Overview

This guide covers deploying Luminari Sage in production environments. The system is currently running on luminarimud.com:8003 using Docker orchestration.

## Prerequisites

### System Requirements

- **OS**: Ubuntu 20.04+ or similar Linux distribution
- **RAM**: Minimum 8GB, recommended 16GB for production
- **Storage**: 50GB minimum (SSD strongly recommended for database performance)
- **CPU**: 4+ cores recommended
- **Network**: Stable internet connection for OpenAI API calls

### Software Requirements

- **Docker** 20.10+ or later
- **Docker Compose** v2.0+ (note: v2 syntax, not v1)
- **Git** for repository cloning
- **Make** (optional but recommended for pipeline management)
- **Python** 3.11+ (only if running scripts outside containers)

### Required API Keys

- **OpenAI API Key**: Required for embeddings and LLM operations
  - Get from: https://platform.openai.com/api-keys
  - Estimated cost: $50-100/month for moderate usage
  - Models used: GPT-4 (chat), text-embedding-ada-002 or sentence-transformers (embeddings)

## Quick Start Deployment

### 1. Clone Repository

```bash
git clone https://github.com/LuminariMUD/sage.git
cd sage
```

### 2. Environment Configuration

```bash
# Copy example environment file
cp .env.example .env
chmod 600 .env

# Edit with your configuration
nano .env
```

**Required Environment Variables**:

```bash
# OpenAI Configuration (REQUIRED)
OPENAI_API_KEY=

# Database Passwords (REQUIRED; no defaults)
POSTGRES_PASSWORD=your-secure-password-here
NEO4J_PASSWORD=your-secure-neo4j-password

# API Keys (REQUIRED in production; no defaults)
# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
SAGE_API_KEY=your-backend-api-key
SAGE_MCP_KEY=your-mcp-operations-key
SAGE_MCP_BACKEND_KEY=your-mcp-backend-key

# Service Configuration
API_PORT=8003                    # API server port
NEO4J_BOLT_PORT=7687            # Neo4j Bolt protocol
NEO4J_HTTP_PORT=7474            # Neo4j Browser
POSTGRES_PORT=5432              # PostgreSQL port

# Database Configuration
POSTGRES_DB=sage_db
POSTGRES_USER=sage
NEO4J_USER=neo4j

# Paths
LORE_DIR=/app/lore_docs         # Lore documents (inside container)

# Optional: Authentication
DISABLE_AUTH=false               # Set to 'true' for local development only

# Optional: Embedding Configuration
USE_OPENAI_EMBEDDINGS=false     # Use OpenAI embeddings (1536 dim) vs sentence-transformers (384 dim)
EMBEDDING_BATCH_SIZE=32         # Batch size for embedding generation
```

### 3. Start Services

```bash
# Start all services (PostgreSQL, Neo4j, API)
docker compose up -d

# Check service health
docker compose ps

# View logs (watch for startup errors)
docker compose logs -f api
```

**Expected Output**:

- PostgreSQL: `database system is ready to accept connections`
- Neo4j: `Started.`
- API: `Application startup complete` on port 8003

### 4. Initialize Data Pipeline

**IMPORTANT**: The data pipeline is resource-intensive and runs separately from deployment:

```bash
# Complete pipeline (recommended for first deployment)
make semantic-pipeline

# This runs four steps in sequence:
# 1. make load-canon          # Load markdown documents → PostgreSQL
# 2. make create-episodes     # Semantic chunking (200-500 tokens)
# 3. make generate-embeddings # Vector embeddings
# 4. make sync-to-graphiti    # Extract entities/relationships → Neo4j

# Estimated time: 10-30 minutes depending on corpus size and hardware
```

**Why Separate Pipeline?**

- Prevents deployment timeouts
- Can be re-run as lore evolves
- Resource-intensive operations scheduled independently
- API is functional immediately (pipeline adds data)

### 5. Verify Deployment

```bash
# Check API health (no auth required)
curl http://localhost:8003/ping
curl http://localhost:8003/api/v1/health

# Test authenticated endpoint
./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats

# Check data pipeline status
make status
```

**Success Indicators**:

- `/ping` returns `{"status": "ok"}`
- `/api/v1/health` returns database connection status
- `/api/v1/stats` shows entity and document counts
- `make status` shows processing completion percentages

## Production Deployment

### Security Hardening

#### 1. SSL/TLS Configuration

Use a reverse proxy (nginx or Caddy) with SSL for production:

**Nginx Configuration**:

```nginx
server {
    listen 443 ssl http2;
    server_name sage.yourdomain.com;

    # SSL certificates (use Let's Encrypt or your provider)
    ssl_certificate /etc/letsencrypt/live/sage.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sage.yourdomain.com/privkey.pem;

    # SSL security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://localhost:8003;
        proxy_http_version 1.1;

        # Upgrade headers for WebSocket/SSE
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support (for streaming chat)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;  # 24 hours for long-running streams
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name sage.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

**Caddy Configuration** (simpler, automatic HTTPS):

```caddyfile
sage.yourdomain.com {
    reverse_proxy localhost:8003 {
        # SSE support
        flush_interval -1
    }
}
```

#### 2. Firewall Configuration

```bash
# Allow only necessary ports
ufw allow 22/tcp    # SSH
ufw allow 443/tcp   # HTTPS
ufw allow 80/tcp    # HTTP (redirect to HTTPS)
ufw enable

# Block direct access to services
ufw deny 8003/tcp   # API
ufw deny 7687/tcp   # Neo4j
ufw deny 5432/tcp   # PostgreSQL
```

#### 3. API Key Management

**Generate Secure Keys**:

```bash
# Generate three separate API keys
python3 -c "import secrets; print('SAGE_API_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('SAGE_MCP_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('SAGE_MCP_BACKEND_KEY=' + secrets.token_urlsafe(32))"

# Add to .env file
# Then restrict permissions
chmod 600 .env
chown root:root .env  # or your deployment user
```

**Key Types and Usage**:

- **SAGE_API_KEY**: General backend API access (most endpoints)
- **SAGE_MCP_KEY**: MCP operations access (Claude Desktop integration)
- **SAGE_MCP_BACKEND_KEY**: MCP backend operations (internal use)

**Key Rotation**:

```bash
# Enter a value generated by your password manager without echoing it
read -r -s -p "New backend key: " NEW_KEY
echo
export NEW_KEY
python3 - <<'PY'
import os
from dotenv import set_key

set_key(".env", "SAGE_API_KEY", os.environ["NEW_KEY"], quote_mode="always")
PY
unset NEW_KEY

# Restart API
docker compose restart api

# Update clients with new key
```

**Environment File Security**:

```bash
# Restrict file permissions
chmod 600 .env

# Never commit .env to version control
# Add to .gitignore if not already present
echo ".env" >> .gitignore
```

### Performance Optimization

#### 1. Database Tuning

**PostgreSQL** (`postgresql.conf`):

```ini
# Memory
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 16MB
maintenance_work_mem = 1GB

# Connections
max_connections = 200
max_parallel_workers = 8

# Write performance
checkpoint_completion_target = 0.9
wal_buffers = 16MB
max_wal_size = 4GB
```

**Neo4j** (`neo4j.conf`):

```ini
# Memory
dbms.memory.heap.initial_size=4g
dbms.memory.heap.max_size=8g
dbms.memory.pagecache.size=4g

# Performance
dbms.threads.worker_count=8
dbms.connector.bolt.thread_pool_max_size=400
```

#### 2. Caching Layer (Optional)

Add Redis for caching:

```yaml
# docker-compose.prod.yml addition
redis:
  image: redis:8.6.5-alpine
  restart: unless-stopped
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes
```

#### 3. Load Balancing

For high availability, deploy multiple API instances:

```yaml
# docker-compose.prod.yml modification
api:
  image: "${SAGE_IMAGE}" # immutable registry digest
  deploy:
    replicas: 3
  # ... rest of configuration
```

Use nginx for load balancing:

```nginx
upstream sage_backend {
    least_conn;
    server localhost:8003;
    server localhost:8004;
    server localhost:8005;
}
```

### Monitoring Setup

#### 1. Prometheus Metrics

```yaml
# docker-compose.monitoring.yml
prometheus:
  image: prom/prometheus
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  volumes:
    - grafana_data:/var/lib/grafana
  ports:
    - "3000:3000"
```

#### 2. Application Metrics

Add to `src/api/main.py`:

```python
from prometheus_client import Counter, Histogram, generate_latest

request_count = Counter('sage_requests_total', 'Total requests')
request_duration = Histogram('sage_request_duration_seconds', 'Request duration')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

#### 3. Log Aggregation

```yaml
# docker-compose.monitoring.yml
loki:
  image: grafana/loki
  ports:
    - "3100:3100"
  volumes:
    - loki_data:/loki

promtail:
  image: grafana/promtail
  volumes:
    - /var/log:/var/log
    - ./promtail.yml:/etc/promtail/promtail.yml
```

### Backup Strategy

#### 1. Automated Backups

Create a backup script (`/root/scripts/backup-sage.sh`):

```bash
#!/bin/bash
# backup-sage.sh - Run daily via cron
# Backs up PostgreSQL, Neo4j, and environment configuration

set -e  # Exit on error

BACKUP_ROOT="/backup/sage"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$BACKUP_ROOT/backup.log"

echo "$(date): Starting backup" >> $LOG_FILE
mkdir -p $BACKUP_DIR

# Navigate to project directory
cd /home/luminari/lore  # Adjust to your path

# Backup PostgreSQL
echo "$(date): Backing up PostgreSQL" >> $LOG_FILE
docker compose exec -T postgres \
  pg_dump -U sage sage_db > $BACKUP_DIR/postgres.sql

# Backup Neo4j (using neo4j-admin dump)
echo "$(date): Backing up Neo4j" >> $LOG_FILE
docker compose exec -T neo4j \
  neo4j-admin database dump neo4j --to-path=/backups
docker cp luminari-neo4j:/backups/neo4j.dump $BACKUP_DIR/

# Backup environment configuration
echo "$(date): Backing up configuration" >> $LOG_FILE
cp .env $BACKUP_DIR/env.backup

# Backup lore documents (if modified)
tar -czf $BACKUP_DIR/lore_docs.tar.gz lore_docs/

# Create backup manifest
cat > $BACKUP_DIR/manifest.txt << EOF
Backup Date: $(date)
PostgreSQL: postgres.sql
Neo4j: neo4j.dump
Environment: env.backup
Lore Documents: lore_docs.tar.gz
EOF

# Compress backup
echo "$(date): Compressing backup" >> $LOG_FILE
tar -czf $BACKUP_DIR.tar.gz -C $BACKUP_ROOT $(basename $BACKUP_DIR)
rm -rf $BACKUP_DIR

# Keep last 30 days of backups
echo "$(date): Cleaning old backups" >> $LOG_FILE
find $BACKUP_ROOT -name "*.tar.gz" -mtime +30 -delete

# Calculate backup size
BACKUP_SIZE=$(du -h $BACKUP_DIR.tar.gz | cut -f1)
echo "$(date): Backup complete - Size: $BACKUP_SIZE" >> $LOG_FILE

# Optional: Upload to S3/remote storage
# aws s3 cp $BACKUP_DIR.tar.gz s3://your-bucket/sage-backups/

echo "$(date): Backup finished successfully" >> $LOG_FILE
```

Make the script executable:

```bash
chmod +x /root/scripts/backup-sage.sh
```

#### 2. Backup Schedule

```bash
# Add to crontab (edit with: crontab -e)
# Daily backup at 2 AM
0 2 * * * /root/scripts/backup-sage.sh

# Weekly backup verification at 3 AM on Sunday
0 3 * * 0 /root/scripts/verify-backup.sh
```

#### 3. Disaster Recovery

**Restore from Backup**:

```bash
# Extract backup
BACKUP_DATE="20251112_020000"  # Your backup timestamp
cd /backup/sage
tar -xzf ${BACKUP_DATE}.tar.gz

# Navigate to extracted directory
cd ${BACKUP_DATE}

# Stop services
cd /home/luminari/lore  # Your project directory
docker compose down

# Restore PostgreSQL
docker compose up -d postgres
sleep 10  # Wait for PostgreSQL to start

docker compose exec -T postgres \
  psql -U sage -d postgres -c "DROP DATABASE IF EXISTS sage_db;"
docker compose exec -T postgres \
  psql -U sage -d postgres -c "CREATE DATABASE sage_db;"
docker compose exec -T postgres \
  psql -U sage sage_db < /backup/sage/${BACKUP_DATE}/postgres.sql

# Restore Neo4j
docker compose down neo4j
docker volume rm lore_neo4j_data  # WARNING: Deletes existing Neo4j data

docker compose up -d neo4j
sleep 10

# Copy dump file into container and restore
docker cp /backup/sage/${BACKUP_DATE}/neo4j.dump luminari-neo4j:/tmp/
docker compose exec neo4j \
  neo4j-admin database load neo4j --from-path=/tmp

# Restore environment configuration
install -m 0600 /backup/sage/${BACKUP_DATE}/env.backup .env

# Restore lore documents (if needed)
tar -xzf /backup/sage/${BACKUP_DATE}/lore_docs.tar.gz

# Start all services
docker compose up -d

# Verify restoration
sleep 15
curl http://localhost:8003/ping
make status
```

**Backup Verification Script** (`/root/scripts/verify-backup.sh`):

```bash
#!/bin/bash
# Verify backup integrity

LATEST_BACKUP=$(ls -t /backup/sage/*.tar.gz | head -1)
echo "Verifying backup: $LATEST_BACKUP"

# Test archive integrity
tar -tzf $LATEST_BACKUP > /dev/null
if [ $? -eq 0 ]; then
    echo "✓ Backup archive is valid"
else
    echo "✗ Backup archive is corrupted"
    exit 1
fi

# Check backup size (should be > 10MB)
SIZE=$(stat -f%z "$LATEST_BACKUP")
if [ $SIZE -gt 10485760 ]; then
    echo "✓ Backup size is reasonable ($SIZE bytes)"
else
    echo "✗ Backup size is too small ($SIZE bytes)"
    exit 1
fi

echo "Backup verification complete"
```

## Deployment Environments

### Development

```bash
# Use default docker-compose.yml
docker compose up

# Enable debug mode in .env
echo "DEBUG=true" >> .env
echo "LOG_LEVEL=DEBUG" >> .env
echo "DISABLE_AUTH=true" >> .env  # Optional for local dev

# Restart to apply
docker compose restart api
```

### Staging (Optional)

```bash
# Create staging environment file
install -m 0600 .env .env.staging

# Edit staging-specific values
nano .env.staging
# Set OPENAI_API_KEY to staging key
# Set different database passwords
# Set LOG_LEVEL=INFO

# Use staging environment
docker compose --env-file .env.staging up -d
```

### Production

```bash
# Use production environment
docker compose up -d

# Ensure production settings in .env
DEBUG=false
LOG_LEVEL=INFO
DISABLE_AUTH=false

# Verify security settings
grep -E "DEBUG|LOG_LEVEL|DISABLE_AUTH" .env
```

### Environment-Specific Best Practices

**Development**:

- `DEBUG=true` for detailed logs
- `DISABLE_AUTH=true` for easier testing
- `LOG_LEVEL=DEBUG` for verbose output
- Smaller data samples for faster iteration

**Staging**:

- `DEBUG=false` but detailed logging
- `LOG_LEVEL=INFO` for reasonable verbosity
- Full authentication enabled
- Production-like data volume

**Production**:

- `DEBUG=false` always
- `LOG_LEVEL=WARNING` or `INFO`
- All security features enabled
- Automated backups configured
- Monitoring and alerting active

## Scaling Considerations

### Vertical Scaling

- Increase container resources:

```yaml
api:
  deploy:
    resources:
      limits:
        cpus: "4"
        memory: 8G
      reservations:
        cpus: "2"
        memory: 4G
```

### Horizontal Scaling

- Add read replicas for PostgreSQL
- Use Neo4j clustering
- Deploy multiple API instances
- Implement queue-based processing

### Storage Scaling

- Use external storage for embeddings
- Implement data archival
- Use S3-compatible storage for documents

## Troubleshooting

The maintained production path is the manual `Deploy Luminari Sage` GitHub
Actions workflow. It creates owner-only files under
`~/luminari-sage/secrets/`; do not run `docker-compose.prod.yml` directly from
a repository checkout with plaintext secret environment entries. On the
production host, run maintenance commands from `~/luminari-sage` against the
deployed `docker-compose.yml`.

### Common Issues

#### 1. Out of Memory

```bash
# Check memory usage
docker stats

# Increase memory limits
cd ~/luminari-sage
docker compose down
# Edit compose file to increase memory
docker compose up -d
```

#### 2. Slow Queries

```bash
# Check PostgreSQL slow queries
docker compose exec postgres \
  psql -U sage -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Rebuild indexes
make rebuild-indexes
```

#### 3. Connection Issues

```bash
# Check service connectivity
docker compose exec api \
  python -c "from src.db.postgres import test_connection; test_connection()"

# Restart services
docker compose restart
```

### Debug Mode

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
export TRACE_ENABLED=true

# View detailed logs
docker compose logs -f api | grep -E "ERROR|WARNING"
```

### Health Checks

```bash
# API health
curl http://localhost:8003/health

# PostgreSQL health
docker compose exec postgres pg_isready

# Neo4j health
curl http://localhost:7474/db/neo4j/cluster/available
```

## Maintenance

### Regular Tasks

#### Daily

- Check logs for errors
- Monitor resource usage
- Verify backup completion

#### Weekly

- Update embeddings for new content
- Clean up old sessions
- Review error logs

#### Monthly

- Update dependencies
- Optimize databases
- Review performance metrics
- Test disaster recovery

### Update Procedure

**Safe Update Process**:

```bash
# 1. Backup current state
/root/scripts/backup-sage.sh
# Wait for backup to complete

# 2. Pull latest changes
cd /home/luminari/lore
git fetch origin
git log HEAD..origin/main  # Review changes
git pull origin main

# 3. Compare environment variable names only (never diff secret values)
comm -3 \
  <(sed -nE 's/^([A-Za-z_][A-Za-z0-9_]*)=.*/\1/p' .env.example | sort) \
  <(sed -nE 's/^([A-Za-z_][A-Za-z0-9_]*)=.*/\1/p' .env | sort)
# Add any missing required variables to .env

# 4. Rebuild and restart containers
docker compose build --no-cache
docker compose down
docker compose up -d

# 5. Wait for services to start
sleep 30

# 6. Run data pipeline if schema changed
# Check CHANGELOG.md for migration notes
make status
# If needed: make semantic-pipeline

# 7. Verify health
curl http://localhost:8003/ping
curl http://localhost:8003/api/v1/health
make status

# 8. Check logs for errors
docker compose logs --tail=100 api
docker compose logs --tail=50 postgres
docker compose logs --tail=50 neo4j

# 9. Test critical endpoints
./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
```

**Rollback Procedure** (if update fails):

```bash
# 1. Stop services
docker compose down

# 2. Restore from backup (see Disaster Recovery section)
BACKUP_DATE="20251112_020000"  # Your pre-update backup
cd /backup/sage
tar -xzf ${BACKUP_DATE}.tar.gz
# Follow restoration steps from Disaster Recovery section

# 3. Revert code
git log --oneline -10  # Find commit before update
git reset --hard <commit-hash>

# 4. Restart services
docker compose up -d
```

## Support

### Getting Help

- GitHub Issues: https://github.com/LuminariMUD/sage/issues
- Documentation: https://github.com/LuminariMUD/sage/tree/main/docs
- Community: Discord/Slack (if available)

### Logs Location

- API Logs: `docker compose logs api`
- PostgreSQL Logs: `docker compose logs postgres`
- Neo4j Logs: `docker compose logs neo4j`
- System Logs: `/var/log/sage/`

### Performance Metrics

- API Metrics: http://localhost:8003/metrics
- PostgreSQL Stats: `pg_stat_statements`
- Neo4j Metrics: http://localhost:7474/metrics

---

_For development setup, see the [Developer Guide](./DEVELOPER_GUIDE.md)._
_For architecture details, see the [System Architecture](./ARCHITECTURE.md)._
