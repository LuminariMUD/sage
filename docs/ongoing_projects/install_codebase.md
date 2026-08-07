# Luminari Sage - Ubuntu Installation Checklist

**Target Environment**: Ubuntu 20.04+ (Native Linux)
**Version**: 0.7.15
**Based on**: [DEPLOYMENT_WSL2-UBUNTU.md](../deployment/DEPLOYMENT_WSL2-UBUNTU.md)

---

## Overview

This installation checklist breaks down the deployment into manageable phases. Complete each phase fully before proceeding to the next. Each phase is designed to fit within one working session.

**Estimated Total Time**: 2-4 hours (excluding model downloads)

**Deployment Mode Decision** (Choose ONE):

- [ ] **Local LLM Mode** - 100% free, requires NVIDIA GPU with 8GB+ VRAM
- [ ] **Cloud API Mode** - Requires OpenAI API key, ~$50-100/month
- [ ] **Hybrid Mode** - Local LLM + OpenAI for Graphiti, ~$20-30/month

---

## Phase 1: System Prerequisites & Setup

**Estimated Time**: 30-45 minutes
**Goal**: Update system and verify requirements

### 1.1 Pre-Installation Verification

- [ ] Verify Ubuntu version (20.04+, 22.04+, or 24.04 LTS)
  ```bash
  lsb_release -a
  ```
- [ ] Check available RAM (16GB minimum, 20GB+ recommended)
  ```bash
  free -h
  ```
- [ ] Check available storage (100GB free space on SSD)
  ```bash
  df -h
  ```
- [ ] Verify you have sudo access
  ```bash
  sudo -v
  ```

### 1.2 GPU Check (Optional - For Local LLM Mode Only)

- [ ] Check if NVIDIA GPU is present
  ```bash
  lspci | grep -i nvidia
  ```
- [ ] If GPU detected, check if drivers installed
  ```bash
  nvidia-smi
  ```
- [ ] Record GPU model and VRAM: _______________
- [ ] Verify GPU has 8GB+ VRAM for Local LLM Mode
- [ ] **If no GPU or <8GB VRAM**: Plan to use Cloud API Mode instead

### 1.3 Update System Packages

- [ ] Update package lists
  ```bash
  sudo apt update
  ```
- [ ] Upgrade installed packages
  ```bash
  sudo apt upgrade -y
  ```
- [ ] Install essential tools
  ```bash
  sudo apt install -y \
    make \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    build-essential \
    htop
  ```

### 1.4 Verify systemd

- [ ] Check systemd is running
  ```bash
  systemctl status
  # Should show systemd is running
  ```

### 1.5 Phase 1 Verification

- [ ] Ubuntu version confirmed (20.04+)
- [ ] System packages updated
- [ ] Essential tools installed
- [ ] systemd active

**Phase 1 Complete**: ☐ (Check when done)

---

## Phase 2: Docker Engine Installation

**Estimated Time**: 20-30 minutes
**Goal**: Install native Docker Engine (NOT Docker Desktop)

### 2.1 Remove Old Docker Versions (if present)

- [ ] Remove old Docker packages
  ```bash
  sudo apt remove -y docker docker-engine docker.io containerd runc
  ```

### 2.2 Install Docker Engine

- [ ] Add Docker's official GPG key
  ```bash
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  ```
- [ ] Add Docker repository
  ```bash
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  ```
- [ ] Update package lists
  ```bash
  sudo apt update
  ```
- [ ] Install Docker Engine and Docker Compose plugin
  ```bash
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  ```

### 2.3 Configure Docker Permissions

- [ ] Add user to docker group
  ```bash
  sudo usermod -aG docker $USER
  ```
- [ ] Apply group membership (temporary - log out/in for permanent)
  ```bash
  newgrp docker
  ```
- [ ] Verify Docker installation
  ```bash
  docker --version
  # Should show: Docker version 24.x or later
  ```
- [ ] Verify Docker Compose
  ```bash
  docker compose version
  # Should show: Docker Compose version v2.x
  ```
- [ ] Test Docker
  ```bash
  docker run hello-world
  # Should download and run successfully
  ```

### 2.4 Enable Docker Service

- [ ] Enable Docker to start on boot
  ```bash
  sudo systemctl enable docker
  ```
- [ ] Start Docker service
  ```bash
  sudo systemctl start docker
  ```
