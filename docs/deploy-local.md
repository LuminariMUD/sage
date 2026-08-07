# Local development deployment

This is the durable setup and recovery guide for running the complete Sage
stack on a developer workstation. It intentionally contains no secret values.
Keep the real `.env` mode `0600` and never commit it.

## Current checkpoint

- Date: 2026-08-07
- Work branch: `main`
- Repository: <https://github.com/LuminariMUD/sage>
- The legacy all-Ollama runtime remains healthy: PostgreSQL, Neo4j, Ollama,
  API/MCP, and the static chat UI are running. The newly configured provider
  profile has not been activated by a restart.
- PostgreSQL contains 14 preserved lore documents, zero episodes, zero durable
  graph-sync jobs, and zero runs. Neo4j contains zero nodes and zero
  relationships after deletion of the operator-rejected corpus.
- The ignored local target profile selects OpenRouter for application and
  Graphiti text and embeddings. `make provider-stack-plan` resolves that target
  to `ollama-not-required`, so the next authorized `make dev` will omit both Ollama
  services. Ingestion remains frozen.
- The development image builds successfully. The current deterministic-suite
  result is recorded in `docs/CHANGELOG.md` and the two active project plans.
- The fresh-container offline fast gate passes 339 tests with 8 skips and 115
  intentional deselections. Host-only Compose renders pass for cloud-only and
  all-local service sets.
- An authenticated desktop/mobile browser check now passes through the real
  LangChain/Ollama chat path: message creation and the SSE stream both return
  `200`, an answer renders, and there are no console/page errors, leaked API
  keys, or horizontal overflow.

Resume work from this checkpoint by running:

```bash
git switch main
git pull --ff-only origin main
docker compose ps --all
make status
```

## Local architecture

| Role                  | Local component                             |
| --------------------- | ------------------------------------------- |
| REST API              | FastAPI + Uvicorn on `127.0.0.1:8003`       |
| MCP server            | FastAPI/Uvicorn process on `127.0.0.1:8004` |
| Developer UI          | Static chat UI on `127.0.0.1:8080`          |
| Chat, creative, tools | Ollama `qwen2.5:7b`                         |
| Graphiti extraction   | Ollama `qwen2.5:3b`                         |
| Embeddings            | Ollama `nomic-embed-text` (768 dimensions)  |
| Vector/document data  | PostgreSQL 18 + pgvector                    |
| Knowledge graph       | Neo4j 2026.06 Community + Graphiti          |

The local profile does not require a cloud LLM. The 3B extraction model was
selected after a live benchmark on the workstation's 8 GB GPU: it produced
coherent entities and facts in roughly 16 seconds after model load, while the
7B model generally took around a minute per episode. Chat and creative work
remain on 7B for better response quality.

Ollama is configured with a 12,288-token context, two parallel slots, and at
most two resident models. Graphiti responses are capped at 4,096 output tokens
and 25 entities/relationships per episode to prevent runaway local generation.

## Prerequisites

- Docker Engine with Compose v2.20 or newer (`required: false` support)
- NVIDIA driver and NVIDIA Container Toolkit for GPU-backed Ollama
- Git and Make
- Free host ports, or alternate values in `.env`

The active workstation uses these non-default host ports because PostgreSQL and
Ollama were already bound on their standard ports:

```dotenv
POSTGRES_PORT=5433
OLLAMA_HOST_PORT=11435
```

Internal container ports remain unchanged.

## First-time setup

```bash
git clone git@github.com:LuminariMUD/sage.git
cd sage
cp .env.example .env
chmod 600 .env
```

Generate independent values for `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`,
`SAGE_API_KEY`, `SAGE_MCP_KEY`, and `SAGE_MCP_BACKEND_KEY`:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep `TEXT_PROVIDER=ollama`, `EMBEDDING_PROVIDER=ollama`, and the two Graphiti
provider overrides empty (inherit) or explicitly `ollama` for the fully local
profile. No cloud-provider key is required for that path. When OpenRouter is
selected, prefer exactly one of `OPENROUTER_API_KEY` or
`OPENROUTER_API_KEY_FILE`; `OPENROUTER_KEY` is a deprecated compatibility alias
and cannot be combined with either canonical input.

The public `.env.example` is contract-tested against every field accepted by
the provider resolver. Keep empty selector values and explanatory comments on
separate lines: dotenv parsers can treat a comment after an empty assignment as
the assignment's value.

Start the complete development stack:

```bash
make dev
```

`make dev` resolves every application and Graphiti capability before starting
Compose. All-cloud profiles omit both `ollama` and `ollama-init`; mixed and local
profiles start Ollama and pull only the selected models through the one-shot init
service. API/MCP and UI start after their selected dependencies are ready. Model
pulls are idempotent on later starts. Use `make provider-stack-plan` for a
credential-free preview.

## Verify the running stack

```bash
docker compose ps --all
make status
curl --fail http://127.0.0.1:8003/ping
curl --fail http://127.0.0.1:8003/api/v1/health
curl --fail http://127.0.0.1:8004/
curl --fail http://127.0.0.1:8080/chat-ui.html >/dev/null
```

