# Luminari Sage - Hybrid Graph RAG System with Semantic Chunking
.PHONY: help status logs restart
.PHONY: load-canon load-draft load-all create-episodes generate-embeddings sync-to-graphiti sync-to-graphiti-ollama sync-to-graphiti-openai
.PHONY: pipeline pipeline-canon pipeline-draft pipeline-all resume rebuild
.PHONY: clear-graph clear-graph-force clear-all reset-all reset-sync reset-embeddings reset-documents
.PHONY: semantic-reset semantic-pipeline
.PHONY: graphiti-status status-graphiti benchmark-graphiti benchmark-graphiti-openai

# Support for verbose mode
ifdef VERBOSE
	VERBOSE_FLAG = --verbose
endif

# Default target
help:
	@echo "🧠 Luminari Sage - Hybrid Graph RAG with Semantic Chunking"
	@echo "=========================================================="
	@echo ""
	@echo "🚀 QUICK START:"
	@echo "  make semantic-pipeline     - Complete semantic chunking pipeline (RECOMMENDED)"
	@echo "  make semantic-reset        - Reset everything and reprocess with semantic chunking"
	@echo "  make status               - Show system status and statistics"
	@echo ""
	@echo "🔄 SEMANTIC CHUNKING PIPELINE:"
	@echo "  make load-canon           - Load canon documents into PostgreSQL"
	@echo "  make load-draft           - Load draft documents into PostgreSQL"
	@echo "  make load-all             - Load both canon and draft documents"
	@echo "  make create-episodes      - Create episodes with semantic chunking (200-500 tokens)"
	@echo "  make generate-embeddings  - Generate embeddings for episodes"
	@echo "  make sync-to-graphiti     - Sync episodes to Neo4j via Graphiti (uses GRAPHITI_PROVIDER)"
	@echo ""
	@echo "🕸️  GRAPHITI OPERATIONS:"
	@echo "  make sync-to-graphiti-ollama   - Sync with Ollama (local, free)"
	@echo "  make sync-to-graphiti-openai   - Sync with OpenAI (requires API key)"
	@echo "  make graphiti-status           - Show Graphiti/Neo4j statistics"
	@echo "  make benchmark-graphiti        - Benchmark entity extraction (Ollama)"
	@echo "  make benchmark-graphiti-openai - Benchmark entity extraction (OpenAI)"
	@echo ""
	@echo "📋 COMPLETE WORKFLOWS:"
	@echo "  make pipeline-canon       - Canon: load → episodes → embeddings → sync"
	@echo "  make pipeline-draft       - Draft: load → episodes → embeddings → sync"
	@echo "  make pipeline-all         - All: load → episodes → embeddings → sync"
	@echo "  make resume               - Resume interrupted pipeline (pending only)"
	@echo "  make rebuild              - Full rebuild: clear → reset → pipeline-canon"
	@echo ""
	@echo "🗑️  RESET & CLEANUP:"
	@echo "  make clear-all            - Clear ALL processed data (episodes + Neo4j)"
	@echo "  make clear-graph          - Clear Neo4j graph only (interactive)"
	@echo "  make clear-graph-force    - Clear Neo4j graph only (no confirmation)"
	@echo "  make reset-all            - Reset all PostgreSQL processing flags"
	@echo "  make reset-sync           - Reset Graphiti sync flags only"
	@echo "  make clear-embeddings     - Clear all embeddings (use before switching providers)"
	@echo "  make reset-documents      - Reset document processing status"
	@echo ""
	@echo "📊 MONITORING:"
	@echo "  make status               - Complete system status"
	@echo "  make embedding-status     - Check embedding generation progress"
	@echo "  make logs                 - Show API container logs"
	@echo "  make restart              - Restart all services"
	@echo ""
	@echo "⚙️  SEMANTIC CHUNKING PARAMETERS:"
	@echo "  • Base tokens: 200 (dynamic 100-500 based on complexity)"
	@echo "  • Overlap: 25% with complete sentences only"
	@echo "  • Similarity threshold: 0.7 for grouping"
	@echo "  • Uses tiktoken for consistent token counting"
	@echo ""
	@echo "📢 VERBOSE MODE:"
	@echo "  Use VERBOSE=1 for detailed output: make pipeline-canon VERBOSE=1"
	@echo ""