- [ ] Verify Docker is running
  ```bash
  sudo systemctl status docker
  # Should show: active (running)
  ```

### 2.5 Phase 2 Verification

- [ ] Docker Engine installed (NOT Docker Desktop)
- [ ] Docker commands work without sudo
- [ ] Docker service enabled and running
- [ ] Test container ran successfully

**Phase 2 Complete**: ☐ (Check when done)

---

## Phase 3: NVIDIA GPU Setup (Local LLM Mode Only)

**Estimated Time**: 30-45 minutes
**Goal**: Configure NVIDIA GPU access for Ollama
**Skip this phase if using Cloud API Mode**

### 3.1 Install NVIDIA GPU Drivers

- [ ] Check if drivers already installed
  ```bash
  nvidia-smi
  # If works, skip to Step 3.2
  ```
- [ ] If not installed, detect recommended driver
  ```bash
  ubuntu-drivers devices
  ```
- [ ] Record recommended driver: _______________
- [ ] Install recommended driver
  ```bash
  sudo ubuntu-drivers autoinstall
  ```
- [ ] Reboot system
  ```bash
  sudo reboot
  ```
- [ ] After reboot, verify driver installation
  ```bash
  nvidia-smi
  # Should display GPU info, driver version, CUDA version
  ```
- [ ] Record driver version: _______________
- [ ] Verify driver is 470.x or later

### 3.2 Install NVIDIA Container Toolkit

- [ ] Add NVIDIA Container Toolkit repository
  ```bash
  distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

  curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  ```
- [ ] Update package lists
  ```bash
  sudo apt-get update
  ```
- [ ] Install NVIDIA Container Toolkit
  ```bash
  sudo apt-get install -y nvidia-container-toolkit
  ```
- [ ] Configure Docker to use NVIDIA runtime
  ```bash
  sudo nvidia-ctk runtime configure --runtime=docker
  ```
- [ ] Restart Docker service
  ```bash
  sudo systemctl restart docker
  ```

### 3.3 Verify GPU Access in Docker

- [ ] Test GPU access from Docker container
  ```bash
  docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
  # Should display GPU information inside container
  ```
- [ ] If test succeeds, GPU is ready for Ollama!

### 3.4 Phase 3 Verification

- [ ] NVIDIA drivers installed (470.x+)
- [ ] nvidia-smi works on host
- [ ] NVIDIA Container Toolkit installed
- [ ] GPU accessible from Docker containers
- [ ] Test container successfully showed GPU

**Phase 3 Complete** (Local LLM Mode): ☐ (Check when done)
**Phase 3 Skipped** (Cloud API Mode): ☐ (Check if using Cloud API)

---

## Phase 4: Repository & Environment Setup

**Estimated Time**: 30-45 minutes
**Goal**: Clone repository and configure environment variables

### 4.1 Clone Repository

- [ ] Navigate to home directory or preferred location
  ```bash
  cd ~
  mkdir -p ~/projects
  cd ~/projects
  ```
- [ ] Clone the repository
  ```bash
  git clone https://github.com/LuminariMUD/sage.git
  cd sage
  ```
- [ ] Verify repository location
  ```bash
  pwd
  # Should show: /home/username/projects/lore
  ```
- [ ] Check repository contents
  ```bash
  ls -la
  # Should show: docker-compose.yml, .env.example, src/, etc.
  ```
- [ ] Verify filesystem type
  ```bash
  df -Th .
  # Should show: ext4 (or similar native filesystem)
  ```

### 4.2 Copy Environment Template

- [ ] Copy example environment file
  ```bash
  cp .env.example .env
  chmod 600 .env
  ```
- [ ] Verify .env file exists
  ```bash
  chmod 600 .env
  stat -c '%A %n' .env
  # Should show owner-only read/write permissions: -rw------- .env
  ```

### 4.3 Generate Secure Keys

- [ ] Generate PostgreSQL password

  ```bash
  python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
  ```

  Record: _______________________________________________

- [ ] Generate Neo4j password

  ```bash
  python3 -c "import secrets; print('NEO4J_PASSWORD=' + secrets.token_urlsafe(32))"
  ```

  Record: _______________________________________________

- [ ] Generate SAGE_API_KEY

  ```bash
  python3 -c "import secrets; print('SAGE_API_KEY=' + secrets.token_urlsafe(32))"
  ```

  Record: _______________________________________________

