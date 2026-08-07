# Local LLM and Graph Pipeline Improvements

| Field            | Value                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------- |
| Status           | Active implementation                                                                                     |
| Last updated     | 2026-08-07                                                                                                |
| Observed         | 2026-08-06 during the full local-development bootstrap                                                    |
| Scope            | Ollama, Graphiti, PostgreSQL-to-Neo4j synchronization, local observability, and browser chat verification |
| Umbrella program | [Ollama and OpenRouter Provider Upgrade Plan](./ollama_openrouter_provider_upgrade_plan.md)               |

## Relationship to the umbrella program

The provider upgrade plan is authoritative for shared architecture, terminology, sequencing, release invariants, migrations, and the definition of done. This document owns the observed local evidence and the detailed Ollama/Graphiti work needed to satisfy those requirements on the 8 GB GPU development stack.

| Concern                                                                                       | Source of truth                                        |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Provider interfaces, text routes, embedding profiles, migration order, cross-provider tests   | Umbrella program                                       |
| Durable graph-sync states, retry layers, audit semantics, hard release invariants             | Umbrella program; detailed locally here                |
| Qwen 3B/7B extraction measurements, GPU residency, worker concurrency, local browser behavior | This workstream                                        |
| Shared contract change                                                                        | Update both documents in the same documentation change |

This workstream must not introduce a local-only shortcut that weakens the provider-neutral contract. In particular, text extraction may use an explicit bounded model fallback, while embeddings must never switch model, revision, implementation, or dimension inside an active vector space.

## Implementation progress

### 2026-08-07 - L1 read-only graph audit checkpoint

- Added `src/scripts/graph_audit.py` and pure reconciliation logic in `src/graphiti/audit.py`.
- Added enforced read-only PostgreSQL sessions and Neo4j read access for audit clients.
- Added human and stable JSON output plus exit codes `0` for clean, `1` for drift, and `2` for incomplete execution.
- Added actionable checks for missing, unexpected, duplicate, and null stable IDs; source-description and available fingerprint/profile mismatches; non-synced jobs with Neo4j records; invalid or inconsistent durable jobs; and lifecycle counts.
- Added `make graph-audit` and `make graph-audit-json`.
- Verified the stopped local snapshot as clean: 611 PostgreSQL episodes, 305 synchronized, 306 pending under the legacy projection, 305 Neo4j Episodic nodes, 305 populated and distinct stable IDs, and zero drift findings.
- Verified 71 fast tests passed and 5 were skipped; the focused audit/security suite passed 18 tests.

The operator stopped the legacy Boolean-based worker at 305 of 611 episodes and requested that it not continue. Do not restart that worker without explicit operator direction. The next ingestion work should use the durable lifecycle after its migration and worker integration are complete.

The live graph currently has no source, sync-profile, or embedding-profile fingerprint metadata. The audit reports that coverage as zero without treating absent legacy metadata as a false drift result; the durable migration and profile work remain required.

### 2026-08-07 - L1 durable schema and migration activation checkpoint

- Added the immutable, checksum-tracked migration runner `src/scripts/migrate_database.py` with read-only status/check modes, per-migration transactions, a PostgreSQL advisory lock, application revision capture, and a required verified-backup reference for apply mode.
- Added `schemas/migrations/0001_graph_sync_lifecycle.sql` for run-level circuit state, authoritative jobs, immutable attempt identities, immutable attempt results, and immutable provider-call provenance.
- Added database constraints for lifecycle states, lease ownership/tokens/expiry, retry timing, verified source/profile identity, failure taxonomy, nonnegative usage/counts, one active run, and degraded fallback success.
- Added triggers that derive `episodes.graphiti_synced` from durable state, reject divergent direct writes, deterministically requeue a changed source revision, and prohibit update/delete operations on ledger tables.
- Added `make db-migrate-status`, `make db-migrate-check`, and backup-gated `make db-migrate` targets.
- Verified the migration in an isolated PostgreSQL schema, including seed reconciliation, Python/SQL fingerprint parity, direct-projection rejection, one-active-run enforcement, immutable-ledger rejection, durable success projection, and source-edit requeue behavior.
- Before activation, executed the complete migration against the current 611-row schema inside an explicit transaction; all DDL, the 611-row seed, and internal verification passed, then `ROLLBACK` removed every test artifact.

