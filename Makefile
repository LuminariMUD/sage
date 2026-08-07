# Luminari Sage - Hybrid Graph RAG System with Semantic Chunking
.PHONY: help dev down status logs restart provider-stack-plan test test-all
.PHONY: load-canon load-draft load-all create-episodes generate-embeddings sync-to-graphiti sync-to-graphiti-ollama sync-to-graphiti-openai
.PHONY: pipeline pipeline-canon pipeline-draft pipeline-all resume rebuild
.PHONY: clear-graph clear-graph-force clear-all reset-all reset-sync reset-embeddings reset-documents
.PHONY: semantic-reset semantic-pipeline
.PHONY: graphiti-status status-graphiti graph-audit graph-audit-json graph-sync-status graph-sync-run-summary graph-sync-run-summary-json graph-quality-report graph-quality-report-json graph-sync-list graph-sync-recover-expired graph-sync-retry-waiting graph-sync-retry-quarantined graph-rebuild-status graph-rebuild-plan graph-rebuild-prepare graph-rebuild-finalize backup-provider-upgrade verify-provider-upgrade-backup db-migrate-status db-migrate-check db-migrate embedding-preflight embedding-preflight-json embedding-profile-activate embedding-shadow-status embedding-shadow-status-json embedding-shadow-register embedding-shadow-backfill embedding-shadow-recover-run embedding-shadow-build-index retrieval-corpus-check retrieval-corpus-check-json benchmark-retrieval benchmark-retrieval-json benchmark-shadow-retrieval benchmark-shadow-retrieval-json benchmark-graphiti benchmark-graphiti-openai provider-config-check provider-config-check-json provider-text-probe provider-embedding-probe

# Capability-aware host launcher. It reuses the model-profile resolver and
# applies the no-Ollama override only when every selected capability is cloud.
PROVIDER_COMPOSE = python3 src/scripts/compose_provider_stack.py

# Support for verbose mode
ifdef VERBOSE
	VERBOSE_FLAG = --verbose
	GRAPHITI_DEBUG_FLAG = --verbose
endif

ifdef MAX_EPISODES
	GRAPH_SYNC_MAX_FLAG = --max-episodes $(MAX_EPISODES)
endif