- [ ] Generate SAGE_MCP_KEY

  ```bash
  python3 -c "import secrets; print('SAGE_MCP_KEY=' + secrets.token_urlsafe(32))"
  ```

  Record: _______________________________________________

- [ ] Generate SAGE_MCP_BACKEND_KEY
  ```bash
  python3 -c "import secrets; print('SAGE_MCP_BACKEND_KEY=' + secrets.token_urlsafe(32))"
  ```
  Record: _______________________________________________

### 4.4 Edit .env File - Choose Your Deployment Mode

**If using Local LLM Mode (GPU required)**:

- [ ] Edit .env file
  ```bash
  nano .env
  ```
- [ ] Configure Local LLM settings:
  ```bash
  # LLM Provider Configuration (100% LOCAL)
  LLM_PROVIDER=ollama

  # Ollama Service
  OLLAMA_BASE_URL=http://ollama:11434

  # Model Selection (optimized for 8GB VRAM)
  OLLAMA_CHAT_MODEL=qwen2.5:7b
  OLLAMA_CREATIVE_MODEL=qwen2.5:7b
  OLLAMA_REASONING_MODEL=deepseek-r1:8b
  OLLAMA_EMBEDDING_MODEL=nomic-embed-text

  # Performance Tuning
  OLLAMA_MAX_CONTEXT_TOKENS=4096
  OLLAMA_CHAT_TEMPERATURE=0.7
  OLLAMA_CREATIVE_TEMPERATURE=0.9
  OLLAMA_EXTRACTION_TEMPERATURE=0.3

  # Embedding Configuration
  USE_LOCAL_EMBEDDINGS=true
  EMBEDDING_BATCH_SIZE=32

  # Graphiti Configuration (100% LOCAL)
  GRAPHITI_PROVIDER=ollama

  # OpenAI NOT REQUIRED - leave empty or omit
  ```

**If using Cloud API Mode (OpenAI)**:

- [ ] Obtain OpenAI API key from https://platform.openai.com/api-keys
- [ ] Store the API key directly in your local `.env`; do not record it in docs or tickets
- [ ] Edit .env file
  ```bash
  nano .env
  ```
- [ ] Configure Cloud API settings:
  ```bash
  # LLM Provider Configuration (OPENAI)
  LLM_PROVIDER=openai

  # OpenAI API Key (REQUIRED)
  OPENAI_API_KEY=

  # OpenAI Models
  LLM_MODEL=gpt-4o-mini
  GRAPHITI_LLM_MODEL=gpt-4o-mini
  EMBEDDING_MODEL=text-embedding-3-small

  # Embedding Configuration
  USE_OPENAI_EMBEDDINGS=true
  USE_LOCAL_EMBEDDINGS=false
  ```

**For ALL deployment modes**:

- [ ] Add generated passwords and keys to .env:
  ```bash
  # Database Passwords
  POSTGRES_USER=luminari
  POSTGRES_PASSWORD=<paste generated password>
  POSTGRES_DB=luminari_sage
  POSTGRES_PORT=5432

  NEO4J_USER=neo4j
  NEO4J_PASSWORD=<paste generated password>
  NEO4J_BOLT_PORT=7687
  NEO4J_HTTP_PORT=7474

  # API Keys
  SAGE_API_KEY=<paste generated key>
  SAGE_MCP_KEY=<paste generated key>
  SAGE_MCP_BACKEND_KEY=<paste generated key>

  # Service Configuration
  API_HOST=0.0.0.0
  API_PORT=8003

  # Paths
  LORE_DIR=/app/lore_docs
  LORE_SOURCE=canon

  # Development Settings
  DISABLE_AUTH=false
  DEBUG=false
  LOG_LEVEL=INFO
  AGENT_TYPE=langchain
  ```

### 4.5 Secure .env File

- [ ] Set file permissions
  ```bash
  chmod 600 .env
  ```
- [ ] Verify permissions
  ```bash
  ls -l .env
  # Should show: -rw------- (only you can read/write)
  ```

### 4.6 Phase 4 Verification

- [ ] Repository cloned to ~/projects/lore
- [ ] .env file created with all required variables
- [ ] Secure passwords and API keys generated
- [ ] File permissions set correctly (600)

**Phase 4 Complete**: ☐ (Check when done)