After the verified backup checkpoint, applied migration `0001_graph_sync_lifecycle` at application revision `a831a497c3499155bb450d80dc96093740e4fbe4`. The ledger is current with no pending migrations. The live seed contains 611 jobs: 305 `synced` and 306 `pending`; all desired and verified source/profile identities reconcile, and the Boolean compatibility projection has zero mismatches. No run, attempt, result, provider-call, lease, retry, or quarantine rows were introduced by migration.

The post-migration audit is clean and now uses `graph_sync_jobs` as its state source, with 611 job source/profile fingerprints, 305 verified source fingerprints, and 305 distinct Neo4j stable IDs. All services remain healthy. The legacy worker remains stopped and must not be restarted.

### 2026-08-07 - L1 durable runtime activation checkpoint

- Added `schemas/migrations/0002_graph_sync_runtime.sql` with per-generation attempt budgets, deterministic retry-policy capture, run heartbeats, a database-enforced provider-call ceiling, terminal-result count validation, and source-edit budget reset without deleting total attempt history.
- Added typed lifecycle contracts in `src/graphiti/sync_models.py` and transactional run, claim, lease, attempt, completion, recovery, quarantine, and operator transitions in `src/graphiti/sync_state.py`.
- Claims use `FOR UPDATE SKIP LOCKED`, database-time lease expiry, token fencing, immutable attempt identities, deterministic backoff, and captured job/provider limits. Systemic failure pauses the run and restores the current item's generation budget; queued jobs are not rewritten or charged.
- Success requires exact stable-ID, current-source, and sync-profile verification. Expired workers cannot choose a terminal outcome, source edits cannot produce stale success, and explicit quarantine retry opens a new budget generation while preserving the total attempt chain.
- Added the sanitized `src/scripts/graph_sync.py` operator CLI and Make targets for status, listing, expired-lease recovery, eligible retry, and confirmation-gated quarantine retry. Inspection uses read-only PostgreSQL sessions and does not expose episode text.
- Added isolated migration and repository tests for concurrent distinct claims, lease expiry, immutable-ledger upgrade backfill, hard provider-call limits, terminal ledger guards, stable verification, source changes, systemic pause/readiness, atomic operator batches, redaction, and preserved retry history.

Focused verification passes 27 unit tests and 9 isolated PostgreSQL integration tests; the full fast suite passes 103 tests with 6 skips and 108 intentionally deselected tests. The complete `0002` SQL was also executed against the live 611-job schema in one explicit transaction: all runtime DDL and invariant checks passed, after which an unconditional rollback proved that the runtime columns/functions were absent, the migration ledger still contained only `0001`, and all 611 jobs remained unchanged. The post-rehearsal graph audit remains clean at 611 jobs, 305 synchronized PostgreSQL rows, and 305 distinct Neo4j stable IDs; all services are healthy.

Migration `0002_graph_sync_runtime` was applied at `2026-08-06T22:57:38Z` with checksum `773cbdfdfbf01a87e2a39c1a46bca6a1f07b124e9951451db078c8c6890f3cec`, verified backup `backups/provider-upgrade-20260806T222200Z`, application revision `4429d33bf4164a9e4b6b477b5e5c634a790a560a`, and 8 ms execution time. Migration status/check modes are current with two applied migrations and no pending SQL.

Post-activation evidence remains unchanged: 611 jobs consist of 305 `synced` and 306 `pending`; there are zero runs, attempts, results, provider calls, leases, retry-wait rows, quarantines, nonzero runtime counters, or compatibility-projection mismatches. The operator status/list commands report the same state, required ledger guards are present, the graph audit remains clean, and every service is healthy. Applying the runtime migration did not start ingestion. The legacy worker remains stopped by operator request; do not run ingestion until the durable worker loop is integrated and separately authorized.

### 2026-08-07 - L1 provider-call reservation activation checkpoint

