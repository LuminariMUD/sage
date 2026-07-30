# Luminari Sage - Deployment Configuration

## Confirmed Decisions

### Infrastructure

- **Domain**: sage.luminarimud.com (subdomain of main game)
- **Hosting**: Self-hosted Docker containers
- **Deployment**: GitHub Actions CI/CD
- **Backups**: Local backups only
- **SSL**: Let's Encrypt via certbot

### AI Configuration

- **Embedding Model**: text-embedding-3-small
  - Cost: $0.00002/1k tokens (5x cheaper than ada-002)
  - Performance: Better than ada-002
  - Dimension: 1536
- **Analysis Model**: TBD (OpenAI vs Claude)
- **Fallback**: Will add once primary provider chosen

### Content Scope

- **Include**: All [ESTABLISHED] content
- **Exclude**:
  - [PROPOSED] sections
  - [DRAFT] sections
  - README.md, TODO.md, CHANGELOG.md (meta files)
  - Work-in-progress documents

### MUD Integration

- **Codebase**: LuminariMUD
- **Priority**: After core system complete
- **Interface**: TCP socket on port 4001

## System Architecture for sage.luminarimud.com

```nginx
# nginx.conf for subdomain routing
server {
    listen 80;
    server_name sage.luminarimud.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name sage.luminarimud.com;

    ssl_certificate /etc/letsencrypt/live/sage.luminarimud.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sage.luminarimud.com/privkey.pem;

    # Web interface
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API endpoints
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket for Discord bot status
    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Docker Compose Configuration

```yaml
version: "3.8"

services:
  postgresql:
    image: pgvector/pgvector:0.8.6-pg18
    container_name: sage-postgresql
    environment:
      POSTGRES_DB: luminari_sage
      POSTGRES_USER: sage_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql # PG18 uses a version subdir; do not mount at .../data
      - ./schemas/postgresql_schema.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "127.0.0.1:5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sage_user -d luminari_sage"]
      interval: 10s
      timeout: 5s
      retries: 5

  neo4j:
    image: neo4j:2026.06.0-community
    container_name: sage-neo4j
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      NEO4J_dbms_memory_pagecache_size: 1G
      NEO4J_dbms_memory_heap_initial__size: 1G
      NEO4J_dbms_memory_heap_max__size: 2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./schemas/neo4j_schema.cypher:/var/lib/neo4j/import/init.cypher
    ports:
      - "127.0.0.1:7474:7474" # Browser
      - "127.0.0.1:7687:7687" # Bolt
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: sage-api
    environment:
      POSTGRES_URL: postgresql://sage_user:${POSTGRES_PASSWORD}@postgresql:5432/luminari_sage
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      JWT_SECRET: ${JWT_SECRET}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      GITHUB_CLIENT_ID: ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET}
      OPENAI_API_KEY: ${OPENAI_API_KEY} # For PydanticAI agents
      EMBEDDING_MODEL: sentence-transformers/all-MiniLM-L6-v2
      EMBEDDING_DIMENSION: 384
      APP_URL: https://sage.luminarimud.com
    depends_on:
      postgresql:
        condition: service_healthy
      neo4j:
        condition: service_started
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./lore:/app/lore:ro
      - ./logs:/app/logs
    restart: unless-stopped

  discord-bot:
    build: ./discord-bot
    container_name: sage-discord
    environment:
      DISCORD_TOKEN: ${DISCORD_TOKEN}
      API_URL: http://api:8000
      API_KEY: ${INTERNAL_API_KEY}
    depends_on:
      - api
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs

volumes:
  postgres_data:
  neo4j_data:
  neo4j_logs:
  redis_data:
```

## Estimated Resource Requirements

### Current Scale (5-10 users)

```yaml
Minimum Requirements:
  CPU: 2 cores
  RAM: 4GB
  Storage: 50GB

Recommended:
  CPU: 4 cores
  RAM: 8GB
  Storage: 100GB

Container Allocation:
  PostgreSQL: 1.5GB RAM
  Neo4j: 2GB RAM
  API: 1GB RAM
  Discord Bot: 512MB RAM
  Redis (optional): 512MB RAM
```

### Growth Planning (up to 50 users)

```yaml
Scale Triggers:
  - If response time > 500ms consistently
  - If RAM usage > 80% consistently
  - If storage > 80% full

Upgrade Path:
  CPU: 4 → 8 cores
  RAM: 8GB → 16GB
  Storage: 100GB → 250GB