ifdef GRAPHITI_BENCHMARK_MAX_CALLS
GRAPHITI_BENCHMARK_MAX_CALLS_FLAG = --max-provider-calls "$(GRAPHITI_BENCHMARK_MAX_CALLS)"
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
	@echo "  make sync-to-graphiti CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC - Run durable graph sync"
	@echo ""
	@echo "🕸️  GRAPHITI OPERATIONS:"
	@echo "  make sync-to-graphiti-ollama   - Sync with Ollama (local, free)"
	@echo "  make sync-to-graphiti-openai   - Sync with OpenAI (requires API key)"
	@echo "  make graphiti-status           - Show Graphiti/Neo4j statistics"
	@echo "  make graph-audit              - Reconcile PostgreSQL and Neo4j (read-only)"
	@echo "  make graph-audit-json         - Emit machine-readable reconciliation JSON"
	@echo "  make graph-sync-status        - Show durable graph job/run state (read-only)"
	@echo "  make graph-sync-run-summary   - Show latest durable throughput/ETA/failures"
	@echo "  make graph-sync-run-summary-json - Emit latest durable run summary as JSON"
	@echo "  make graph-quality-report     - Show separate relationship-quality evidence"
	@echo "  make graph-quality-report-json - Emit relationship-quality evidence as JSON"
	@echo "  make graph-sync-list          - List failed/active graph jobs (read-only)"
	@echo "  make graph-sync-recover-expired - Requeue or quarantine expired leases"
	@echo "  make graph-sync-retry-waiting EPISODE_IDS='...' - Retry waiting jobs"
	@echo "  make graph-sync-retry-quarantined EPISODE_IDS='...' CONFIRM=1 - Retry quarantined"
	@echo "  make graph-rebuild-status     - Inspect durable rebuild state and event history"
	@echo "  make graph-rebuild-plan       - Check rebuild readiness without mutation"
	@echo "  make graph-rebuild-prepare BACKUP_REFERENCE=... CONFIRM_GRAPH_REBUILD=... - Requeue and clear safely"
	@echo "  make graph-rebuild-finalize CONFIRM_GRAPH_REBUILD_FINALIZE=... - Accept a clean rebuilt graph"
	@echo "  make backup-provider-upgrade BACKUP_REFERENCE=... - Create verified DB backups"
	@echo "  make verify-provider-upgrade-backup BACKUP_REFERENCE=... - Verify backup gate"
	@echo "  make db-migrate-status        - Show immutable PostgreSQL migration status"
	@echo "  make db-migrate-check         - Fail when PostgreSQL migrations are pending"
	@echo "  make db-migrate BACKUP_REFERENCE=... - Apply after verified backups"
	@echo "  make embedding-preflight      - Check vector dimensions, profiles, indexes, and counts"
	@echo "  make embedding-preflight-json - Emit the read-only embedding preflight as JSON"
	@echo "  make embedding-profile-activate CONFIRM_EMBEDDING_PROFILE=... - Activate metadata only"
	@echo "  make embedding-shadow-status  - Inspect candidate spaces read-only"
	@echo "  make embedding-shadow-register SHADOW_EMBEDDING_PROVIDER=... CONFIRM_SHADOW_EMBEDDING=... - Register candidate metadata"
	@echo "  make embedding-shadow-backfill SHADOW_EMBEDDING_PROVIDER=... CONFIRM_SHADOW_EMBEDDING=... - Run bounded candidate batches"
	@echo "  make embedding-shadow-recover-run SHADOW_EMBEDDING_RUN_ID=... CONFIRM_SHADOW_EMBEDDING=... - Finalize an abandoned run"
	@echo "  make embedding-shadow-build-index SHADOW_EMBEDDING_PROVIDER=... CONFIRM_SHADOW_EMBEDDING=... - Build candidate HNSW index"
	@echo "  make retrieval-corpus-check   - Reconcile retrieval judgments read-only"
	@echo "  make retrieval-corpus-check-json - Emit corpus reconciliation as JSON"
	@echo "  make benchmark-retrieval CONFIRM_RETRIEVAL_BENCHMARK=RUN_RETRIEVAL_BENCHMARK - Active-index quality benchmark"
	@echo "  make benchmark-shadow-retrieval SHADOW_EMBEDDING_PROVIDER=... CONFIRM_RETRIEVAL_BENCHMARK=... - Candidate quality benchmark"
	@echo "  make provider-config-check    - Validate and show sanitized provider profiles"
	@echo "  make provider-config-check-json - Emit sanitized provider profiles as JSON"
	@echo "  make provider-stack-plan      - Show whether local Ollama services are required"
	@echo "  make provider-text-probe CONFIRM_PROVIDER_PROBE=RUN_PROVIDER_PROBE - One bounded text call"
	@echo "  make provider-embedding-probe CONFIRM_PROVIDER_PROBE=RUN_PROVIDER_PROBE - One bounded embedding call"
	@echo "  make benchmark-graphiti CONFIRM_GRAPHITI_BENCHMARK=RUN_GRAPHITI_BENCHMARK - Fixed-corpus extraction benchmark"
	@echo ""
	@echo "📋 COMPLETE WORKFLOWS:"
	@echo "  make pipeline-canon       - Canon: load → episodes → embeddings → sync"
	@echo "  make pipeline-draft       - Draft: load → episodes → embeddings → sync"
	@echo "  make pipeline-all         - All: load → episodes → embeddings → sync"
	@echo "  make resume               - Resume interrupted pipeline (pending only)"
	@echo "  make rebuild              - Backup-gated durable graph rebuild (three exact confirmations)"
	@echo ""
	@echo "🗑️  RESET & CLEANUP:"
	@echo "  make clear-all            - Clear ALL processed data (episodes + Neo4j)"
	@echo "  make clear-graph          - Retired; use graph-rebuild-prepare"
	@echo "  make clear-graph-force    - Retired; use graph-rebuild-prepare"
	@echo "  make reset-all            - Retired; use capability-specific safe workflows"
	@echo "  make reset-sync           - Retired; use graph-rebuild-prepare"
	@echo "  make clear-embeddings     - Clear all embeddings (use before switching providers)"
	@echo "  make reset-documents      - Reset document processing status"
	@echo ""
	@echo "📊 MONITORING:"
	@echo "  make status               - Complete system status"
	@echo "  make embedding-status     - Check embedding generation progress"
	@echo "  make logs                 - Show API container logs"
	@echo "  make restart              - Restart all services"
	@echo "  make test                 - Run fast tests in the API container"
	@echo "  make test-all             - Run every test, including live/slow suites"
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
	@docker compose exec -T api python src/scripts/load_documents.py --source canon $(VERBOSE_FLAG)