Useful browser endpoints:

- Chat UI: <http://localhost:8080/chat-ui.html>
- OpenAPI docs: <http://localhost:8003/docs>
- Neo4j Browser: <http://localhost:7474>

Protected API calls should use `scripts/curl_with_sage_key.sh`, which reads the
key without printing it or putting it directly in shell history:

```bash
./scripts/curl_with_sage_key.sh \
  'http://127.0.0.1:8003/api/v1/lore/search?query=crystal+dwarves&limit=5'
```

To verify chat manually, open the UI, open Settings, keep the local endpoint at
`http://localhost:8003`, paste `SAGE_API_KEY` from the uncommitted `.env`, and
select the LangChain engine. The password field is intentionally cleared on
page exit and the key is never written to browser storage.

The 2026-08-06 browser checkpoint used desktop `1440x900` and mobile `390x844`
viewports. The Browser plugin and repository-owned JavaScript Playwright
workflow were unavailable, so the check used installed Python Playwright with
the cached Chromium binary. That mismatched driver/browser pair labels a
manually consumed streaming fetch `net::ERR_ABORTED` in its protocol events
even after the complete body and final SSE event arrive. A control that consumes
the same response as text reports `requestfinished`; the UI has no error, both
HTTP responses are `200`, and PostgreSQL records the stream `completed`.

## Development workflow

Application source, tests, and static UI files are mounted read-only into the
API development container. Both API and MCP Uvicorn processes watch `/app/src`;
editing Python source on the host triggers an automatic reload. The UI mount
also lets the fast suite enforce browser-source streaming contracts.

```bash
make logs-tail
make logs
make shell
make test
```

`make test` is the fast deterministic suite. `make test-all` additionally runs
live integration, data-dependent, quality, performance, stress, and slow tests;
it is intentionally not the normal edit-loop command.

Stop containers while preserving every named data/model volume:

```bash
make down
```

## Lore data pipeline

The pipeline is resumable. Normal commands do not clear existing volumes:

```bash
make load-canon
make create-episodes
make generate-embeddings
# Only after an operator explicitly authorizes ingestion:
make sync-to-graphiti CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
```

Or run/resume the complete sequence:

```bash
make semantic-pipeline CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
make resume CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
```

Monitor progress without changing data:

```bash
make embedding-status
make graphiti-status
make graph-sync-status
make graph-sync-run-summary
make graph-sync-run-summary-json
```

The run-summary commands use one repeatable-read, read-only PostgreSQL
transaction. They report current-profile completion, job eligibility, expired
leases, run outcomes, failure-class counts, reserved/completed provider calls,
telemetry coverage, rolling verified episodes per minute, and an explicitly
approximate ETA. Use `RUN_ID=<uuid>` for a historical run and
`PROGRESS_WINDOW_SECONDS=<60..86400>` to change the default five-minute rolling
window. A missing ETA always includes a stable reason such as `warming_up`,
`stopped`, `paused_systemic`, `blocked_quarantine`, or `insufficient_progress`.

Graph synchronization is inert unless both `--run` and the exact confirmation
token are supplied. The Make target enforces the same gate. Do not run it while
an operator freeze is active. The worker claims authoritative durable jobs one
at a time, records an immutable attempt and every provider request, writes the
PostgreSQL episode UUID as Graphiti's native UUID, and marks success only after
independently proving one Neo4j record has the expected stable ID, source
description, source fingerprint, sync profile, and embedding profile.

Only after that exact gate passes, the worker constructs the complete ordered
Graphiti text route. The OpenAI-compatible SDK retry count and graphiti-core's
four-attempt retry wrapper are both disabled at this boundary. Same-candidate
generation retries and candidate fallback occur only for their configured failure
classes. Every actual request is reserved before network I/O and is completed in
the durable ledger only after JSON parsing and independent schema validation;
malformed, schema-invalid, and output-limit records contain stable classifications
rather than model output. A successful fallback is persisted and reported as a
degraded success.

`GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS` is one operation-wide ceiling across all
Graphiti-internal extraction, deduplication, attribute, summary, and enrichment
requests for an episode, including concurrent tasks. The default of `3` is a
fail-closed safety value, not a measured production recommendation, and may stop a
nontrivial episode before graph persistence. Keep it aligned with
`GRAPH_SYNC_MAX_PROVIDER_CALLS`, establish a larger value only through the bounded
non-persistent benchmark, and use `MAX_EPISODES` for the independent job-claim
limit. Exhaustion enters the durable retry/quarantine lifecycle; it never creates
an unrecorded provider request. Merely configuring a provider credential does not
authorize a benchmark or worker run.

Legacy bulk mode is disabled because it bypasses leases, provider-call budgets,
and post-write durable verification. Use `MAX_EPISODES` for a bounded authorized
run:

```bash
make sync-to-graphiti \
  CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC \
  MAX_EPISODES=5
```

## Controlled graph rebuild

