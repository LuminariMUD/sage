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

### 2026-08-07 - L1 durable schema and migration tooling checkpoint

- Added the immutable, checksum-tracked migration runner `src/scripts/migrate_database.py` with read-only status/check modes, per-migration transactions, a PostgreSQL advisory lock, application revision capture, and a required verified-backup reference for apply mode.
- Added `schemas/migrations/0001_graph_sync_lifecycle.sql` for run-level circuit state, authoritative jobs, immutable attempt identities, immutable attempt results, and immutable provider-call provenance.
- Added database constraints for lifecycle states, lease ownership/tokens/expiry, retry timing, verified source/profile identity, failure taxonomy, nonnegative usage/counts, one active run, and degraded fallback success.
- Added triggers that derive `episodes.graphiti_synced` from durable state, reject divergent direct writes, deterministically requeue a changed source revision, and prohibit update/delete operations on ledger tables.
- Added `make db-migrate-status`, `make db-migrate-check`, and backup-gated `make db-migrate` targets.
- Verified the migration in an isolated PostgreSQL schema, including seed reconciliation, Python/SQL fingerprint parity, direct-projection rejection, one-active-run enforcement, immutable-ledger rejection, durable success projection, and source-edit requeue behavior.
- Executed the complete migration against the current 611-row schema inside an explicit transaction; all DDL, the 611-row seed, and internal verification passed, then `ROLLBACK` removed every test artifact.

Live activation is intentionally pending. The migration command reports `0001_graph_sync_lifecycle` pending and no migration ledger. Capture and verify current PostgreSQL and Neo4j backups before applying it. The legacy worker remains stopped and must not be restarted.

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