# =============================================================================
# DOCUMENT LOADING
# =============================================================================

.PHONY: load-canon
load-canon:
	@echo "📚 Loading canon documents into PostgreSQL..."
	@docker exec -it luminari-api python src/scripts/load_documents.py --source canon $(VERBOSE_FLAG)

.PHONY: load-draft
load-draft:
	@echo "📚 Loading draft documents into PostgreSQL..."
	@docker exec -it luminari-api python src/scripts/load_documents.py --source draft $(VERBOSE_FLAG)

.PHONY: load-all
load-all:
	@echo "📚 Loading all documents (canon + draft) into PostgreSQL..."
	@docker exec -it luminari-api python src/scripts/load_documents.py --source all $(VERBOSE_FLAG)

# =============================================================================
# SEMANTIC CHUNKING PIPELINE
# =============================================================================

.PHONY: create-episodes
create-episodes:
	@echo "🧠 Creating episodes with semantic chunking (200-500 tokens, 25% overlap)..."
	@docker exec -it luminari-api python src/scripts/create_episodes_from_documents.py \
		--base-tokens 200 --max-tokens 500 --overlap-percentage 0.25 \
		--similarity-threshold 0.7 --complexity-factor 1.5 $(VERBOSE_FLAG)

.PHONY: create-episodes-large
create-episodes-large:
	@echo "🧠 Creating large episodes with semantic chunking (300-800 tokens)..."
	@docker exec -it luminari-api python src/scripts/create_episodes_from_documents.py \
		--base-tokens 400 --max-tokens 800 --overlap-percentage 0.3 \
		--similarity-threshold 0.7 --complexity-factor 1.5 $(VERBOSE_FLAG)

.PHONY: generate-embeddings
generate-embeddings:
	@echo "🔢 Generating embeddings for episodes..."
	@docker exec -it luminari-api python src/scripts/generate_embeddings.py $(VERBOSE_FLAG)

.PHONY: sync-to-graphiti
sync-to-graphiti:
	@echo "🕸️  Syncing episodes to Graphiti/Neo4j (uses GRAPHITI_PROVIDER env var)..."
	@docker exec -it luminari-api python src/scripts/extract_entities.py $(VERBOSE_FLAG)

.PHONY: sync-to-graphiti-ollama
sync-to-graphiti-ollama:
	@echo "🕸️  Syncing episodes to Graphiti/Neo4j with Ollama..."
	@docker exec -e GRAPHITI_PROVIDER=ollama -it luminari-api python src/scripts/extract_entities.py $(VERBOSE_FLAG)

.PHONY: sync-to-graphiti-openai
sync-to-graphiti-openai:
	@echo "🕸️  Syncing episodes to Graphiti/Neo4j with OpenAI..."
	@docker exec -e GRAPHITI_PROVIDER=openai -it luminari-api python src/scripts/extract_entities.py $(VERBOSE_FLAG)

# =============================================================================
# COMPLETE WORKFLOWS
# =============================================================================

.PHONY: semantic-pipeline
semantic-pipeline: pipeline-canon
	@echo "✅ Semantic chunking pipeline complete!"

.PHONY: semantic-reset
semantic-reset:
	@echo "🔄 Resetting everything and reprocessing with semantic chunking..."
	@docker exec -it luminari-api python src/scripts/reset_semantic_chunking.py
	@echo "✅ Semantic reset complete!"

.PHONY: pipeline pipeline-canon
pipeline: pipeline-canon

pipeline-canon: load-canon create-episodes generate-embeddings sync-to-graphiti
	@echo "✅ Complete Canon pipeline finished!"