- Added migration `0003_graph_sync_provider_call_intents` so every allowed text-provider request is committed as an immutable intent before network I/O and completed through a separate append-only record afterward.
- Moved the database provider-call ceiling to the intent ledger, matched every completion to its reserved provider/model/candidate/prompt/schema identity, and required successful attempts to have no incomplete calls.
- Updated the repository with token-fenced reservation and completion methods. Attempt recovery counts reservations, so a process death after request dispatch leaves explainable provenance and can never be mistaken for an uncalled or successful attempt.
- Updated operator status and attempt chains to distinguish reserved calls from completed calls while continuing to omit prompts, episode text, and credentials.
- Added upgrade backfill coverage for completed calls created between migrations `0002` and `0003`, direct-database guard tests, and an interrupted-call integration test that recovers to `retry_wait` with one visible incomplete reservation.

Focused verification passes 27 unit tests and 10 isolated PostgreSQL integration tests; the full fast suite passes 103 tests with 6 skips and 109 intentionally deselected tests. A live-schema rehearsal created the intent table, its referential constraint, request-limit and completion triggers, and invariant checks inside one explicit transaction, then rolled back unconditionally. Post-rollback proof shows no intent table/function, two unchanged migration-ledger rows, and all 611 jobs intact.

Migration `0003_graph_sync_provider_call_intents` was applied at `2026-08-06T23:11:09Z` with checksum `d784d783f49cf16bf1a3ee51f8eeb074bc93e12ffd8310c204438ade41829bc6`, verified backup `backups/provider-upgrade-20260806T222200Z`, application revision `03b39f85eca202a9f314244e00b078e0bbd96a53`, and 6 ms execution time. Migration status/check modes are current with three applied migrations and no pending SQL.

Activation produced zero intents, completions, attempts, runs, leases, or projection mismatches. All required intent append-only, request-limit, and completion-matching triggers are present; operator status reports zero reserved and completed calls; the graph audit remains clean at 305 synchronized records and 305 distinct stable IDs; and every service is healthy. No provider request or ingestion was started, and the legacy worker remains stopped.

### 2026-08-07 - L1 durable worker and crash-recovery checkpoint

- Replaced the Boolean-driven worker with an explicitly confirmed durable entrypoint. Without `--run --confirm RUN_DURABLE_GRAPH_SYNC`, it is inert; the old bulk paths are rejected before connecting to either database.
- Added a deterministic sync profile covering the application/Graphiti implementation, prompt and schema versions, entity/edge contracts, normalization behavior, route candidate, embedding profile, and extraction bounds. Fingerprints contain no endpoints, credentials, or episode content.
- Moved provider accounting to the actual `chat.completions.create` boundary. Every upstream request is reserved first and completed separately, while underlying OpenAI-compatible transport retries are disabled. Graphiti-level retry attempts therefore remain visible and cannot exceed the database-enforced request budget.
- Added stable native-UUID Graphiti writes plus independent content, stable-ID, source-description, source-fingerprint, sync-profile, and embedding-profile verification. A compatible legacy node is adopted only when it is unique, its content matches, and no existing identity/profile metadata would be overwritten.
- Added one-at-a-time worker orchestration with graph/provider readiness, a read-only target-profile preflight before any run mutation, expired-lease recovery, run/lease heartbeats, systemic circuit pause, classified terminal outcomes, graceful cancellation, and resource cleanup.
- Added fault injection before the graph write, after the write, before verification, and after verification but before PostgreSQL success. Every case converges without a duplicate stable ID or false PostgreSQL success; recovery after a graph write reuses the native UUID without another provider path.
- Hardened the isolated PostgreSQL fixture so missing migrations, escaped `search_path`, missing isolated tables, or unexpected row counts fail before repository code can execute.

Verification passes 127 fast tests with 6 skips and 109 deselected tests, plus all 8 isolated PostgreSQL lifecycle tests in a fresh container. A read-only live query proved the new candidate inspection against one stopped legacy record; it found one stable-ID/source-description/content match and correctly reported zero legacy source/sync/embedding metadata coverage. Neo4j accepted the write query under `EXPLAIN`, `graph-audit` remains clean at 611 jobs and 305 distinct stable IDs, migrations remain current, and all services are healthy.

The first isolated integration invocation ran in the older API container, whose mount set predates `/app/schemas`. After creating an isolated `episodes` table, that fixture fell through to the public durable tables and opened one empty run. It claimed no jobs and created no attempts, provider requests, or results. The run was immediately stopped and retained as zero-attempt operational history. Mandatory migration/table/schema/count guards now prevent recurrence, and the passing rerun used a fresh one-off container.