---

## Phase 5: Service Deployment & Verification

**Estimated Time**: 45-60 minutes (includes initial build and model downloads)
**Goal**: Start all services and verify they're running correctly

### 5.1 Pre-Deployment Verification

- [ ] Navigate to repository
  ```bash
  cd ~/projects/lore
  ```
- [ ] Check Docker is running
  ```bash
  docker ps
  # Should NOT show: "Cannot connect to the Docker daemon"
  ```
- [ ] Verify .env file exists and is configured
  ```bash
  ls -la .env
  grep LLM_PROVIDER .env
  # Should show your chosen provider
  ```

### 5.2 Start Services

- [ ] Start all services (first launch will build images)
  ```bash
  docker compose up -d
  ```
- [ ] Wait for build to complete (5-10 minutes for first build)
- [ ] Verify containers are running
  ```bash
  docker compose ps
  # All services should show: STATUS = Up
  ```

### 5.3 Monitor Service Startup

- [ ] Watch logs for all services
  ```bash
  docker compose logs -f
  # Press Ctrl+C to stop following (services keep running)
  ```
- [ ] Look for startup success messages:
  - PostgreSQL: "database system is ready to accept connections"
  - Neo4j: "Started."
  - API: "Application startup complete."
  - Ollama (if Local LLM): "Ollama is running"

### 5.4 Check Service Health

- [ ] Check container status
  ```bash
  docker compose ps
  # All should show: Up
  ```
- [ ] Check for errors in logs
  ```bash
  docker compose logs postgres | grep -i error
  docker compose logs neo4j | grep -i error
  docker compose logs api | grep -i error
  ```

### 5.5 Test API Endpoints

- [ ] Health check (no auth required)
  ```bash
  curl http://localhost:8003/ping
  # Expected: {"status":"ok"}
  ```
- [ ] Detailed health check
  ```bash
  curl http://localhost:8003/api/v1/health
  # Expected: {"status":"healthy","database":"connected","neo4j":"connected"}
  ```
- [ ] Test authenticated endpoint
  ```bash
  ./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
  # Expected: {"documents":0,"episodes":0,"entities":0,"relationships":0}
  ```

### 5.6 Access Web Interfaces

- [ ] Open browser and navigate to:
  - [ ] API Documentation: http://localhost:8003/docs
  - [ ] API Redoc: http://localhost:8003/redoc
  - [ ] Neo4j Browser: http://localhost:7474
    - Username: `neo4j`
    - Password: (from NEO4J_PASSWORD in .env)

### 5.7 Pull Ollama Models (Local LLM Mode Only)

**Skip this step if using Cloud API Mode**

- [ ] Check Ollama is running
  ```bash
  docker compose ps ollama
  # Should show: STATUS = Up
  ```
- [ ] Pull embedding model (~274MB)
  ```bash
  docker exec luminari-ollama ollama pull nomic-embed-text
  ```
- [ ] Pull chat model (~4.7GB, takes 5-15 minutes)
  ```bash
  docker exec luminari-ollama ollama pull qwen2.5:7b
  ```
- [ ] Pull reasoning model (~5GB, takes 5-15 minutes)
  ```bash
  docker exec luminari-ollama ollama pull deepseek-r1:8b
  ```
- [ ] Verify models are installed
  ```bash
  docker exec luminari-ollama ollama list
  # Should show all three models
  ```
- [ ] Test model inference
  ```bash
  docker exec luminari-ollama ollama run qwen2.5:7b "Write a short description of crystal dwarves in 2 sentences."
  # Should generate coherent text in ~5-10 seconds
  ```

### 5.8 Monitor GPU Usage (Local LLM Mode Only)

**Skip this step if using Cloud API Mode**

- [ ] Monitor GPU while model is running
  ```bash
  nvidia-smi
  # Should show ~5.5GB VRAM usage for 7B-8B models
  ```
- [ ] Record VRAM usage: _______________

### 5.9 Phase 5 Verification

- [ ] All Docker containers running (postgres, neo4j, api)
- [ ] Ollama running (Local LLM) or OpenAI configured (Cloud API)
- [ ] API endpoints responding correctly
- [ ] Web interfaces accessible
- [ ] Models downloaded and tested (Local LLM Mode)
- [ ] GPU showing expected VRAM usage (Local LLM Mode)