.PHONY: load-draft
load-draft:
	@echo "📚 Loading draft documents into PostgreSQL..."
	@docker compose exec -T api python src/scripts/load_documents.py --source draft $(VERBOSE_FLAG)

.PHONY: load-all
load-all:
	@echo "📚 Loading all documents (canon + draft) into PostgreSQL..."
	@docker compose exec -T api python src/scripts/load_documents.py --source all $(VERBOSE_FLAG)

# =============================================================================
# SEMANTIC CHUNKING PIPELINE
# =============================================================================

.PHONY: create-episodes
create-episodes:
	@echo "🧠 Creating episodes with semantic chunking (200-500 tokens, 25% overlap)..."
	@docker compose exec -T api python src/scripts/create_episodes_from_documents.py \
		--base-tokens 200 --max-tokens 500 --overlap-percentage 0.25 \
		--similarity-threshold 0.7 --complexity-factor 1.5 $(VERBOSE_FLAG)

.PHONY: create-episodes-large
create-episodes-large:
	@echo "🧠 Creating large episodes with semantic chunking (300-800 tokens)..."
	@docker compose exec -T api python src/scripts/create_episodes_from_documents.py \
		--base-tokens 400 --max-tokens 800 --overlap-percentage 0.3 \
		--similarity-threshold 0.7 --complexity-factor 1.5 $(VERBOSE_FLAG)

.PHONY: generate-embeddings
generate-embeddings:
	@echo "🔢 Generating embeddings for episodes..."
	@docker compose exec -T api python src/scripts/generate_embeddings.py $(VERBOSE_FLAG)

.PHONY: sync-to-graphiti
sync-to-graphiti:
	@test "$(CONFIRM_GRAPH_SYNC)" = "RUN_DURABLE_GRAPH_SYNC" || \
		(echo "CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC is required" >&2; exit 2)
	@echo "[graph-sync] Starting explicitly confirmed durable synchronization..."
	@docker compose run --rm --no-deps api python src/scripts/sync_episodes_to_graphiti.py \
		--run --confirm "$(CONFIRM_GRAPH_SYNC)" $(GRAPH_SYNC_MAX_FLAG) $(GRAPHITI_DEBUG_FLAG)

.PHONY: sync-to-graphiti-ollama
sync-to-graphiti-ollama:
	@test "$(CONFIRM_GRAPH_SYNC)" = "RUN_DURABLE_GRAPH_SYNC" || \
		(echo "CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC is required" >&2; exit 2)
	@echo "[graph-sync] Starting explicitly confirmed durable sync with Ollama..."
	@docker compose run --rm --no-deps -e GRAPHITI_PROVIDER=ollama api \
		python src/scripts/sync_episodes_to_graphiti.py --run \
		--confirm "$(CONFIRM_GRAPH_SYNC)" $(GRAPH_SYNC_MAX_FLAG) $(GRAPHITI_DEBUG_FLAG)

.PHONY: sync-to-graphiti-openai
sync-to-graphiti-openai:
	@test "$(CONFIRM_GRAPH_SYNC)" = "RUN_DURABLE_GRAPH_SYNC" || \
		(echo "CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC is required" >&2; exit 2)
	@echo "[graph-sync] Starting explicitly confirmed durable sync with OpenAI..."
	@docker compose run --rm --no-deps -e GRAPHITI_PROVIDER=openai api \
		python src/scripts/sync_episodes_to_graphiti.py --run \
		--confirm "$(CONFIRM_GRAPH_SYNC)" $(GRAPH_SYNC_MAX_FLAG) $(GRAPHITI_DEBUG_FLAG)

# =============================================================================
# COMPLETE WORKFLOWS
# =============================================================================

.PHONY: semantic-pipeline
semantic-pipeline: pipeline-canon
	@echo "✅ Semantic chunking pipeline complete!"