The operator's stop request remains authoritative. No live worker or ingestion was started for this checkpoint, and future activation still requires separate explicit authorization plus a deliberate target-profile transition for pending jobs.

### 2026-08-07 - L1 backup and restore gate tooling checkpoint

- Added a combined provider-upgrade backup command that creates a PostgreSQL custom-format dump and offline Neo4j Community dumps for both `neo4j` and `system`.
- PostgreSQL verification performs a real scratch-database restore and records restored episode, synchronized-episode, and public-table counts.
- Neo4j verification inspects and consistency-checks both dump archives before restarting the exact service container and waiting for health.
- Added a strict completion-marker verifier and made live migration repeat that verifier before applying any SQL.
- Added a recovery runbook with explicit PostgreSQL and Neo4j restore commands and post-restore audit requirements.
- Verified 5 focused tests plus Bash syntax, ShellCheck, Compose rendering, Make dry-runs, and refusal guards.

The tooling was committed before the operational checkpoint. It does not start the legacy worker, which remains stopped by operator request.

The first operational attempt proved the failure path: Neo4j's login shell omitted `neo4j-admin` from `PATH`, so the dump command exited before producing an archive. Cleanup removed the exact temporary directory, restarted Neo4j to healthy, emitted no completion marker, and left the worker stopped. The script now uses the image's absolute `/var/lib/neo4j/bin/neo4j-admin` path before retrying under a new reference.

The replacement reference `backups/provider-upgrade-20260806T222200Z` is verified and was recorded by the applied migration. Its PostgreSQL scratch restore proved 611 episodes, 305 synchronized episodes, and 12 public tables. Both Neo4j archives passed metadata inspection and full consistency checks. The verifier confirmed all three SHA-256 digests and private permissions; cleanup left no scratch database or dump directory. All services returned healthy, the graph audit remained clean with 305 distinct stable IDs, and the worker remained stopped. Retain this backup through the rollout and rollback bake period.

### 2026-08-07 - Provider-neutral construction checkpoint, no activation

- Added validated capability-level text and embedding settings for Ollama and OpenRouter, including independent Graphiti overrides, bounded extraction-route declarations, model/profile fingerprints, selected-provider-only credential checks, and fail-closed OpenRouter routing/privacy defaults.
- Added the OpenRouter text and embedding adapters, modern batch Ollama embeddings, shared vector validation, provider-neutral LangChain/PydanticAI construction, optional legacy agent credentials, model-family prompt selection, and sanitized API startup/health identities.
- Replaced the Graphiti provider coupling with independent text and embedding clients. Offline construction covers all four Ollama/OpenRouter combinations without provider I/O.
- Added `OPENROUTER_API_KEY_FILE` container loading and a deprecated `OPENROUTER_KEY` compatibility alias. Local secret values remain ignored and were not logged or copied into tracked files.

The complete offline fast suite passes 185 tests with 6 skips and 109 deselected tests. Formatting, linting, compilation, ShellCheck, Compose validation, secret/environment contracts, and diff checks pass. No provider request, graph claim, or ingestion occurred.

This checkpoint does not approve an OpenRouter model, change the active Nomic vector space, execute the declared 3B-to-7B extraction fallback, or authorize a graph profile transition. The operator's stop instruction remains authoritative: the durable worker stays stopped until the operator explicitly requests activation.

### 2026-08-07 - Bounded provider route and deployment checkpoint, no activation

- Added classified, finite, bounded OpenRouter transport retries with `Retry-After` support and OpenAI SDK retries disabled at the direct adapter boundary. Stream creation may retry before the first chunk; a mid-stream failure is surfaced without replaying partial output.
- Added a higher-level text-route executor that distinguishes actual transport calls, same-candidate model retries, and ordered candidate fallback under one hard request count. Authentication and invalid configuration never fall back; successful fallback is recorded as degraded, and attempt provenance contains no prompt or exception detail.
- Added same-profile OpenRouter embedding retry without any cross-model fallback, plus deterministic response-index ordering and strict vector validation coverage.
- Added provider-selected production secret overrides and conditional CI/remote deployment transport. An all-Ollama deployment writes and mounts no OpenAI or OpenRouter key; mixed profiles mount only their selected cloud credentials. Deployment inputs are not inherited by Docker or health-check child processes.
- Accepted the ignored local `OPENROUTER_KEY` compatibility alias without reading it into tracked files, printing it, or making a live provider request.