**Phase 5 Complete**: ☐ (Check when done)

---

## Phase 6: Data Pipeline Execution

**Estimated Time**: 30-60 minutes (varies by mode and hardware)
**Goal**: Load lore documents and build knowledge graph

### 6.1 Pre-Pipeline Verification

- [ ] Verify all services are running
  ```bash
  docker compose ps
  # All should show: Up
  ```
- [ ] Check API is responding
  ```bash
  curl http://localhost:8003/ping
  # Should return: {"status":"ok"}
  ```

### 6.2 Run Complete Pipeline

- [ ] Start complete semantic pipeline
  ```bash
  make semantic-pipeline
  ```
  **Note**: This runs 4 steps sequentially:
  1. Load documents → PostgreSQL (~2-5 min)
  2. Create episodes (semantic chunks) (~3-5 min)
  3. Generate embeddings (~5-20 min depending on mode)
  4. Sync to Graphiti (Neo4j) (~5-30 min depending on mode)

### 6.3 Monitor Pipeline Progress

- [ ] In a separate terminal, watch API logs
  ```bash
  docker compose logs -f api
  ```
- [ ] Monitor for errors or warnings
- [ ] For Local LLM Mode: Monitor GPU usage
  ```bash
  watch -n 1 nvidia-smi
  # Should show VRAM usage during processing
  ```

### 6.4 Expected Pipeline Times

**Cloud API Mode** (estimated):

- Load Documents: 2-3 min
- Create Episodes: 3-5 min
- Generate Embeddings: 2-5 min (OpenAI API)
- Sync to Graphiti: 10-20 min (OpenAI API)
- **Total**: ~17-33 min

**Local LLM Mode** (estimated):

- Load Documents: 2-3 min
- Create Episodes: 3-5 min
- Generate Embeddings: 10-20 min (Ollama)
- Sync to Graphiti: 15-30 min (Ollama)
- **Total**: ~30-58 min

### 6.5 Verify Pipeline Status

- [ ] Check pipeline completion
  ```bash
  make status
  ```
- [ ] Expected output should show:
  - Documents: 42 (or current count)
  - Episodes: 518 (or current count)
  - Entities: 100+ (varies)
  - Relationships: 200+ (varies)
  - Processing complete: 100%

### 6.6 Test Data Availability

- [ ] Search lore documents
  ```bash
  ./scripts/curl_with_sage_key.sh \
    "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves&limit=5"
  # Should return search results
  ```
- [ ] Test RAG query
  ```bash
  ./scripts/curl_with_sage_key.sh \
    -X POST http://localhost:8003/api/v1/rag/query \
    -H "Content-Type: application/json" \
    -d '{"query": "Who are the crystal dwarves of Nagburim?", "limit": 5, "use_graph": true}'
  # Should return RAG response with context
  ```

### 6.7 Verify Neo4j Graph

- [ ] Open Neo4j Browser: http://localhost:7474
- [ ] Login with credentials from .env
- [ ] Run Cypher query to view entities:
  ```cypher
  MATCH (n:Entity) RETURN n LIMIT 25
  ```
- [ ] Verify entities are created
- [ ] Run query to view relationships:
  ```cypher
  MATCH (a:Entity)-[r]->(b:Entity) RETURN a, r, b LIMIT 25
  ```

### 6.8 Troubleshooting Pipeline Issues

**If pipeline fails during embeddings**:

- [ ] Check logs for errors
  ```bash
  docker compose logs api | grep -i "error\|failed"
  ```
- [ ] For Local LLM: Check Ollama is responding
  ```bash
  docker exec luminari-ollama ollama list
  ```
- [ ] For Cloud API: Verify OpenAI API key is correct
  ```bash
  python3 scripts/check_secret_config.py OPENAI_API_KEY
  ```

**If pipeline fails during Graphiti sync**:

- [ ] Check Neo4j is running
  ```bash
  docker compose ps neo4j
  ```
- [ ] Check Neo4j logs
  ```bash
  docker compose logs neo4j | tail -50
  ```
- [ ] For Local LLM: Monitor GPU memory
  ```bash
  nvidia-smi
  # If VRAM at 100%, models may be OOM
  ```

### 6.9 Phase 6 Verification

- [ ] Pipeline completed without errors
- [ ] make status shows expected counts
- [ ] Search endpoints return results
- [ ] RAG query works correctly
- [ ] Neo4j graph contains entities and relationships
- [ ] Data is accessible through API