.PHONY: semantic-reset
semantic-reset:
	@echo "🔄 Resetting everything and reprocessing with semantic chunking..."
	@docker compose exec -T api python src/scripts/reset_semantic_chunking.py
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
	@docker compose exec -T api python src/scripts/create_episodes_from_documents.py $(VERBOSE_FLAG)
	@docker compose exec -T api python src/scripts/generate_embeddings.py $(VERBOSE_FLAG)
	@$(MAKE) sync-to-graphiti CONFIRM_GRAPH_SYNC="$(CONFIRM_GRAPH_SYNC)" \
		MAX_EPISODES="$(MAX_EPISODES)" $(if $(VERBOSE),VERBOSE=1,)
	@echo "✅ Pipeline resumed!"

.PHONY: rebuild
rebuild:
	@test "$(CONFIRM_GRAPH_REBUILD)" = "PREPARE_DURABLE_GRAPH_REBUILD" || \
		(echo "CONFIRM_GRAPH_REBUILD=PREPARE_DURABLE_GRAPH_REBUILD is required" >&2; exit 2)
	@test "$(CONFIRM_GRAPH_SYNC)" = "RUN_DURABLE_GRAPH_SYNC" || \
		(echo "CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC is required" >&2; exit 2)
	@test "$(CONFIRM_GRAPH_REBUILD_FINALIZE)" = "FINALIZE_DURABLE_GRAPH_REBUILD" || \
		(echo "CONFIRM_GRAPH_REBUILD_FINALIZE=FINALIZE_DURABLE_GRAPH_REBUILD is required" >&2; exit 2)
	@$(MAKE) graph-rebuild-prepare \
		BACKUP_REFERENCE="$(BACKUP_REFERENCE)" \
		CONFIRM_GRAPH_REBUILD="$(CONFIRM_GRAPH_REBUILD)"
	@$(MAKE) sync-to-graphiti \
		CONFIRM_GRAPH_SYNC="$(CONFIRM_GRAPH_SYNC)" \
		MAX_EPISODES="$(MAX_EPISODES)" $(if $(VERBOSE),VERBOSE=1,)
	@$(MAKE) graph-rebuild-finalize \
		CONFIRM_GRAPH_REBUILD_FINALIZE="$(CONFIRM_GRAPH_REBUILD_FINALIZE)"
	@echo "Durable graph rebuild complete."

# =============================================================================
# RESET & CLEANUP OPERATIONS
# =============================================================================

.PHONY: clear-all
clear-all:
	@echo "🗑️  Clearing ALL processed data (PostgreSQL episodes + Neo4j)..."
	@docker compose exec api python src/scripts/clear_all_data.py

.PHONY: clear-graph
clear-graph:
	@echo "Direct graph clearing is retired; use graph-rebuild-prepare." >&2
	@exit 2

.PHONY: clear-graph-force
clear-graph-force:
	@echo "Untracked graph clearing is retired; use graph-rebuild-prepare." >&2
	@exit 2

.PHONY: reset-all
reset-all:
	@echo "The legacy combined reset is retired; use capability-specific safe workflows." >&2
	@exit 2

.PHONY: reset-sync
reset-sync:
	@echo "Direct sync-flag reset is retired; use graph-rebuild-prepare." >&2
	@exit 2

.PHONY: reset-embeddings clear-embeddings
reset-embeddings: clear-embeddings

clear-embeddings:
	@echo "🔄 Clearing all embeddings (use before switching embedding providers)..."
	@docker compose exec -T postgres psql -U luminari -d luminari_sage -c "UPDATE episodes SET embedding = NULL;"
	@echo "✅ All embeddings cleared"

.PHONY: reset-documents
reset-documents:
	@echo "🔄 Resetting document processing status..."
	@docker compose exec -T api python src/scripts/reset_processing.py --target documents --yes

# =============================================================================
# STATUS & MONITORING
# =============================================================================

.PHONY: status
status:
	@echo "📊 Luminari Sage - Hybrid Graph RAG Status"
	@echo "==========================================="
	@echo ""
	@echo "🐳 Docker Services:"
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "❌ Docker services not running"
	@echo ""
	@echo "🔍 API Health:"
	@curl -s http://localhost:8003/ping | jq . 2>/dev/null || echo "❌ API not responding"
	@echo ""
	@echo "📊 Processing Status:"
	@docker compose exec -T api python src/scripts/reset_processing.py --status 2>/dev/null || echo "❌ Could not get processing status"
	@echo ""
	@echo "🕸️  Neo4j Graph Status:"
	@docker compose exec -T api python src/scripts/clear_graph.py --status 2>/dev/null || echo "❌ Could not get graph status"