The complete offline fast suite passes 203 tests with 6 skips and 109 deselected tests. The focused route/provider/deployment suite passes 60 tests, and production Compose renders all-Ollama, direct-OpenAI, OpenRouter-only, and mixed cloud profiles. Formatting, linting, Bash/ShellCheck/Actionlint, environment contracts, secret isolation, and diff checks pass.

This checkpoint does not wire the new route executor into Graphiti extraction. The existing durable Graphiti wrapper still owns provider reservations and disables opaque client retries; the proposed 3B-to-7B fallback remains declarative and unexecuted. No graph job was claimed, no provider call was made, and the operator's stop instruction remains authoritative.

### 2026-08-07 - Capability-derived Ollama model lifecycle checkpoint, no activation

- Added a shared POSIX-shell resolver that derives the exact local text and embedding models required by the application, Graphiti, and optional extraction fallback capability selectors.
- Replaced the fixed `ollama-init` pull list with validated, deduplicated profile resolution. All-cloud profiles skip model setup without requiring the Ollama CLI, while mixed profiles include only their selected Ollama capabilities.
- Updated the setup and warmup scripts to consume the same resolver output. Text warmup uses `ollama run`; embedding warmup uses `/api/embed` rather than a text-generation request.
- Kept provider keys and passwords out of the init service and passed raw empty capability overrides through Compose so application-level legacy precedence remains authoritative.
- Added ten offline tests for all-local, all-cloud, mixed, task-specific, invalid, deduplicated, fake-pull, and static lifecycle contracts.

The complete offline fast suite passes 213 tests with 6 skips and 109 deselected tests. Syntax, ShellCheck, Compose, formatting/linting, and a read-only Compose model-list check pass. The list check resolved the current local profile's three model names only; no model was pulled, warmed, or invoked.

This slice does not make the base API service's Ollama dependency conditional, so cloud-only startup still has follow-up work. No graph job was claimed, no provider call was made, and the operator's stop instruction remains authoritative.

## Why this project exists

The local stack now runs end to end, including PostgreSQL, Neo4j, Ollama, the API, the MCP server, and the browser UI. The full 611-episode graph import exposed several opportunities to make the system faster, easier to operate, and more reliable with small local models.

The current sync is safe and resumable: PostgreSQL is marked synchronized only after exactly one Neo4j episode with the expected stable ID is independently verified. The improvements below preserve that invariant while making failure handling durable, explainable, testable, and provider-neutral.

The intended processing model is idempotent at-least-once delivery; this workstream does not attempt a cross-database exactly-once transaction. PostgreSQL owns synchronization intent and attempt history; the stable episode UUID makes Neo4j writes repeatable; independent reconciliation proves convergence.

## Shared operating contract

- Use the durable states `pending`, `leased`, `retry_wait`, `quarantined`, and `synced`.
- Treat transport retry, same-candidate generation retry, text-candidate fallback, durable job retry, and embedding fallback as distinct policies.
- Cap total provider calls per leased attempt even when libraries contain internal retries.
- Pause new claims at run level for systemic failures without rewriting or charging queued episode jobs.
- Record every candidate/model attempt with a sanitized outcome and immutable route/prompt/schema fingerprint.
- Mark an episode `synced` only after stable-ID verification.
- Bind each claim and successful verification to a deterministic source-content fingerprint; requeue a source revision detected mid-flight.
- Report fallback success as degraded success.
- Run the read-only `graph-audit` after imports, preserved-volume restarts, cutovers, and rollbacks.
- Keep synchronization completeness separate from graph-quality acceptance.

## Findings and proposed work

### 1. Make structured extraction reliable across model sizes

**Observed:** The local `qwen2.5:3b` reasoning model periodically returns malformed JSON, usually an unterminated string in a large structured response. Graphiti often recovers through its internal retries, but some episodes can exhaust those retries. A larger `qwen2.5:7b` model is available as a slower fallback.

**Proposed:**

