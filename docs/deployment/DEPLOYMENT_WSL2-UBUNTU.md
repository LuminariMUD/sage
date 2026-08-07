# Luminari Sage - Ubuntu Deployment Guide

**Last Updated**: January 2025
**Target Environment**: Ubuntu 20.04+ (Native Linux)
**Version**: 0.7.12
**Status**: Production Ready

## Overview

This guide covers deploying Luminari Sage on Ubuntu Linux. The system uses Docker containers for PostgreSQL, Neo4j, and the Sage API service.

**For general deployment concepts**, refer to the main [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [System Setup](#system-setup)
3. [Docker Engine Installation](#docker-engine-installation)
4. [NVIDIA GPU Setup (Optional)](#nvidia-gpu-setup-optional)
5. [Repository Setup](#repository-setup)
6. [Environment Configuration](#environment-configuration)
7. [Docker Deployment](#docker-deployment)
8. [Data Pipeline Execution](#data-pipeline-execution)
9. [Performance Optimization](#performance-optimization)
10. [Troubleshooting](#troubleshooting)
11. [Backup and Recovery](#backup-and-recovery)

---

## Prerequisites

### System Requirements

- **OS**: Ubuntu 20.04 LTS, 22.04 LTS, or 24.04 LTS
- **RAM**: 16GB minimum (20GB+ recommended)
- **Storage**: 100GB free space (SSD strongly recommended)
- **CPU**: 4+ cores recommended
- **sudo Access**: Required for Docker and system package installation

### GPU Requirements (Optional - For Local LLM)

**Luminari Sage supports TWO deployment modes:**

1. **Local LLM Mode (100% Free, GPU Recommended)**:
   - NVIDIA GPU with 8GB+ VRAM (RTX 3060, RTX 4060, RTX 5070, etc.)
   - CUDA 11.0+ support
   - No API costs - runs entirely offline
   - Slightly lower quality than GPT-4, but excellent for development

2. **Cloud API Mode (OpenAI)**:
   - No GPU required
   - Requires OpenAI API key
   - ~$50-100/month for moderate usage
   - Best quality responses

**Check Your GPU**:

```bash
# Check if NVIDIA GPU is present
nvidia-smi

# Should show GPU model, driver version, CUDA version
# Example: RTX 5070 GPU, Driver 537.42, CUDA 12.2
```

**Minimum GPU Specs for Local LLM**:

- **8GB VRAM**: Can run 7B-8B models (qwen2.5:7b, deepseek-r1:8b) - Recommended
- **6GB VRAM**: Limited to 3B models (slower, lower quality)
- **4GB VRAM**: Not recommended for production use

**No GPU?** You can still use Luminari Sage with OpenAI API (see Cloud API Mode below).

### Required API Keys (Cloud API Mode Only)

**If using Local LLM Mode**: Skip this section - no API keys needed!

**If using Cloud API Mode**:

- **OpenAI API Key**: Required for embeddings and LLM operations
  - Get from: https://platform.openai.com/api-keys
  - Estimated cost: $50-100/month for moderate usage
  - Configure `LLM_PROVIDER=openai` in `.env`

**Hybrid Mode** (optional): Use local LLM for chat, OpenAI for Graphiti entity extraction

- Set `LLM_PROVIDER=ollama` and `GRAPHITI_PROVIDER=openai`
- Reduces costs significantly (~$20-30/month)

---

## System Setup

### Update System Packages

```bash
# Update package lists
sudo apt update

# Upgrade installed packages
sudo apt upgrade -y

# Install essential tools
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

### Enable systemd (if not already enabled)

```bash
# Verify systemd is running
systemctl status
# Should show systemd is running
```

---

## Docker Engine Installation

**DO NOT install Docker Desktop** - Use Docker Engine (native Linux Docker daemon).

### Step 1: Remove Old Docker Versions (if present)

```bash
sudo apt remove -y docker docker-engine docker.io containerd runc
```

### Step 2: Install Docker Engine

```bash
# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package lists
sudo apt update

# Install Docker Engine, containerd, and Docker Compose plugin
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### Step 3: Configure Docker Permissions

```bash
# Add your user to docker group (avoid needing sudo for docker commands)
sudo usermod -aG docker $USER

# Apply group membership (log out and back in, or use this temporary fix)
newgrp docker

# Verify Docker installation
docker --version
# Should show: Docker version 24.x or later

docker compose version
# Should show: Docker Compose version v2.x

# Test Docker
docker run hello-world
# Should download and run test container successfully
```

### Step 4: Enable Docker Service

```bash
# Enable Docker to start on boot
sudo systemctl enable docker

# Start Docker service
sudo systemctl start docker

# Verify Docker is running
sudo systemctl status docker
# Should show: active (running)
```

---

## NVIDIA GPU Setup (Optional)

**Skip this section if**:

- You're using Cloud API Mode (OpenAI)
- Your system doesn't have an NVIDIA GPU
- Your GPU has less than 6GB VRAM

**Required for**: Local LLM Mode with Ollama

### Step 1: Install NVIDIA GPU Drivers

**Check if drivers are installed**:

```bash
nvidia-smi

# Should display GPU information
# If command not found, install drivers
```

**Install NVIDIA drivers**:

```bash
# Detect recommended driver
ubuntu-drivers devices

# Install recommended driver
sudo ubuntu-drivers autoinstall

# Or install specific version
sudo apt install -y nvidia-driver-535  # Adjust version as needed

# Reboot system
sudo reboot
```

**After reboot, verify installation**:

```bash
nvidia-smi
# Should display GPU information, driver version, CUDA version
```

**Minimum Driver Version**:

- **NVIDIA Driver**: 470.x or later
- **CUDA**: 11.0+ (included with driver)
- Recommended: Driver 510.x+

### Step 2: Install NVIDIA Container Toolkit

**Required**: Allows Docker containers to access GPU

```bash
# Add NVIDIA Container Toolkit repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update package lists
sudo apt-get update

# Install NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker service
sudo systemctl restart docker
```

### Step 3: Verify GPU Access in Docker

**Test GPU access from Docker**:

```bash
# Test with NVIDIA CUDA container
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# Expected: Should display GPU information inside container
# If successful, GPU is ready for Ollama!
```

**Troubleshooting GPU Access**:

**Error: "could not select device driver"**:

```bash
# Verify NVIDIA Container Toolkit is installed
dpkg -l | grep nvidia-container-toolkit

# Restart Docker
sudo systemctl restart docker
```

**Error: "failed to initialize NVML"**:

```bash
# Check driver is loaded
nvidia-smi

# Restart system
sudo reboot
```

**Error: "nvidia-smi not found in container"**:

```bash
# Verify NVIDIA Container Toolkit is installed
dpkg -l | grep nvidia-container-toolkit

# If not installed, repeat Step 2
```

### GPU Resource Management

**Monitor GPU usage**:

```bash
# Real-time GPU monitoring
watch -n 1 nvidia-smi

# Check VRAM usage
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Expected when Ollama is running a model:
# memory.used [MiB], memory.total [MiB]
# 5500 MiB, 8192 MiB
```

**Expected VRAM usage with default models**:

- **qwen2.5:7b** (chat): ~5.5GB VRAM
- **deepseek-r1:8b** (reasoning): ~5.5GB VRAM
- **nomic-embed-text** (embeddings): ~1GB VRAM
- **Multiple models loaded**: May cause OOM - configure `OLLAMA_MAX_LOADED_MODELS=1`

---

## Repository Setup

### Step 1: Clone Repository

```bash
# Navigate to home directory or preferred location
cd ~

# Create projects directory (optional)
mkdir -p ~/projects
cd ~/projects

# Clone the repository
git clone https://github.com/LuminariMUD/sage.git
cd sage

# Verify repository contents
ls -la
# Should show: docker-compose.yml, .env.example, src/, lore_docs/, etc.
```

### Step 2: Verify Filesystem

```bash
# Check filesystem type
df -Th .
# Filesystem should show: ext4 (or similar native filesystem)

# Verify you're on local filesystem (not network mount)
pwd
# Should show: /home/username/projects/lore (or similar)
```

---

## Environment Configuration

### Step 1: Copy Environment Template

```bash
cd ~/projects/lore

# Copy example environment file
cp .env.example .env
chmod 600 .env
```

### Step 2: Generate Secure Keys

```bash
# Generate PostgreSQL password
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"

# Generate Neo4j password
python3 -c "import secrets; print('NEO4J_PASSWORD=' + secrets.token_urlsafe(32))"

# Generate API keys
python3 -c "import secrets; print('SAGE_API_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('SAGE_MCP_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('SAGE_MCP_BACKEND_KEY=' + secrets.token_urlsafe(32))"

# Copy the generated values - you'll add them to .env
```

### Step 3: Edit Environment Variables

```bash
# Edit with nano (or vim, if preferred)
nano .env
```

**Choose Your Deployment Mode**:

#### Option A: Local LLM Mode (Recommended, 100% Free)

```bash
# ============================================
# LLM Provider Configuration (100% LOCAL)
# ============================================
LLM_PROVIDER=ollama              # Use local Ollama models

# Ollama Service
OLLAMA_BASE_URL=http://ollama:11434

# Model Selection (optimized for 8GB VRAM)
OLLAMA_CHAT_MODEL=qwen2.5:7b                 # General chat (40-50 tok/s)
OLLAMA_CREATIVE_MODEL=qwen2.5:7b             # Creative writing
OLLAMA_REASONING_MODEL=deepseek-r1:8b        # Analysis & entity extraction
OLLAMA_EMBEDDING_MODEL=nomic-embed-text      # 768-dim embeddings

# Performance Tuning
OLLAMA_MAX_CONTEXT_TOKENS=4096               # Safe for 8GB VRAM
OLLAMA_CHAT_TEMPERATURE=0.7
OLLAMA_CREATIVE_TEMPERATURE=0.9
OLLAMA_EXTRACTION_TEMPERATURE=0.3

# Embedding Configuration
USE_LOCAL_EMBEDDINGS=true                     # Free local embeddings
EMBEDDING_BATCH_SIZE=32

# Graphiti Configuration (100% LOCAL)
GRAPHITI_PROVIDER=ollama                      # Use Ollama for entity extraction

# OpenAI NOT REQUIRED in this mode
# OPENAI_API_KEY can be left empty or omitted
```

#### Option B: Cloud API Mode (OpenAI)

```bash
# ============================================
# LLM Provider Configuration (OPENAI)
# ============================================
LLM_PROVIDER=openai              # Use OpenAI cloud API

# OpenAI API Key (REQUIRED)
OPENAI_API_KEY=

# OpenAI Models
LLM_MODEL=gpt-4o-mini           # Chat model
GRAPHITI_LLM_MODEL=gpt-4o-mini  # Entity extraction
EMBEDDING_MODEL=text-embedding-3-small

# Embedding Configuration
USE_OPENAI_EMBEDDINGS=true       # Use OpenAI embeddings
USE_LOCAL_EMBEDDINGS=false       # Disable local embeddings
```

#### Option C: Hybrid Mode (Cost Savings)

```bash
# ============================================
# LLM Provider Configuration (HYBRID)
# ============================================
# Use local LLM for chat, OpenAI for Graphiti only
LLM_PROVIDER=ollama

# Ollama Configuration (same as Option A)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_CREATIVE_MODEL=qwen2.5:7b
OLLAMA_REASONING_MODEL=deepseek-r1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
USE_LOCAL_EMBEDDINGS=true

# Graphiti uses OpenAI for best quality extraction
GRAPHITI_PROVIDER=openai         # Override for Graphiti only
OPENAI_API_KEY=
GRAPHITI_LLM_MODEL=gpt-4o-mini

# Estimated cost: ~$20-30/month (Graphiti only)
```

#### Required for All Modes:

```bash
# ============================================
# Database Passwords (REQUIRED - Use Generated Values)
# ============================================
POSTGRES_USER=luminari
POSTGRES_PASSWORD=<paste generated password>
POSTGRES_DB=luminari_sage
POSTGRES_PORT=5432

NEO4J_USER=neo4j
NEO4J_PASSWORD=<paste generated password>
NEO4J_BOLT_PORT=7687
NEO4J_HTTP_PORT=7474

# ============================================
# API Keys (REQUIRED - Use Generated Values)
# ============================================
SAGE_API_KEY=<paste generated key>
SAGE_MCP_KEY=<paste generated key>
SAGE_MCP_BACKEND_KEY=<paste generated key>

# ============================================
# Service Configuration
# ============================================
API_HOST=0.0.0.0
API_PORT=8003

# ============================================
# Paths (Container paths - do not change)
# ============================================
LORE_DIR=/app/lore_docs
LORE_SOURCE=canon                # canon, legends, or all

# ============================================
# Development Settings
# ============================================
DISABLE_AUTH=false               # Set to 'true' for easier local testing
DEBUG=false                      # Set to 'true' for verbose logging
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
AGENT_TYPE=langchain             # pydantic or langchain
```

### Step 4: Set File Permissions

```bash
# Restrict .env file permissions (security best practice)
chmod 600 .env

# Verify
ls -l .env
# Should show: -rw------- (only you can read/write)
```

### Step 5: Verify Environment Variables

```bash
# Check that required variables are set (adjust for your deployment mode)

# For Local LLM Mode:
grep '^LLM_PROVIDER=' .env
python3 scripts/check_secret_config.py POSTGRES_PASSWORD NEO4J_PASSWORD

# For Cloud API Mode:
python3 scripts/check_secret_config.py \
  OPENAI_API_KEY POSTGRES_PASSWORD NEO4J_PASSWORD
```

---

## Docker Deployment

### Step 1: Verify Prerequisites

```bash
cd ~/projects/lore

# Check Docker is running
docker ps
# Should NOT show: "Cannot connect to the Docker daemon"

# Check Docker Compose version
docker compose version
# Should show: v2.x or later

# Verify .env file exists
ls -la .env
# Should show: -rw------- 1 youruser youruser ... .env
```

### Step 2: Start Services

```bash
# Start all services (PostgreSQL, Neo4j, API) in detached mode
docker compose up -d

# Output should show:
# [+] Running 3/3
#  ✔ Container luminari-postgres  Started
#  ✔ Container luminari-neo4j     Started
#  ✔ Container luminari-api       Started
```

**First Launch**: Docker will:

1. Pull images (postgres:16, neo4j:5.12.0, python:3.11-slim)
2. Build the Sage API image (~5-10 minutes)
3. Create named volumes (postgres_data, neo4j_data, neo4j_logs)
4. Start services in dependency order

### Step 3: Monitor Service Startup

```bash
# Watch logs for all services
docker compose logs -f

# Or watch specific service
docker compose logs -f api

# Press Ctrl+C to stop following logs (services keep running)
```

**Expected Log Output**:

**PostgreSQL**:

```
luminari-postgres | database system is ready to accept connections
```

**Neo4j**:

```
luminari-neo4j | Started.
```

**API**:

```
luminari-api | INFO:     Application startup complete.
luminari-api | INFO:     Uvicorn running on http://0.0.0.0:8003 (Press CTRL+C to quit)
```

**Wait 30-60 seconds** for all services to fully initialize (especially Neo4j).

### Step 4: Verify Service Health

```bash
# Check container status
docker compose ps

# All services should show: STATUS = Up

# Check logs for errors
docker compose logs postgres | grep -i error
docker compose logs neo4j | grep -i error
docker compose logs api | grep -i error
```

### Step 5: Test API Endpoints

```bash
# Health check (no auth required)
curl http://localhost:8003/ping
# Expected: {"status":"ok"}

# Detailed health check
curl http://localhost:8003/api/v1/health
# Expected: {"status":"healthy","database":"connected","neo4j":"connected"}

# Test authenticated endpoint
./scripts/curl_with_sage_key.sh http://localhost:8003/api/v1/stats
# Expected: {"documents":0,"episodes":0,"entities":0,"relationships":0}
# (counts will be 0 until data pipeline runs)
```

### Step 6: Access Web Interfaces

Services are accessible from your browser:

- **API Documentation**: http://localhost:8003/docs (Swagger UI)
- **API Redoc**: http://localhost:8003/redoc
- **Neo4j Browser**: http://localhost:7474
  - Username: `neo4j`
  - Password: (value from `NEO4J_PASSWORD` in `.env`)

### Step 7: Pull Ollama Models (Local LLM Mode Only)

**Skip this section if** using Cloud API Mode (`LLM_PROVIDER=openai`)

**Required for Local LLM Mode** - download models to Ollama:

```bash
cd ~/projects/lore

# Check Ollama is running
docker compose ps ollama
# Should show: STATUS = Up

# Pull essential models (~15GB total download)
docker exec luminari-ollama ollama pull nomic-embed-text        # 274MB - Embeddings
docker exec luminari-ollama ollama pull qwen2.5:7b              # 4.7GB - Chat/Creative
docker exec luminari-ollama ollama pull deepseek-r1:8b          # 5GB - Reasoning/Entity extraction

# Verify models are installed
docker exec luminari-ollama ollama list
# Should show:
# NAME                   ID              SIZE      MODIFIED
# nomic-embed-text:latest   ...         274 MB    X seconds ago
# qwen2.5:7b                ...         4.7 GB    X seconds ago
# deepseek-r1:8b            ...         5.0 GB    X seconds ago
```

**Test model inference**:

```bash
# Test chat model
docker exec luminari-ollama ollama run qwen2.5:7b "Write a short description of crystal dwarves in 2 sentences."

# Expected: Should generate coherent 2-sentence description in ~5-10 seconds
# Speed: ~40-50 tokens/second on RTX 5070 8GB

# Monitor GPU during inference
nvidia-smi
# Should show ~5.5GB VRAM usage while model is running
```

**Optional Models** (for experimentation):

```bash
# Faster but lower quality (good for testing)
docker exec luminari-ollama ollama pull qwen2.5:3b              # 2GB - Fast chat

# Alternative to qwen2.5:7b
docker exec luminari-ollama ollama pull llama3.2:8b             # 4.7GB - Alternative chat

# Specialized for code (if needed)
docker exec luminari-ollama ollama pull codellama:7b            # 4GB - Code generation
```

**Model Storage**:

- Models are stored in Docker volume `ollama_models`
- Persistent across container restarts
- To remove models: `docker exec luminari-ollama ollama rm <model_name>`
- To check disk usage: `docker exec luminari-ollama du -sh /root/.ollama`

**Expected VRAM Usage**:

- **One model loaded**: ~5.5GB (qwen2.5:7b or deepseek-r1:8b)
- **Embeddings**: ~1GB (nomic-embed-text)
- **Total**: 6.5GB max (safe for 8GB VRAM)
- Models automatically unload when `OLLAMA_MAX_LOADED_MODELS=1`

### Troubleshooting Startup Issues

**Container won't start**:

```bash
# Check detailed logs
docker compose logs api --tail=100

# Check if ports are already in use
sudo lsof -i :8003  # API
sudo lsof -i :7474  # Neo4j Browser
sudo lsof -i :7687  # Neo4j Bolt
sudo lsof -i :5432  # PostgreSQL
```

**Out of Memory**:

```bash
# Check available memory
free -h

# Check Docker stats
docker stats

# Consider reducing container resources or adding swap
```

---

## Data Pipeline Execution

### Overview

The data pipeline processes markdown lore documents into a queryable knowledge graph:

1. **Load Documents** → PostgreSQL `lore_documents` table
2. **Create Episodes** → Semantic chunking (200-500 tokens)
3. **Generate Embeddings** → Vector embeddings for similarity search
4. **Sync to Graphiti** → Extract entities and relationships to Neo4j

**Estimated Time**: 10-30 minutes (depends on corpus size and hardware)

### Step 1: Verify Services Are Running

```bash
cd ~/projects/lore

# Check service status
docker compose ps
# All services should show: STATUS = Up

# Test database connections
docker compose exec api python -c "from src.db.postgres import test_connection; import asyncio; asyncio.run(test_connection())"
```

### Step 2: Run Complete Pipeline

```bash
# Run full semantic pipeline (recommended for first deployment)
make semantic-pipeline

# This executes four steps in sequence:
# 1. make load-canon          # Load markdown → PostgreSQL (~2-5 min)
# 2. make create-episodes     # Semantic chunking (~3-5 min)
# 3. make generate-embeddings # Vector embeddings (~5-15 min, varies by mode)
# 4. make sync-to-graphiti    # Extract entities → Neo4j (~5-30 min, varies by mode)
```

**Monitor Progress**:

```bash
# In a separate terminal, watch logs
docker compose logs -f api
```

### Step 3: Run Individual Steps (Alternative)

If you prefer to run steps individually or need to re-run specific steps:

```bash
# Step 1: Load canonical lore documents
make load-canon
# Output: Loaded X documents from lore_docs/

# Step 2: Create episodes (semantic chunks)
make create-episodes
# Output: Created Y episodes from X documents

# Step 3: Generate embeddings
make generate-embeddings
# Output: Generated embeddings for Y episodes

# Step 4: Sync to Graphiti (Neo4j)
make sync-to-graphiti
# Output: Extracted entities and relationships to Neo4j
```

### Step 4: Monitor Pipeline Status

```bash
# Check pipeline status and statistics
make status

# Expected output:
# === Luminari Sage System Status ===
# Documents: 42 (42 processed)
# Episodes: 518 (518 embedded)
# Entities: 156
# Relationships: 342
# Processing complete: 100%
```

### Step 5: Verify Data

```bash
# Test API with data
# Search lore
./scripts/curl_with_sage_key.sh \
  "http://localhost:8003/api/v1/lore/search?query=crystal+dwarves&limit=5"

# RAG query
./scripts/curl_with_sage_key.sh \
  -X POST http://localhost:8003/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who are the crystal dwarves of Nagburim?",
    "limit": 5,
    "use_graph": true
  }'

# View Neo4j graph
# Open http://localhost:7474 in browser
# Run Cypher query: MATCH (n:Entity) RETURN n LIMIT 25
```

### Performance Expectations

**Hardware**: Modern CPU (4-8 cores), 16GB RAM, SSD

#### Cloud API Mode (OpenAI)

| Step                | Time          | Notes                           |
| ------------------- | ------------- | ------------------------------- |
| Load Documents      | 2-3 min       | I/O bound, very fast on SSD     |
| Create Episodes     | 3-5 min       | CPU bound, uses tiktoken        |
| Generate Embeddings | 2-5 min       | OpenAI API, network bound       |
| Sync to Graphiti    | 10-20 min     | OpenAI API calls, network bound |
| **Total**           | **17-33 min** | Network speed dependent         |

#### Local LLM Mode (Ollama)

**Hardware**: NVIDIA GPU 8GB VRAM + modern CPU, 16GB RAM, SSD

| Step                | Time          | Notes                                |
| ------------------- | ------------- | ------------------------------------ |
| Load Documents      | 2-3 min       | I/O bound                            |
| Create Episodes     | 3-5 min       | CPU bound                            |
| Generate Embeddings | 10-20 min     | Ollama nomic-embed-text, CPU+GPU     |
| Sync to Graphiti    | 15-30 min     | Ollama deepseek-r1:8b, GPU inference |
| **Total**           | **30-58 min** | GPU accelerated, 100% free           |

**With sentence-transformers** (CPU-only fallback):

- Embedding generation: ~15-25 minutes (CPU-bound)
- Total time: ~35-58 minutes

#### Hybrid Mode (Ollama + OpenAI Graphiti)

| Step                | Time          | Notes                     |
| ------------------- | ------------- | ------------------------- |
| Load Documents      | 2-3 min       | I/O bound                 |
| Create Episodes     | 3-5 min       | CPU bound                 |
| Generate Embeddings | 10-20 min     | Ollama nomic-embed-text   |
| Sync to Graphiti    | 10-20 min     | OpenAI API (best quality) |
| **Total**           | **25-48 min** | Best balance cost/quality |

### Monitor GPU Usage (Local LLM Mode)

**During pipeline execution**:

```bash
# Terminal 1: Run pipeline
make semantic-pipeline

# Terminal 2: Monitor GPU in real-time
watch -n 1 nvidia-smi

# Expected VRAM usage:
# - Embeddings step: ~1GB (nomic-embed-text)
# - Graphiti step: ~5.5GB (deepseek-r1:8b)
# - Peak: ~6GB
```

**Check model performance**:

```bash
# View Ollama logs during inference
docker compose logs -f ollama

# Expected log output:
# - "loaded model" - Model loaded into VRAM
# - GPU utilization: 80-100% during inference
# - Tokens/second: 35-50 for 7B-8B models
```

**Performance indicators**:

- **Good**: 35-50 tokens/second, <10% OOM errors
- **Slow**: <20 tokens/second → Check GPU is being used
- **OOM**: "out of memory" errors → Reduce context or use smaller model

### Resume Interrupted Pipeline

The pipeline tracks processing status. If interrupted:

```bash
# Resume from last completed step
make semantic-pipeline

# Or reset processing flags and start fresh
make reset-all
make semantic-pipeline
```

### Clear and Rebuild

```bash
# Clear all processed data (keeps documents)
make clear-all

# Full rebuild from scratch
make rebuild
# Equivalent to: make reset-all && make semantic-pipeline
```

### Troubleshooting Pipeline Issues

**Out of Memory During Embeddings**:

```bash
# Reduce batch size in .env
echo "EMBEDDING_BATCH_SIZE=16" >> .env

# Restart API
docker compose restart api

# Re-run embeddings
make generate-embeddings
```

**Graphiti Extraction Fails**:

**For Cloud API Mode**:

```bash
# Check OpenAI API key
python3 scripts/check_secret_config.py OPENAI_API_KEY

# Check API logs
docker compose logs api | grep -i "openai\|error"

# Verify Neo4j connection
docker compose exec api python -c "from src.db.neo4j_db import test_connection; import asyncio; asyncio.run(test_connection())"
```

**For Local LLM Mode**:

```bash
# Check Ollama is running
docker compose ps ollama
# Should show: STATUS = Up

# Check models are available
docker exec luminari-ollama ollama list
# Should show: deepseek-r1:8b

# Test model manually
docker exec luminari-ollama ollama run deepseek-r1:8b "Extract entities from: The Crystal Dwarves live in Nagburim."

# Check GPU is accessible
docker exec luminari-ollama nvidia-smi
# Should NOT show "failed to initialize NVML"

# Check Ollama logs for errors
docker compose logs ollama | grep -i "error\|failed"
```

**Pipeline Hangs**:

```bash
# Check container resources
docker stats

# Check system memory
free -h

# For Local LLM Mode - check GPU
nvidia-smi
# VRAM should not be at 100%

# Check if model is stuck loading
docker compose logs ollama --tail=50
```

**Ollama Out of Memory** (Local LLM Mode only):

```bash
# Symptoms: "CUDA out of memory" or container crashes during Graphiti

# Solution 1: Ensure only ONE model loaded at a time
docker compose logs ollama | grep "loaded model"
# Should show only one model at a time

# Solution 2: Use smaller model
# Edit .env:
# OLLAMA_REASONING_MODEL=qwen2.5:3b  # Smaller than deepseek-r1:8b

# Solution 3: Reduce context window
# Edit .env:
# OLLAMA_MAX_CONTEXT_TOKENS=2048  # Down from 4096

# Solution 4: Restart Ollama to clear VRAM
docker compose restart ollama
```

---

## Performance Optimization

### 1. Docker Performance

**Enable BuildKit** (faster builds):

```bash
# Add to ~/.bashrc or ~/.zshrc
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

**Prune unused resources**:

```bash
# Clean up unused images, containers, volumes
docker system prune -a --volumes

# WARNING: This will remove ALL unused Docker resources
```

### 2. PostgreSQL Tuning

**For production or large datasets**, consider tuning PostgreSQL:

Edit PostgreSQL config in Docker container or use custom postgresql.conf:

```ini
# Memory (scaled for 16GB system)
shared_buffers = 4GB              # 25% of allocated memory
effective_cache_size = 12GB       # 75% of system memory
work_mem = 64MB                   # Increased from default
maintenance_work_mem = 1GB

# Connections
max_connections = 100

# Checkpoints
checkpoint_completion_target = 0.9
wal_buffers = 16MB

# Query Planning
random_page_cost = 1.1            # SSD optimization
effective_io_concurrency = 200    # SSD optimization
```

**Apply custom config** (optional):

```yaml
# Add to docker-compose.yml under postgres service
services:
  postgres:
    command: postgres -c shared_buffers=4GB -c effective_cache_size=12GB
```

### 3. Neo4j Tuning

**For large graphs**, configure Neo4j memory:

Edit Neo4j config in Docker container or use environment variables:

```yaml
# Add to docker-compose.yml under neo4j service
services:
  neo4j:
    environment:
      - NEO4J_server_memory_heap_initial__size=2g
      - NEO4J_server_memory_heap_max__size=4g
      - NEO4J_server_memory_pagecache_size=2g
      - NEO4J_dbms_threads_worker__count=4
```

Or create `neo4j.conf`:

```ini
# Memory
server.memory.heap.initial_size=2g
server.memory.heap.max_size=4g
server.memory.pagecache.size=2g

# Performance
dbms.threads.worker_count=4
dbms.connector.bolt.thread_pool_max_size=200
```

### 4. System Resource Monitoring

**Monitor Docker container resource usage**:

```bash
# Real-time container stats
docker stats

# Expected usage:
# luminari-postgres: ~2-4 GB RAM
# luminari-neo4j:    ~2-4 GB RAM
# luminari-api:      ~1-2 GB RAM
# luminari-ollama:   ~6-8 GB RAM (if Local LLM Mode with models loaded)
```

**Monitor system resources**:

```bash
# Memory usage
free -h

# CPU usage
htop

# Disk usage
df -h

# Docker volumes
docker system df -v
```

### 5. GPU Optimization (Local LLM Mode)

**Monitor GPU usage during operation**:

```bash
# Real-time GPU monitoring
watch -n 1 nvidia-smi

# GPU utilization should be 80-100% during inference
# Memory usage should be ~5.5GB for 7B-8B models
```

**Optimize Ollama configuration** in `.env`:

```bash
# Limit models in memory (recommended for 8GB VRAM)
OLLAMA_MAX_LOADED_MODELS=1       # Only one model loaded at a time
OLLAMA_NUM_PARALLEL=1            # One inference at a time

# GPU memory allocation
OLLAMA_GPU_MEMORY_FRACTION=0.9   # Use 90% of available VRAM
OLLAMA_NUM_GPU=1                 # Use one GPU

# Thread configuration (adjust for your CPU)
OLLAMA_NUM_THREAD=8              # Number of CPU threads for model
```

---

## Troubleshooting

### Issue 1: "Cannot connect to Docker daemon"

**Symptoms**:

```bash
docker ps
# Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
```

**Solutions**:

**A. Check Docker service status**:

```bash
sudo systemctl status docker
# If not running:
sudo systemctl start docker
```

**B. Check user permissions**:

```bash
# Ensure user is in docker group
groups $USER | grep docker

# If not, add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or use:
newgrp docker
```

**C. Check Docker socket permissions**:

```bash
sudo chmod 666 /var/run/docker.sock
```

### Issue 2: Port Already in Use

**Symptoms**:

```bash
docker compose up
# Error: Bind for 0.0.0.0:8003 failed: port is already allocated
```

**Solutions**:

**A. Find and stop conflicting process**:

```bash
# Find what's using the port
sudo lsof -i :8003

# Kill the process
sudo kill -9 <PID>
```

**B. Change port in .env**:

```bash
# Edit .env
nano .env

# Change:
API_PORT=8004  # or another unused port

# Restart services
docker compose down
docker compose up -d
```

### Issue 3: Out of Memory

**Symptoms**:

- Containers crashing
- "OOMKilled" in `docker ps -a`
- System becomes unresponsive

**Solutions**:

**A. Check system memory**:

```bash
free -h

# Check what's using memory
ps aux --sort=-%mem | head -10
```

**B. Reduce container memory usage**:

```bash
# Stop unnecessary containers
docker compose stop ollama  # If not using Local LLM

# Restart services
docker compose restart
```

**C. Add swap space**:

```bash
# Create 8GB swap file
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Issue 4: Ollama GPU Not Accessible (Local LLM Mode)

**Symptoms**:

```bash
docker exec luminari-ollama nvidia-smi
# failed to initialize NVML: Unknown Error
```

**Solutions**:

**A. Verify NVIDIA Container Toolkit**:

```bash
# Check if installed
dpkg -l | grep nvidia-container-toolkit

# If not installed, see "NVIDIA GPU Setup" section
```

**B. Restart Docker**:

```bash
sudo systemctl restart docker
```

**C. Test GPU access**:

```bash
# Test with NVIDIA CUDA container
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
# Should display GPU info
```

**D. Check driver**:

```bash
# Verify driver is loaded
nvidia-smi

# If not working, reinstall driver
sudo ubuntu-drivers autoinstall
sudo reboot
```

### Issue 5: Slow Performance

**Diagnosis**:

```bash
# Check if on slow filesystem (network mount, etc.)
df -Th ~/projects/lore
# Should show ext4 or similar local filesystem

# Check I/O performance
time dd if=/dev/zero of=test.dat bs=1M count=1024
# Should complete in <5 seconds on SSD

rm test.dat
```

**Solutions**:

- Ensure repository is on local SSD, not network mount
- Close resource-intensive applications
- Check `docker stats` for container resource usage
- Consider upgrading hardware (RAM, SSD, GPU)

### Issue 6: Pipeline Fails with API Errors (Cloud Mode)

**Symptoms**:

- "OpenAI API error: Rate limit exceeded"
- "OpenAI API error: Invalid API key"

**Solutions**:

**A. Verify API key**:

```bash
python3 scripts/check_secret_config.py OPENAI_API_KEY
```

**B. Check API quota**:

- Visit https://platform.openai.com/account/usage
- Verify you have remaining quota
- Check billing is set up

**C. Reduce API rate**:

```bash
# Edit .env to reduce batch sizes
EMBEDDING_BATCH_SIZE=16  # Down from 32
```

---

## Backup and Recovery

### Backup Docker Volumes

**PostgreSQL**:

```bash
cd ~/projects/lore

# Backup PostgreSQL
docker compose exec -T postgres pg_dump -U luminari luminari_sage > ~/backups/postgres-$(date +%Y%m%d).sql

# Compress
gzip ~/backups/postgres-$(date +%Y%m%d).sql
```

**Neo4j**:

```bash
# Backup Neo4j database
docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/backups

# Copy from container to host
docker cp luminari-neo4j:/backups/neo4j.dump ~/backups/neo4j-$(date +%Y%m%d).dump
```

**Environment Configuration**:

```bash
# Backup .env file
mkdir -p ~/backups
cp .env ~/backups/env-$(date +%Y%m%d).backup
chmod 600 ~/backups/env-$(date +%Y%m%d).backup
```

### Restore Docker Volumes

**PostgreSQL**:

```bash
# Stop API service
docker compose stop api

# Drop and recreate database
docker compose exec postgres psql -U luminari -d postgres -c "DROP DATABASE IF EXISTS luminari_sage;"
docker compose exec postgres psql -U luminari -d postgres -c "CREATE DATABASE luminari_sage;"

# Restore from backup
gunzip -c ~/backups/postgres-20250112.sql.gz | docker compose exec -T postgres psql -U luminari luminari_sage

# Restart services
docker compose restart
```

**Neo4j**:

```bash
# Stop Neo4j
docker compose stop neo4j

# Copy dump to container
docker cp ~/backups/neo4j-20250112.dump luminari-neo4j:/tmp/

# Restore
docker compose exec neo4j neo4j-admin database load neo4j --from-path=/tmp

# Start Neo4j
docker compose start neo4j
```

---

## Summary

**Ubuntu deployment of Luminari Sage requires**:

1. ✅ **Ubuntu 20.04+** with systemd
2. ✅ **Docker Engine** (NOT Docker Desktop)
3. ✅ **Repository cloned** to local filesystem
4. ✅ **Environment variables** in `.env` (API keys, passwords)
5. ✅ **NVIDIA GPU + drivers** (optional, for Local LLM Mode)

**Deployment Steps**:

1. Clone repository to `~/projects/lore`
2. Configure `.env` with API keys and passwords
3. Run `docker compose up -d`
4. Pull Ollama models (Local LLM Mode) or configure OpenAI key (Cloud API Mode)
5. Run `make semantic-pipeline`
6. Access API at http://localhost:8003

**Common Issues**:

- Docker daemon not running → `sudo systemctl start docker`
- Permission denied → `sudo usermod -aG docker $USER`
- Port conflicts → Change port in `.env`
- Out of memory → Add swap or reduce container resources
- GPU not accessible → Install NVIDIA Container Toolkit

**For more details**, see:

- General deployment concepts: [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- Architecture and development: [CLAUDE.md](../CLAUDE.md)

---

**Questions or Issues?**

- GitHub Issues: https://github.com/LuminariMUD/sage/issues
- Documentation: https://github.com/LuminariMUD/sage/tree/main/docs