.PHONY: status-episodes
status-episodes:
	@echo "📊 Episode Creation Status:"
	@docker compose exec -T api python src/scripts/create_episodes_from_documents.py --status

.PHONY: status-embeddings embedding-status
status-embeddings: embedding-status

embedding-status:
	@echo "📊 Embedding Status:"
	@docker compose exec -T postgres psql -U luminari -d luminari_sage -c \
		"SELECT \
			COUNT(*) as total_episodes, \
			COUNT(embedding) as with_embeddings, \
			COUNT(*) - COUNT(embedding) as missing_embeddings, \
			CASE WHEN COUNT(embedding) > 0 THEN array_length(embedding::float[], 1) ELSE NULL END as dimension \
		FROM episodes;"

.PHONY: status-processing
status-processing:
	@echo "📊 Processing Status:"
	@docker compose exec -T api python src/scripts/reset_processing.py --status

.PHONY: graphiti-status status-graphiti
graphiti-status: status-graphiti

status-graphiti:
	@echo "📊 Graphiti Status:"
	@docker compose exec -T postgres psql -U luminari -d luminari_sage -c \
		"SELECT COUNT(*) FILTER (WHERE graphiti_synced) AS processed, COUNT(*) AS total FROM episodes;"
	@echo ""
	@docker compose exec -T api python src/scripts/clear_graph.py --status

.PHONY: graph-audit
graph-audit:
	@docker compose exec -T api python src/scripts/graph_audit.py

.PHONY: graph-audit-json
graph-audit-json:
	@docker compose exec -T api python src/scripts/graph_audit.py --json

.PHONY: graph-sync-status
graph-sync-status:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py status

.PHONY: graph-sync-run-summary
graph-sync-run-summary:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		run-summary \
		--window-seconds "$(or $(PROGRESS_WINDOW_SECONDS),300)" $(if $(strip $(RUN_ID)),--run-id "$(RUN_ID)",)

.PHONY: graph-sync-run-summary-json
graph-sync-run-summary-json:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		--json run-summary \
		--window-seconds "$(or $(PROGRESS_WINDOW_SECONDS),300)" $(if $(strip $(RUN_ID)),--run-id "$(RUN_ID)",)

.PHONY: graph-quality-report
graph-quality-report:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		quality-report $(if $(strip $(RUN_ID)),--run-id "$(RUN_ID)",)

.PHONY: graph-quality-report-json
graph-quality-report-json:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		--json quality-report $(if $(strip $(RUN_ID)),--run-id "$(RUN_ID)",)

.PHONY: graph-sync-list
graph-sync-list:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		list --state leased --state retry_wait --state quarantined

.PHONY: graph-sync-recover-expired
graph-sync-recover-expired:
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py recover-expired

.PHONY: graph-sync-retry-waiting
graph-sync-retry-waiting:
	@test -n "$(EPISODE_IDS)" || \
		(echo "EPISODE_IDS is required" >&2; exit 2)
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		retry-waiting $(EPISODE_IDS)

.PHONY: graph-sync-retry-quarantined
graph-sync-retry-quarantined:
	@test "$(CONFIRM)" = "1" || \
		(echo "CONFIRM=1 is required for quarantined retries" >&2; exit 2)
	@test -n "$(EPISODE_IDS)" || \
		(echo "EPISODE_IDS is required" >&2; exit 2)
	@docker compose run --rm --no-deps api python src/scripts/graph_sync.py \
		retry-quarantined --confirm $(EPISODE_IDS)

.PHONY: graph-rebuild-status
graph-rebuild-status:
	@docker compose run --rm --no-deps api \
		python src/scripts/graph_rebuild.py status

.PHONY: graph-rebuild-plan
graph-rebuild-plan:
	@docker compose run --rm --no-deps api \
		python src/scripts/graph_rebuild.py plan

.PHONY: graph-rebuild-prepare
graph-rebuild-prepare:
	@test -n "$(BACKUP_REFERENCE)" || \
		(echo "BACKUP_REFERENCE below backups/ is required" >&2; exit 2)
	@test "$(CONFIRM_GRAPH_REBUILD)" = "PREPARE_DURABLE_GRAPH_REBUILD" || \
		(echo "CONFIRM_GRAPH_REBUILD=PREPARE_DURABLE_GRAPH_REBUILD is required" >&2; exit 2)
	@docker compose run --rm --no-deps --user 0:0 \
		-v "$(CURDIR)/backups:/app/backups:ro" api \
		python src/scripts/graph_rebuild.py prepare \
		--backup-reference "$(BACKUP_REFERENCE)" \
		--confirm "$(CONFIRM_GRAPH_REBUILD)"