Migration `0006_graph_rebuild_operations` must be applied through the normal
verified-backup migration gate before these commands are available. The read-only
plan reports the configured target profiles, current cross-store audit, graph
counts, leases, active runs, and any blocker:

```bash
make graph-rebuild-plan
make graph-rebuild-status
```

Create a new combined backup immediately before preparation. Creating the rebuild
operation accepts only a backup from the prior 24 hours whose scratch-restored
episode count matches the clean pre-clear audit. An interrupted operation can later
resume with that same re-verified backup even after the initial freshness window:

```bash
make backup-provider-upgrade \
  BACKUP_REFERENCE=backups/provider-upgrade-<timestamp>

make graph-rebuild-prepare \
  BACKUP_REFERENCE=backups/provider-upgrade-<timestamp> \
  CONFIRM_GRAPH_REBUILD=PREPARE_DURABLE_GRAPH_REBUILD
```

Preparation starts a new retry generation for every job while preserving total
attempt counts, attempt/result/provider ledgers, and source fingerprints. It records
the target sync and embedding fingerprints before clearing all Neo4j data. A crash
after that PostgreSQL commit leaves `jobs_requeued`; rerun the same command with the
same backup and profile to finish the idempotent clear. No provider client is
constructed and no graph job is claimed during preparation. A session-scoped lock
serializes the complete cross-store phase; a concurrent prepare fails before it can
clear anything, and a crashed command releases the lock with its database session.

Run only the durable worker, then finalize separately:

```bash
make sync-to-graphiti CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC

make graph-rebuild-finalize \
  CONFIRM_GRAPH_REBUILD_FINALIZE=FINALIZE_DURABLE_GRAPH_REBUILD
```

Every worker run opened during the rebuild is linked to its operation and uses the
normal lease, immutable attempt, provider-request, verification, and retry/quarantine
contracts. Finalization refuses unless all target-profile jobs are synchronized and
the exact sync/embedding-profile audit is clean. Only then is the profile pair
recorded as active. `make rebuild` composes all three steps but checks all three
confirmation tokens before preparation begins.

## Safety and recovery

- `make down` preserves data.
- `make clean-logs` truncates only Sage application log files; it never prunes
  Docker volumes.
- Direct `make clear-graph`, `make clear-graph-force`, `make reset-sync`, and
  `make reset-all` paths are retired and refuse execution. Use the controlled
  rebuild workflow for graph state and capability-specific tools for vectors or
  documents. `make clear-all` remains a separate explicit corpus-deletion tool.
- Re-running `make dev`, model setup, document loading, embedding generation,
  or graph sync is designed to resume/idempotently reuse completed work.

If a command is interrupted, first inspect rather than reset:

```bash
docker compose ps --all
make status
docker compose logs --tail=100 api ollama neo4j postgres
git status --short --branch
```

## Issues fixed during local bring-up

- PostgreSQL health checks now target the configured database instead of
  repeatedly probing a nonexistent database named after the user.
- API and MCP development reload use the bind-mounted source tree.
- Local development dependencies are installed only in the Compose API image;
  the production image remains lean.
- The UI is part of Compose and waits for a healthy API.
- Ollama uses the current `OLLAMA_CONTEXT_LENGTH` server setting rather than the
  ignored legacy `OLLAMA_NUM_CTX` environment setting.
- DeepSeek R1 was removed from the active path because it cannot satisfy the
  tool-calling/structured Graphiti contracts used here.
- LangChain service selection now accepts Ollama directly instead of requiring
  an unrelated `OPENAI_API_KEY` to be present before enabling ReAct.
- Browser chat stream preflights now allow the UI's `Cache-Control` request
  header; previously message creation returned `200` but CORS blocked the SSE
  request before an answer could render.
- Terminal SSE events no longer return early from the UI reader. The response
  is drained to EOF and its reader lock is explicitly released after server
  completion.
- Graphiti no longer drops every Neo4j index and constraint when initialized.
- Graphiti edge prompts use the shared `Entity` base type, which substantially
  reduces prompt size for local inference.
- Graphiti output/entity/relation limits prevent repeated multi-thousand-token
  extraction responses.
- Bulk sync now calls graphiti-core's real bulk API and refuses to mark rows
  synced until cross-store stable IDs are verified.
- Incremental sync now independently verifies a unique Neo4j stable-ID/source
  link before marking PostgreSQL complete, and safely resumes an already-linked
  row without repeating extraction.
- The graph status command now closes PostgreSQL with the supported connection
  API and returns a failing process status when inspection itself fails.
- Make targets use the active Compose project and noninteractive execution where
  appropriate; log cleanup no longer runs a destructive Docker volume prune.

## Remaining work at this checkpoint

1. Keep ingestion and provider activation frozen until the operator separately
   authorizes the pending migrations, source reprocessing, vector evaluation, and
   graph rebuild.
2. Create a fresh verified backup before applying migrations `0004` through
   `0006`; do not reuse the backup of the deleted 611-episode corpus.
3. After authorization, rebuild the episode corpus, evaluate the shadow vector
   space, run the controlled graph rebuild, and require clean pre/post audits and a
   preserved-volume restart before cutover.