Optimization Options:
  - Add Redis cache for session/query caching
  - Scale Neo4j with read replicas
  - Add pgbouncer for PostgreSQL connection pooling
  - Separate Graphiti processing to worker nodes
  - Add read replica for PostgreSQL
```

## Environment Variables (.env)

```bash
# Database
POSTGRES_PASSWORD=
NEO4J_PASSWORD=

# JWT
JWT_SECRET=

# OAuth (Google)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# OAuth (GitHub)
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# AI (choose one when decided)
OPENAI_API_KEY=
# ANTHROPIC_API_KEY=

# Discord
DISCORD_TOKEN=

# Internal
INTERNAL_API_KEY=

# Domain
APP_URL=https://sage.luminarimud.com
```

## GitHub Actions Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy to sage.luminarimud.com

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Deploy to Server
        uses: appleboy/ssh-action@master
        with:
          host: luminarimud.com
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /opt/luminari-sage
            git pull origin main
            docker-compose build --no-cache api discord-bot
            docker-compose up -d
            docker system prune -f

            # Run migrations if needed
            docker exec sage-api python scripts/migrate_schema.py

            # Health check
            sleep 10
            curl -f https://sage.luminarimud.com/health || exit 1
```

## Backup Configuration

```bash
#!/bin/bash
# /opt/luminari-sage/scripts/backup.sh

BACKUP_DIR="/backups/luminari-sage"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory
mkdir -p $BACKUP_DIR

echo "Starting backup at $DATE"

# Backup PostgreSQL
echo "Backing up PostgreSQL..."
docker exec sage-postgresql pg_dump \
    -U sage_user \
    luminari_sage | gzip > $BACKUP_DIR/postgresql_$DATE.sql.gz

# Backup Neo4j
echo "Backing up Neo4j..."
docker exec sage-neo4j neo4j-admin database dump neo4j \
    --to-path=/tmp/neo4j_backup_$DATE.dump && \
    docker cp sage-neo4j:/tmp/neo4j_backup_$DATE.dump $BACKUP_DIR/

# Backup environment
cp /opt/luminari-sage/.env $BACKUP_DIR/env_$DATE

# Remove old backups
echo "Cleaning old backups..."
find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete

echo "Backup complete!"

# Verify backup sizes
du -sh $BACKUP_DIR/postgresql_$DATE.sql.gz
du -sh $BACKUP_DIR/neo4j_backup_$DATE.dump
```

## Crontab Entry

```cron
# Add to root's crontab
# Daily backup at 3 AM
0 3 * * * /opt/luminari-sage/scripts/backup.sh >> /var/log/sage-backup.log 2>&1

# Weekly restart to clear any memory leaks (Sunday 4 AM)
0 4 * * 0 cd /opt/luminari-sage && docker-compose restart >> /var/log/sage-restart.log 2>&1
```

## Initial Setup Commands

```bash
# 1. Clone repository
cd /opt
git clone https://github.com/LuminariMUD/sage.git
cd luminari-sage

# 2. Set up environment
cp .env.example .env
chmod 600 .env
# Edit .env with your values
nano .env

# 3. Set up SSL certificate
sudo certbot certonly --standalone -d sage.luminarimud.com

# 4. Create necessary directories
mkdir -p logs backups

# 5. Set permissions
chmod +x scripts/*.sh

# 6. Initial deployment
docker-compose up -d

# 7. Run initial migration
docker exec sage-api python scripts/initial_migration.py

# 8. Set up cron jobs
crontab -e
# Add the backup and restart entries

# 9. Verify everything is running
docker-compose ps
curl https://sage.luminarimud.com/health
```

## Development Workflow

```bash
# Local development
git clone https://github.com/LuminariMUD/sage.git
cd luminari-sage

# Create feature branch
git checkout -b feature/new-feature

# Make changes and test locally
docker-compose -f docker-compose.dev.yml up

# Commit and push
git add .
git commit -m "Add new feature"
git push origin feature/new-feature

# Create PR, review, merge to main
# GitHub Actions automatically deploys to sage.luminarimud.com
```

## Monitoring Endpoints

```python
# Health check endpoint
GET https://sage.luminarimud.com/health

# Metrics endpoint (Prometheus format)
GET https://sage.luminarimud.com/metrics

# Stats endpoint (human readable)
GET https://sage.luminarimud.com/api/v1/stats
```

---

_Configuration confirmed and ready for implementation_
_Domain: sage.luminarimud.com_
_Embedding: text-embedding-3-small_
_MUD: LuminariMUD codebase_