**Phase 6 Complete**: ☐ (Check when done)

---

## Phase 7: Performance Optimization & Final Validation

**Estimated Time**: 15-20 minutes
**Goal**: Optimize system performance and validate installation

### 7.1 Monitor System Resources

- [ ] Monitor system memory usage
  ```bash
  free -h
  ```
- [ ] Record system memory usage: _____ GB used / _____ GB total

- [ ] Monitor Docker container stats
  ```bash
  docker stats --no-stream
  ```
- [ ] Record resource usage:
  - PostgreSQL: _____ GB RAM
  - Neo4j: _____ GB RAM
  - API: _____ GB RAM
  - Ollama (if applicable): _____ GB RAM

### 7.2 Performance Benchmarking

- [ ] Test search performance

  ```bash
  time ./scripts/curl_with_sage_key.sh \
    "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves&limit=10" \
    > /dev/null
  ```

  Response time: _____ seconds

- [ ] Test RAG query performance
  ```bash
  time ./scripts/curl_with_sage_key.sh \
    -X POST http://localhost:8003/api/v1/rag/query \
    -H "Content-Type: application/json" \
    -d '{"query": "Who are the crystal dwarves?", "limit": 5}' > /dev/null
  ```
  Response time: _____ seconds

### 7.3 Backup Configuration

- [ ] Backup .env file
  ```bash
  install -d -m 0700 ~/backups
  install -m 0600 .env ~/backups/env-$(date +%Y%m%d).backup
  ```
- [ ] Record backup location: _______________

### 7.4 Final System Validation

- [ ] All services running
  ```bash
  docker compose ps
  # All should show: Up
  ```
- [ ] Health check passes
  ```bash
  curl http://localhost:8003/api/v1/health
  # Should show all components healthy
  ```
- [ ] Database has data
  ```bash
  ./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
  # Should show non-zero counts
  ```
- [ ] Web interfaces accessible from browser
  - [ ] http://localhost:8003/docs
  - [ ] http://localhost:7474

### 7.5 Record System Configuration

**Record final system specs for troubleshooting**:

- Ubuntu Version: _______________
- Docker Version: _______________
- Docker Compose Version: _______________
- Deployment Mode: [ ] Local LLM [ ] Cloud API [ ] Hybrid
- GPU Model (if applicable): _______________
- Total RAM: _____ GB
- Pipeline Completion Time: _____ minutes

### 7.6 Phase 7 Verification

- [ ] Resource usage is within expected ranges
- [ ] Performance benchmarks completed
- [ ] Backups created
- [ ] Final validation successful
- [ ] System configuration documented

**Phase 7 Complete**: ☐ (Check when done)

---

## Installation Complete! 🎉

### Quick Reference - Common Commands

**Service Management**:

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f api

# Restart service
docker compose restart api
```

**Data Pipeline**:

```bash
# Complete pipeline
make semantic-pipeline

# Check status
make status

# Rebuild from scratch
make rebuild
```

**Testing**:

```bash
# Health check
curl http://localhost:8003/ping

# Search lore
./scripts/curl_with_sage_key.sh \
  "http://localhost:8003/api/v1/lore/search?query=dwarves"
```

**GPU Monitoring** (Local LLM Mode):

```bash
# Monitor GPU
nvidia-smi

# Monitor GPU in real-time
watch -n 1 nvidia-smi
```

### Next Steps

- [ ] Review API documentation: http://localhost:8003/docs
- [ ] Explore Neo4j graph: http://localhost:7474
- [ ] Read main documentation: [CLAUDE.md](../CLAUDE.md)
- [ ] Review troubleshooting guide: [DEPLOYMENT_WSL2-UBUNTU.md](../deployment/DEPLOYMENT_WSL2-UBUNTU.md#troubleshooting)

### Troubleshooting Resources

If you encounter issues:

1. Check service logs: `docker compose logs -f`
2. Verify resource allocation: `free -h` and `docker stats`
3. Review troubleshooting section in deployment guide
4. Check GitHub issues: https://github.com/LuminariMUD/sage/issues

---

**Installation Date**: _______________
**Completed By**: _______________
**Total Installation Time**: _____ hours

**All Phases Complete**: ☐ (Final check when all phases done)
