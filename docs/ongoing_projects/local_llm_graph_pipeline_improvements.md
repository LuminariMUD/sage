# Local LLM and Graph Pipeline Improvements

**Status:** Active investigation and backlog  
**Observed:** 2026-08-06 during the full local-development bootstrap  
**Scope:** Ollama, Graphiti, PostgreSQL-to-Neo4j synchronization, local observability, and browser chat verification

## Why this project exists

The local stack now runs end to end, including PostgreSQL, Neo4j, Ollama, the API, the MCP server, and the browser UI. The full 611-episode graph import exposed several opportunities to make the system faster, easier to operate, and more reliable with small local models.

The current sync is safe and resumable: PostgreSQL is marked synchronized only after exactly one Neo4j episode with the expected stable ID is independently verified. The improvements below build on that contract.

## Findings and proposed work

### 1. Make structured extraction reliable across model sizes

**Observed:** The local `qwen2.5:3b` reasoning model periodically returns malformed JSON, usually an unterminated string in a large structured response. Graphiti often recovers through its internal retries, but some episodes can exhaust those retries. A larger `qwen2.5:7b` model is available as a slower fallback.

**Proposed:**

- Add an explicit extraction-model policy: fast primary model, stronger fallback model, and bounded retry counts.
- Record parse failures separately from graph-validation failures.
- Reduce oversized extraction responses by splitting entity and relationship work when practical.
- Evaluate models and prompts against a fixed representative episode corpus before changing defaults.
- Prefer schema-constrained generation where the Ollama and Graphiti versions support it.

**Acceptance criteria:**

- A repeatable benchmark reports parse success, end-to-end success, latency, and token usage per model.
- Every primary-model failure either succeeds through the configured fallback or enters a visible failed state.
- No failed extraction is reported as synchronized.

### 2. Add a durable retry and quarantine queue

**Observed:** Failed rows currently remain `graphiti_synced = false`, which makes the import resumable but does not preserve failure reason, attempt history, or next action. During the current run, multiple rows exhausted the 3B model's retries; safety checks confirmed that they left neither a false PostgreSQL success flag nor an orphan Neo4j episode.

**Proposed:**

- Replace the Boolean-only lifecycle with explicit states such as `pending`, `processing`, `synced`, `retryable`, and `quarantined`.
- Store attempt count, model, last error class, sanitized error summary, and timestamps.
- Add CLI modes for retrying retryable rows, retrying quarantined rows with a named fallback model, and listing failures.
- Use a lease or lock timeout so interrupted workers safely return abandoned work to the queue.

**Acceptance criteria:**

- Operators can explain why any episode is pending or failed without reading transient console output.
- An interrupted run resumes without duplication or manual database edits.
- Retry selection is deterministic and test-covered.

### 3. Turn cross-store reconciliation into a first-class command

**Observed:** The strongest current audit compares PostgreSQL episode UUIDs with Neo4j `Episodic.stable_id` values and checks total, populated, and distinct counts. These checks are currently assembled from several manual commands.

**Proposed:**

- Add a `graph-audit` command that performs the complete PostgreSQL/Neo4j ID-set comparison.
- Report missing IDs, unexpected IDs, duplicate stable IDs, null stable IDs, and mismatched source descriptions.
- Support both a human-readable summary and machine-readable JSON.
- Expose the command through the Makefile and run it after imports and preserved-volume restarts.

**Acceptance criteria:**

- A zero exit code proves a one-to-one mapping for every synchronized episode.
- Any mismatch produces actionable IDs and a nonzero exit code.
- The audit can run repeatedly without changing data.

### 4. Improve progress and failure observability

**Observed:** A full local import takes hours, while current console output emphasizes individual Graphiti warnings and does not provide a stable completion percentage, rolling throughput, retry count, or ETA. Invalid relationship proposals can dominate the output even when the episode itself succeeds.

**Proposed:**

- Emit structured per-episode outcomes and periodic aggregate progress.
- Track attempted, linked, retried, quarantined, skipped, and remaining counts.
- Show rolling episodes per minute and an explicitly approximate ETA.
- Separate expected rejected-edge warnings from episode-level failures.
- Add Prometheus-compatible counters later if long-running imports become a routine deployed operation.

**Acceptance criteria:**

- A single status line answers how much work is complete, how fast it is moving, and whether failures need attention.
- Logs distinguish data-quality warnings from synchronization failures.
- Progress remains accurate after a restart.

### 5. Measure and improve graph quality, not only graph completeness

**Observed:** The model frequently proposes relationship names or endpoints that do not match extracted nodes. Graphiti rejects those proposals, so episode linkage remains correct, but a successful episode can still produce few or no retained relationships.

**Proposed:**

- Define a canonical relationship vocabulary and normalize common aliases before persistence.
- Validate relationship endpoints against the current extraction result before calling graph maintenance code.
- Record proposed, accepted, normalized, and rejected edge counts by reason.
- Build a small reviewed lore set with expected entities and important relationships.
- Add minimum graph-quality thresholds separately from synchronization completeness.

**Acceptance criteria:**

- Quality reports show precision-oriented metrics for the reviewed corpus.
- Rejection reasons are measurable and trend downward after model or prompt changes.
- Completeness checks never imply that relationship extraction quality is acceptable.

### 6. Benchmark safe throughput improvements

**Observed:** Early full-run throughput was about two verified episodes per minute, which puts a 611-episode import in the multi-hour range. The GPU has 8 GB of VRAM, so unconstrained parallel extraction risks model eviction or out-of-memory failures.

**Proposed:**

- Benchmark one and two concurrent extraction workers with fixed context and model residency settings.
- Measure GPU memory, model reloads, parse success, Neo4j contention, and total verified throughput.
- Investigate shorter context or staged extraction only when graph-quality metrics remain stable.
- Preserve single-worker operation as the safe default until a benchmark proves otherwise.

**Acceptance criteria:**

- The chosen concurrency has a documented speedup and no regression in success or graph-quality rates.
- Resource limits prevent the local stack from destabilizing the API and browser chat services.

### 7. Add a repeatable local end-to-end release gate

**Observed:** Unit tests alone did not expose the browser stream CORS failure caused by the `Cache-Control` request header. Real desktop and mobile browser tests found it. Preserved-volume restart checks are also necessary to prove that PostgreSQL and Neo4j data survive normal local stack cycling.

**Proposed:**

- Add an automated local release gate covering Compose health, API and MCP health, one browser SSE chat, graph reconciliation, and preserved-volume restart.
- Keep browser assertions focused on user-visible completion, console errors, HTTP status, credential persistence, and responsive overflow.
- Document the browser driver's incremental-fetch instrumentation quirk so it is not confused with an application failure.

**Acceptance criteria:**

- One documented command runs the complete local gate and returns a reliable exit status.
- The gate detects a CORS preflight regression before release.
- Data counts and IDs remain unchanged after a normal `down` and `dev` cycle.

## Suggested implementation order

1. Cross-store `graph-audit` command.
2. Durable retry and quarantine metadata.
3. Structured progress and failure reporting.
4. Model fallback policy and extraction benchmark corpus.
5. Graph-quality metrics and relationship normalization.
6. Throughput benchmark and bounded concurrency.
7. Unified local end-to-end release gate.

The first three items reduce operational risk immediately. Model, quality, and throughput work should then be evaluated together so a speed improvement cannot silently reduce graph usefulness.