- Implement an explicit extraction route: `qwen2.5:3b` as the provisional fast primary and `qwen2.5:7b` as the provisional stronger fallback.
- Allow fallback only for approved failure classes such as malformed JSON, schema validation, and measured output truncation; never for authentication, invalid configuration, cancellation, or operator shutdown.
- Scope failures as item-specific or systemic; authentication, configuration, profile, database, or broad resource failures pause new claims instead of quarantining the corpus.
- Set independent same-candidate generation-attempt counts plus one hard maximum-provider-call budget covering every actual upstream request in the leased job attempt.
- Coordinate or disable Graphiti's opaque internal retries so nested layers cannot create a retry storm.
- Record transport, parse, schema, graph-validation, persistence, and verification failures separately.
- Reduce oversized extraction responses by splitting entity and relationship work when practical.
- Evaluate candidates, prompts, schemas, and extraction shape against a fixed, versioned representative episode corpus before changing defaults.
- Prefer schema-constrained generation where the Ollama and Graphiti versions support it.
- Record the actual model digest, route fingerprint, prompt/schema version, attempt number, latency, and sanitized outcome for every call.
- Report fallback success as degraded success so improving availability cannot hide a weak primary model.

**Acceptance criteria:**

- A repeatable benchmark reports parse success, schema success, primary/fallback success, end-to-end success, graph quality, latency, and token usage per candidate.
- Every primary-model failure either succeeds through the configured fallback or enters a visible failed state.
- No leased attempt exceeds its configured maximum number of provider calls.
- Attempt provenance coverage is 100 percent without storing episode text or secrets.
- No failed extraction is reported as synchronized.

### 2. Add a durable retry and quarantine queue

**Observed:** Failed rows currently remain `graphiti_synced = false`, which makes the import resumable but does not preserve failure reason, attempt history, or next action. During the current run, multiple rows exhausted the 3B model's retries; safety checks confirmed that they left neither a false PostgreSQL success flag nor an orphan Neo4j episode.

**Proposed:**

- Replace the Boolean-only lifecycle with `pending`, `leased`, `retry_wait`, `quarantined`, and `synced`; keep `graphiti_synced` temporarily as a derived compatibility field.
- Store state, desired source fingerprint, job-attempt count, next-attempt time, lease owner/expiry, last attempt ID, last error class/code, sanitized summary, sync-profile fingerprint, and verified timestamp.
- Store an append-only attempt ledger containing run, captured source fingerprint, route/candidate, prompt/schema version, timing, usage, outcome, and graph-count provenance.
- Claim work atomically with `FOR UPDATE SKIP LOCKED` or an equivalent proven mechanism.
- Use expiry and heartbeat semantics so interrupted workers safely return abandoned work to `retry_wait`.
- Use the stable episode UUID for idempotent Neo4j writes and independently verify it before the `synced` transition.
- Recheck the source fingerprint before success; if the episode changed during extraction, preserve the attempt but queue the new revision instead of marking stale work synchronized.
- Add CLI modes for listing state, retrying eligible work, explicitly retrying quarantined rows, and inspecting sanitized attempt chains.
- Use deterministic backoff and distinguish permanent failures from retryable ones.
- Quarantine only item-specific permanent failures; stop the run and preserve item budgets when a systemic failure makes further work unsafe.

**Acceptance criteria:**

- Operators can explain why any episode is pending or failed without reading transient console output.
- An interrupted run resumes without duplication or manual database edits.
- Retry selection is deterministic and test-covered.
- Two workers cannot hold a valid lease for the same episode.
- Faults injected before write, after write, before verification, and after verification converge without false success or duplicate stable IDs.
- A source edit during an active lease cannot leave the episode synchronized to stale content.
- Retrying quarantined work preserves all prior attempt records.
- A provider-wide authentication/configuration failure pauses claims and does not mass-quarantine or consume the attempt budgets of unrelated episodes.

### 3. Turn cross-store reconciliation into a first-class command

**Observed:** The strongest current audit compares PostgreSQL episode UUIDs with Neo4j `Episodic.stable_id` values and checks total, populated, and distinct counts. These checks are currently assembled from several manual commands.

**Implementation status:** The command, Make targets, read-only sessions, stable output, exit codes, legacy projection, and forward-compatible durable-job/profile checks were delivered on 2026-08-07. Post-migration and preserved-volume evidence remains outstanding.

**Proposed:**