.PHONY: pipeline-draft
pipeline-draft: load-draft create-episodes generate-embeddings sync-to-graphiti
	@echo "✅ Complete Draft pipeline finished!"

.PHONY: pipeline-all
pipeline-all: load-all create-episodes generate-embeddings sync-to-graphiti
	@echo "✅ Complete All Sources pipeline finished!"

.PHONY: resume
resume:
	@echo "🔄 Resuming interrupted pipeline..."
	@docker exec -it luminari-api python src/scripts/create_episodes_from_documents.py $(VERBOSE_FLAG)
	@docker exec -it luminari-api python src/scripts/generate_embeddings.py $(VERBOSE_FLAG)
	@docker exec -it luminari-api python src/scripts/extract_entities.py $(VERBOSE_FLAG)
	@echo "✅ Pipeline resumed!"

.PHONY: rebuild
rebuild: clear-graph-force reset-all pipeline-canon
	@echo "✅ Full rebuild complete!"

# =============================================================================
# RESET & CLEANUP OPERATIONS
# =============================================================================

.PHONY: clear-all
clear-all:
	@echo "🗑️  Clearing ALL processed data (PostgreSQL episodes + Neo4j)..."
	@docker exec -it luminari-api python src/scripts/clear_all_data.py

.PHONY: clear-graph
clear-graph:
	@echo "🗑️  Clearing Neo4j graph (interactive)..."
	@docker exec -it luminari-api python src/scripts/clear_graph.py

.PHONY: clear-graph-force
clear-graph-force:
	@echo "🗑️  Force clearing Neo4j graph..."
	@docker exec luminari-api python src/scripts/clear_graph.py --yes

.PHONY: reset-all
reset-all:
	@echo "🔄 Resetting all processing flags..."
	@docker exec luminari-api python src/scripts/reset_processing.py --target all --yes

.PHONY: reset-sync
reset-sync:
	@echo "🔄 Resetting Graphiti sync flags..."
	@docker exec luminari-api python src/scripts/reset_processing.py --target sync --yes

.PHONY: reset-embeddings clear-embeddings
reset-embeddings: clear-embeddings

clear-embeddings:
	@echo "🔄 Clearing all embeddings (use before switching embedding providers)..."
	@docker exec luminari-postgres psql -U luminari -d luminari_sage -c "UPDATE episodes SET embedding = NULL;"
	@echo "✅ All embeddings cleared"

.PHONY: reset-documents
reset-documents:
	@echo "🔄 Resetting document processing status..."
	@docker exec luminari-api python src/scripts/reset_processing.py --target documents --yes

# =============================================================================
# STATUS & MONITORING
# =============================================================================

.PHONY: status
status:
	@echo "📊 Luminari Sage - Hybrid Graph RAG Status"
	@echo "==========================================="
	@echo ""
	@echo "🐳 Docker Services:"
	@docker compose -p luminari-sage ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "❌ Docker services not running"
	@echo ""
	@echo "🔍 API Health:"
	@curl -s http://localhost:8003/ping | jq . 2>/dev/null || echo "❌ API not responding"
	@echo ""
	@echo "📊 Processing Status:"
	@docker exec luminari-api python src/scripts/reset_processing.py --status 2>/dev/null || echo "❌ Could not get processing status"
	@echo ""
	@echo "🕸️  Neo4j Graph Status:"
	@docker exec luminari-api python src/scripts/clear_graph.py --yes --debug 2>/dev/null | head -20 || echo "❌ Could not get graph status"

.PHONY: status-episodes
status-episodes:
	@echo "📊 Episode Creation Status:"
	@docker exec luminari-api python src/scripts/create_episodes_from_documents.py --status

.PHONY: status-embeddings embedding-status
status-embeddings: embedding-status