.PHONY: graph-rebuild-finalize
graph-rebuild-finalize:
	@test "$(CONFIRM_GRAPH_REBUILD_FINALIZE)" = "FINALIZE_DURABLE_GRAPH_REBUILD" || \
		(echo "CONFIRM_GRAPH_REBUILD_FINALIZE=FINALIZE_DURABLE_GRAPH_REBUILD is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/graph_rebuild.py finalize \
		--confirm "$(CONFIRM_GRAPH_REBUILD_FINALIZE)"

.PHONY: backup-provider-upgrade
backup-provider-upgrade:
	@test -n "$(BACKUP_REFERENCE)" || \
		(echo "BACKUP_REFERENCE below backups/ is required" >&2; exit 2)
	@CONFIRM_NEO4J_OFFLINE_BACKUP=1 \
		bash src/scripts/backup_provider_upgrade.sh "$(BACKUP_REFERENCE)"

.PHONY: verify-provider-upgrade-backup
verify-provider-upgrade-backup:
	@test -n "$(BACKUP_REFERENCE)" || \
		(echo "BACKUP_REFERENCE below backups/ is required" >&2; exit 2)
	@python3 src/scripts/verify_provider_upgrade_backup.py "$(BACKUP_REFERENCE)"

.PHONY: db-migrate-status
db-migrate-status:
	@docker compose run --rm --no-deps api python src/scripts/migrate_database.py

.PHONY: db-migrate-check
db-migrate-check:
	@docker compose run --rm --no-deps api python src/scripts/migrate_database.py --check

.PHONY: db-migrate
db-migrate:
	@test -n "$(BACKUP_REFERENCE)" || \
		(echo "BACKUP_REFERENCE is required and must identify verified backups" >&2; exit 2)
	@test -z "$(shell git status --porcelain)" || \
		(echo "Commit the exact migration and application revision before applying" >&2; exit 2)
	@python3 src/scripts/verify_provider_upgrade_backup.py "$(BACKUP_REFERENCE)"
	@docker compose run --rm --no-deps api python src/scripts/migrate_database.py \
		--apply \
		--backup-reference "$(BACKUP_REFERENCE)" \
		--application-revision "$(shell git rev-parse --verify HEAD)"

.PHONY: embedding-preflight
embedding-preflight:
	@docker compose run --rm --no-deps api \
		python src/scripts/embedding_preflight.py status --scope all

.PHONY: embedding-preflight-json
embedding-preflight-json:
	@docker compose run --rm --no-deps api \
		python src/scripts/embedding_preflight.py --json status --scope all

.PHONY: embedding-profile-activate
embedding-profile-activate:
	@test -n "$(CONFIRM_EMBEDDING_PROFILE)" || \
		(echo "CONFIRM_EMBEDDING_PROFILE is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/embedding_preflight.py activate \
		$(if $(filter 1 true yes,$(ADOPT_EXISTING)),--adopt-existing,) \
		--confirm "$(CONFIRM_EMBEDDING_PROFILE)"

.PHONY: embedding-shadow-status
embedding-shadow-status:
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py status

.PHONY: embedding-shadow-status-json
embedding-shadow-status-json:
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py --json status

.PHONY: embedding-shadow-register
embedding-shadow-register:
	@test "$(CONFIRM_SHADOW_EMBEDDING)" = "REGISTER_SHADOW_EMBEDDING_SPACE" || \
		(echo "CONFIRM_SHADOW_EMBEDDING=REGISTER_SHADOW_EMBEDDING_SPACE is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py register \
		--provider "$(or $(SHADOW_EMBEDDING_PROVIDER),openrouter)" \
		--confirm "$(CONFIRM_SHADOW_EMBEDDING)"

.PHONY: embedding-shadow-backfill
embedding-shadow-backfill:
	@test "$(CONFIRM_SHADOW_EMBEDDING)" = "RUN_SHADOW_EMBEDDING_BACKFILL" || \
		(echo "CONFIRM_SHADOW_EMBEDDING=RUN_SHADOW_EMBEDDING_BACKFILL is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py backfill \
		--provider "$(or $(SHADOW_EMBEDDING_PROVIDER),openrouter)" \
		--max-provider-requests "$(or $(SHADOW_EMBEDDING_MAX_REQUESTS),1)" \
		--confirm "$(CONFIRM_SHADOW_EMBEDDING)"

.PHONY: embedding-shadow-recover-run
embedding-shadow-recover-run:
	@test -n "$(SHADOW_EMBEDDING_RUN_ID)" || \
		(echo "SHADOW_EMBEDDING_RUN_ID is required" >&2; exit 2)
	@test "$(CONFIRM_SHADOW_EMBEDDING)" = "RECOVER_SHADOW_EMBEDDING_RUN" || \
		(echo "CONFIRM_SHADOW_EMBEDDING=RECOVER_SHADOW_EMBEDDING_RUN is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py recover-run \
		"$(SHADOW_EMBEDDING_RUN_ID)" \
		--confirm "$(CONFIRM_SHADOW_EMBEDDING)"

.PHONY: embedding-shadow-build-index
embedding-shadow-build-index:
	@test "$(CONFIRM_SHADOW_EMBEDDING)" = "BUILD_SHADOW_EMBEDDING_INDEX" || \
		(echo "CONFIRM_SHADOW_EMBEDDING=BUILD_SHADOW_EMBEDDING_INDEX is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/shadow_embeddings.py build-index \
		--provider "$(or $(SHADOW_EMBEDDING_PROVIDER),openrouter)" \
		--confirm "$(CONFIRM_SHADOW_EMBEDDING)"

.PHONY: retrieval-corpus-check
retrieval-corpus-check:
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py validate

.PHONY: retrieval-corpus-check-json
retrieval-corpus-check-json:
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py --json validate

.PHONY: benchmark-retrieval
benchmark-retrieval:
	@test "$(CONFIRM_RETRIEVAL_BENCHMARK)" = "RUN_RETRIEVAL_BENCHMARK" || \
		(echo "CONFIRM_RETRIEVAL_BENCHMARK=RUN_RETRIEVAL_BENCHMARK is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py run \
		--max-provider-requests "$(or $(RETRIEVAL_BENCHMARK_MAX_REQUESTS),1)" \
		--confirm "$(CONFIRM_RETRIEVAL_BENCHMARK)"

.PHONY: benchmark-retrieval-json
benchmark-retrieval-json:
	@test "$(CONFIRM_RETRIEVAL_BENCHMARK)" = "RUN_RETRIEVAL_BENCHMARK" || \
		(echo "CONFIRM_RETRIEVAL_BENCHMARK=RUN_RETRIEVAL_BENCHMARK is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py --json run \
		--max-provider-requests "$(or $(RETRIEVAL_BENCHMARK_MAX_REQUESTS),1)" \
		--confirm "$(CONFIRM_RETRIEVAL_BENCHMARK)"

.PHONY: benchmark-shadow-retrieval
benchmark-shadow-retrieval:
	@test "$(CONFIRM_RETRIEVAL_BENCHMARK)" = "RUN_RETRIEVAL_BENCHMARK" || \
		(echo "CONFIRM_RETRIEVAL_BENCHMARK=RUN_RETRIEVAL_BENCHMARK is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py run \
		--space shadow \
		--provider "$(or $(SHADOW_EMBEDDING_PROVIDER),openrouter)" \
		--max-provider-requests "$(or $(RETRIEVAL_BENCHMARK_MAX_REQUESTS),1)" \
		--confirm "$(CONFIRM_RETRIEVAL_BENCHMARK)"

.PHONY: benchmark-shadow-retrieval-json
benchmark-shadow-retrieval-json:
	@test "$(CONFIRM_RETRIEVAL_BENCHMARK)" = "RUN_RETRIEVAL_BENCHMARK" || \
		(echo "CONFIRM_RETRIEVAL_BENCHMARK=RUN_RETRIEVAL_BENCHMARK is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_retrieval.py --json run \
		--space shadow \
		--provider "$(or $(SHADOW_EMBEDDING_PROVIDER),openrouter)" \
		--max-provider-requests "$(or $(RETRIEVAL_BENCHMARK_MAX_REQUESTS),1)" \
		--confirm "$(CONFIRM_RETRIEVAL_BENCHMARK)"

.PHONY: provider-config-check
provider-config-check:
	@docker compose run --rm --no-deps api \
		python src/scripts/provider_ops.py check

.PHONY: provider-config-check-json
provider-config-check-json:
	@docker compose run --rm --no-deps api \
		python src/scripts/provider_ops.py --json check

.PHONY: provider-text-probe
provider-text-probe:
	@test "$(CONFIRM_PROVIDER_PROBE)" = "RUN_PROVIDER_PROBE" || \
		(echo "CONFIRM_PROVIDER_PROBE=RUN_PROVIDER_PROBE is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/provider_ops.py text-probe \
		--task "$(or $(PROVIDER_TASK),chat)" \
		--confirm "$(CONFIRM_PROVIDER_PROBE)"

.PHONY: provider-embedding-probe
provider-embedding-probe:
	@test "$(CONFIRM_PROVIDER_PROBE)" = "RUN_PROVIDER_PROBE" || \
		(echo "CONFIRM_PROVIDER_PROBE=RUN_PROVIDER_PROBE is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/provider_ops.py embedding-probe \
		--scope "$(or $(PROVIDER_EMBEDDING_SCOPE),application)" \
		--confirm "$(CONFIRM_PROVIDER_PROBE)"

.PHONY: benchmark-graphiti
benchmark-graphiti:
	@test "$(CONFIRM_GRAPHITI_BENCHMARK)" = "RUN_GRAPHITI_BENCHMARK" || \
		(echo "CONFIRM_GRAPHITI_BENCHMARK=RUN_GRAPHITI_BENCHMARK is required" >&2; exit 2)
	@docker compose run --rm --no-deps api \
		python src/scripts/benchmark_graphiti.py \
		--candidate "$(or $(GRAPHITI_BENCHMARK_CANDIDATE),primary)" \
		--concurrency "$(or $(GRAPHITI_BENCHMARK_CONCURRENCY),1)" \
		$(GRAPHITI_BENCHMARK_MAX_CALLS_FLAG) \
		--confirm "$(CONFIRM_GRAPHITI_BENCHMARK)"

.PHONY: benchmark-graphiti-openai
benchmark-graphiti-openai:
	@echo "benchmark-graphiti-openai is disabled; select GRAPHITI_TEXT_PROVIDER and use benchmark-graphiti" >&2
	@exit 2

# =============================================================================
# SYSTEM OPERATIONS
# =============================================================================

.PHONY: dev
dev:
	@echo "Starting the capability-selected local development stack..."
	@$(PROVIDER_COMPOSE) up -d --build --remove-orphans

.PHONY: provider-stack-plan
provider-stack-plan:
	@$(PROVIDER_COMPOSE) plan

.PHONY: down
down:
	@echo "Stopping the local development stack (data volumes are preserved)..."
	@docker compose down

.PHONY: logs
logs:
	@echo "API container logs..."
	@docker compose logs -f api

.PHONY: logs-tail
logs-tail:
	@echo "API container logs (last 50 lines)..."
	@docker compose logs --tail=50 api

.PHONY: restart
restart:
	@echo "Restarting selected services..."
	@$(PROVIDER_COMPOSE) up -d --force-recreate --remove-orphans api ui

.PHONY: shell
shell:
	@echo "Opening shell in API container..."
	@docker compose exec api bash

# =============================================================================
# TESTING & VALIDATION
# =============================================================================

.PHONY: test
test:
	@echo "🧪 Running fast tests in the development container..."
	@docker compose exec -T api python -m pytest \
		-m "not integration and not data_dependent and not e2e and not quality and not performance and not stress and not slow"

.PHONY: test-all
test-all:
	@echo "🧪 Running all tests, including live and slow suites..."
	@docker compose exec -T api python -m pytest

.PHONY: test-chunking
test-chunking:
	@echo "🧪 Testing semantic chunking..."
	@docker compose exec -T api python src/scripts/semantic_chunker.py

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
	@echo "🧹 Clearing Sage application log files only (Docker volumes are preserved)..."
	@docker compose exec -T api sh -c \
		'find /app/logs -maxdepth 1 -type f -name "*.log" -exec truncate -s 0 {} +'

.PHONY: watch-logs
watch-logs:
	@echo "👀 Watching logs (press Ctrl+C to stop)..."
	@docker compose logs -f

# Show all available targets
.PHONY: targets
targets:
	@echo "📋 Available Make Targets:"
	@grep '^.PHONY:' Makefile | sed 's/.PHONY: /  /' | sort | uniq