- Add a `graph-audit` command that performs the complete PostgreSQL/Neo4j ID-set comparison.
- Report missing IDs, unexpected IDs, duplicate/null stable IDs, mismatched source descriptions/fingerprints, incorrectly synchronized jobs, incompatible profiles, and lifecycle counts.
- Support both a human-readable summary and machine-readable JSON.
- Return `0` for clean reconciliation, `1` for discovered drift, and `2` when invocation or infrastructure failure prevents a complete audit.
- Use read-only database credentials where practical and guarantee that the command never mutates either store.
- Expose the command through the Makefile and run it after imports and preserved-volume restarts.

**Acceptance criteria:**

- A zero exit code proves the defined one-to-one mapping and lifecycle invariants for every synchronized episode.
- Any mismatch produces actionable IDs and exit code `1`; an incomplete audit returns `2`, never a false clean result.
- The audit can run repeatedly without changing data.

### 4. Improve progress and failure observability

**Observed:** A full local import takes hours, while current console output emphasizes individual Graphiti warnings and does not provide a stable completion percentage, rolling throughput, retry count, or ETA. Invalid relationship proposals can dominate the output even when the episode itself succeeds.

**Proposed:**

- Give every import a run ID and emit structured, sanitized per-attempt outcomes plus periodic aggregate progress.
- Track attempted, primary-success, fallback-success, verified, retrying, quarantined, skipped, leased, and remaining counts.
- Show rolling episodes per minute and an explicitly approximate ETA.
- Separate expected rejected-edge warnings, extraction failures, persistence failures, and verification failures.
- Use bounded-cardinality metrics; keep episode IDs and sanitized error detail out of metric labels.
- Track Ollama queue depth, model load/reload time, GPU pressure, and whether graph work degrades interactive API/chat latency.
- Add Prometheus-compatible counters when long-running imports become a routine deployed operation.

**Acceptance criteria:**

- A single status line answers how much work is complete, how fast it is moving, and whether failures need attention.
- Logs distinguish data-quality warnings from synchronization failures.
- Progress remains accurate after a restart.
- Every quarantined row has a visible reason and complete sanitized attempt chain.

### 5. Measure and improve graph quality, not only graph completeness

**Observed:** The model frequently proposes relationship names or endpoints that do not match extracted nodes. Graphiti rejects those proposals, so episode linkage remains correct, but a successful episode can still produce few or no retained relationships.

**Proposed:**

- Define a canonical relationship vocabulary and normalize common aliases before persistence.
- Validate relationship endpoints against the current extraction result before calling graph maintenance code.
- Version the Graphiti/application implementation, vocabulary, alias map, extraction route/prompt, schemas, entity/edge definitions, and referenced embedding profile in the sync-profile fingerprint.
- Record proposed, accepted, normalized, and rejected entity/edge counts by stable reason code.
- Build a versioned reviewed lore set with expected entities and important relationships.
- Add minimum graph-quality thresholds separately from synchronization completeness.
- Require explicit reprocessing rather than silently mixing results after the sync profile changes.

**Acceptance criteria:**

- Quality reports show precision-oriented metrics for the reviewed corpus.
- Rejection reasons are measurable and trend downward after model or prompt changes.
- Completeness checks never imply that relationship extraction quality is acceptable.
- A candidate route cannot ship solely because it synchronized more episodes; it must also satisfy the reviewed quality threshold.

### 6. Benchmark safe throughput improvements

**Observed:** Early full-run throughput was about two verified episodes per minute, which puts a 611-episode import in the multi-hour range. The GPU has 8 GB of VRAM, so unconstrained parallel extraction risks model eviction or out-of-memory failures.

**Proposed:**

- Benchmark one and two concurrent extraction workers with fixed context and model residency settings.
- Isolate graph extraction and interactive text generation with separate queue/concurrency budgets.
- Measure GPU memory, model reloads, queue wait, parse/schema success, fallback rate, Neo4j contention, API/browser latency, and total verified throughput.
- Investigate shorter context or staged extraction only when graph-quality metrics remain stable.
- Preserve single-worker operation as the safe default until a benchmark proves otherwise.

**Acceptance criteria:**

- The chosen concurrency has a documented speedup and no regression in success or graph-quality rates.
- Resource limits prevent the local stack from destabilizing the API and browser chat services.
- An out-of-memory or model-eviction condition is surfaced as a classified failure and cannot trigger unbounded retries.

### 7. Add a repeatable local end-to-end release gate