embedding-status:
	@echo "📊 Embedding Status:"
	@docker exec luminari-postgres psql -U luminari -d luminari_sage -c \
		"SELECT \
			COUNT(*) as total_episodes, \
			COUNT(embedding) as with_embeddings, \
			COUNT(*) - COUNT(embedding) as missing_embeddings, \
			CASE WHEN COUNT(embedding) > 0 THEN array_length(embedding::float[], 1) ELSE NULL END as dimension \
		FROM episodes;"

.PHONY: status-processing
status-processing:
	@echo "📊 Processing Status:"
	@docker exec luminari-api python src/scripts/reset_processing.py --status

.PHONY: graphiti-status status-graphiti
graphiti-status: status-graphiti

status-graphiti:
	@echo "📊 Graphiti Status:"
	@test -n "$${NEO4J_PASSWORD:-}" || { echo "NEO4J_PASSWORD is not set" >&2; exit 1; }
	@echo ""
	@echo "Episodes processed:"
	@docker exec luminari-postgres psql -U luminari -d luminari_sage -c \
		"SELECT COUNT(*) FILTER (WHERE graphiti_synced) as processed, \
				COUNT(*) as total \
		 FROM episodes;"
	@echo ""
	@echo "Entities in knowledge graph:"
	@docker exec -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD luminari-neo4j cypher-shell \
		"MATCH (e:Entity) RETURN count(e) as entities;" --format plain
	@echo ""
	@echo "Relationships in knowledge graph:"
	@docker exec -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD luminari-neo4j cypher-shell \
		"MATCH ()-[r]->() RETURN count(r) as relationships;" --format plain
	@echo ""
	@echo "Top 10 relationship types:"
	@docker exec -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD luminari-neo4j cypher-shell \
		"MATCH ()-[r]->() RETURN DISTINCT type(r) as type, COUNT(r) as count ORDER BY count DESC LIMIT 10;" --format plain

.PHONY: benchmark-graphiti
benchmark-graphiti:
	@echo "🧪 Running Graphiti benchmark..."
	@bash scripts/benchmark_graphiti.sh ollama

.PHONY: benchmark-graphiti-openai
benchmark-graphiti-openai:
	@echo "🧪 Running Graphiti benchmark with OpenAI..."
	@bash scripts/benchmark_graphiti.sh openai

# =============================================================================
# SYSTEM OPERATIONS
# =============================================================================

.PHONY: logs
logs:
	@echo "📋 API Container logs..."
	@docker compose -p luminari-sage logs -f api

.PHONY: logs-tail
logs-tail:
	@echo "📋 API Container logs (last 50 lines)..."
	@docker compose -p luminari-sage logs --tail=50 api

.PHONY: restart
restart:
	@echo "🔄 Restarting all services..."
	@docker compose -p luminari-sage restart

.PHONY: shell
shell:
	@echo "🐚 Opening shell in API container..."
	@docker exec -it luminari-api bash

# =============================================================================
# TESTING & VALIDATION
# =============================================================================

.PHONY: test-chunking
test-chunking:
	@echo "🧪 Testing semantic chunking..."
	@docker exec -it luminari-api python src/scripts/semantic_chunker.py

.PHONY: test-api
test-api:
	@echo "🧪 Testing API endpoints..."
	@curl -s http://localhost:8003/ping || echo "❌ Ping failed"
	@curl -s http://localhost:8003/api/v1/lore/search?query=test | jq . || echo "❌ Search failed"

# =============================================================================
# DEVELOPMENT HELPERS
# =============================================================================

.PHONY: clean-logs
clean-logs:
	@echo "🧹 Cleaning Docker logs..."
	@docker system prune --volumes -f

.PHONY: watch-logs
watch-logs:
	@echo "👀 Watching logs (press Ctrl+C to stop)..."
	@docker compose -p luminari-sage logs -f

# Show all available targets
.PHONY: targets
targets:
	@echo "📋 Available Make Targets:"
	@grep '^.PHONY:' Makefile | sed 's/.PHONY: /  /' | sort | uniq