**Observed:** Unit tests alone did not expose the browser stream CORS failure caused by the `Cache-Control` request header. Real desktop and mobile browser tests found it. Preserved-volume restart checks are also necessary to prove that PostgreSQL and Neo4j data survive normal local stack cycling.

**Proposed:**

- Add an automated local release gate covering Compose health, API and MCP readiness, embedding-profile preflight, one browser SSE chat, one representative Graphiti ingest, `graph-audit`, and preserved-volume restart.
- Keep browser assertions focused on user-visible completion, console errors, HTTP status, credential persistence, and responsive overflow.
- Document the browser driver's incremental-fetch instrumentation quirk so it is not confused with an application failure.
- Emit a machine-readable report containing the application revision, sanitized configuration/profile fingerprints, component results, timings, and artifact paths.
- Keep provider-billed live tests opt-in and separately credentialed; the local gate must remain usable in all-Ollama mode.

**Acceptance criteria:**

- One documented command runs the complete local gate and returns a reliable exit status.
- The gate detects a CORS preflight regression before release.
- Data counts and IDs remain unchanged after a normal `down` and `dev` cycle.
- Graph reconciliation and active embedding-profile checks are clean before and after the restart.
- The evidence report is sufficient to compare two candidate releases without reading transient terminal output.

## Delivery packages and dependencies

| Package                       | Scope                                                                              | Umbrella phase | Depends on                | Exit evidence                           |
| ----------------------------- | ---------------------------------------------------------------------------------- | -------------: | ------------------------- | --------------------------------------- |
| L0 — Baseline                 | Manual reconciliation, extraction/retrieval corpus, current 3B/7B/GPU measurements |              0 | None                      | Versioned baseline and clean snapshot   |
| L1 — Truth and recovery       | Durable states, attempt ledger, atomic leases, CLI, `graph-audit`, progress        |              1 | L0 and restorable backups | Fault-injection report and clean audit  |
| L2 — Extraction correctness   | Bounded 3B→7B route, schema validation, retry coordination, relationship quality   |              3 | L1 and versioned corpus   | Candidate comparison and approved route |
| L3 — Local resource tuning    | Separate budgets plus one/two-worker benchmark                                     |              9 | L2 correctness gates      | GPU/API/throughput comparison           |
| L4 — Local release automation | Compose/API/MCP/browser/ingest/audit/restart gate                                  |            8–9 | L1; extend after L2/L3    | Machine-readable release report         |

Execute L0 and L1 before changing providers or optimizing throughput. L2 establishes correctness before L3 tests speed. Build the release-gate skeleton during L1, then extend it as later capabilities arrive.

## Required evidence artifacts

- Verified database-backup reference, checksums, restore evidence, and recovery runbook.
- Sanitized resolved configuration plus application, model, route, prompt/schema, and embedding fingerprints.
- Baseline and candidate extraction/graph-quality reports.
- Graph-job migration and seed reconciliation report.
- Crash-window and concurrent-lease test results.
- Pre/post-import and pre/post-restart `graph-audit` JSON.
- One/two-worker GPU, throughput, model-residency, and API/browser-latency comparison.
- Complete local release-gate report with links to logs/screenshots where applicable.
- Decision record for every threshold, fallback class, lease duration, concurrency, and accepted deviation.

## Local decisions to close

| Decision                                              | Recommendation                                                                 | Decision gate            |
| ----------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------ |
| Primary/fallback route                                | Start evaluation with `qwen2.5:3b` → `qwen2.5:7b`                              | L0 exit                  |
| Fallback-eligible failures                            | Malformed JSON, schema validation, and proven output truncation only           | L0 exit                  |
| Provider-call ceiling                                 | Derive from the benchmark; validate one hard ceiling across all retry layers   | Before L1 exit           |
| Lease duration/heartbeat                              | Base on measured p99 extraction duration plus recovery headroom                | Before L1 implementation |
| Quarantine retry policy                               | Explicit operator action with immutable prior attempt history                  | Before L1 exit           |
| Parse, schema, fallback, and graph-quality thresholds | Set from the versioned corpus; approve before changing defaults                | L0/L2 exits              |
| Worker concurrency                                    | One by default; use two only if it passes all quality/resource/isolation gates | L3 exit                  |
| Browser/device coverage                               | Require desktop and mobile-responsive paths supported by the product           | Before L4 exit           |
