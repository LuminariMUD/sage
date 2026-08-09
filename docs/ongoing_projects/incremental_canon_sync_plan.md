# Incremental Canon Synchronization Plan

| Field        | Value                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------- |
| Status       | Proposed; implementation has not started                                                     |
| Last updated | 2026-08-09                                                                                  |
| Scope        | Canon file discovery, revisions, semantic episodes, embeddings, Graphiti, Neo4j, and audits |
| Candidate    | [CocoIndex](https://cocoindex.io/docs/index) as the incremental reconciliation engine       |
| Related      | [Local LLM and Graph Pipeline Improvements](./local_llm_graph_pipeline_improvements.md)      |

## Executive summary

Replace the current sequence of independent loader, chunker, and embedding scripts
with a declarative incremental ingestion flow while retaining Sage's existing
provider controls, durable Graphiti worker, attempt ledger, graph audit, and
backup-gated rebuild machinery.

The proposed boundary is:

```text
lore_docs/canon
       |
       v
   CocoIndex
       |
       v
PostgreSQL documents, immutable revisions, active episodes, and embeddings
       |
       v
durable graph action outbox
       |
       v
existing Graphiti worker
       |
       v
     Neo4j
```

CocoIndex is the candidate because it provides filesystem change detection,
memoized transformations, desired-state reconciliation, automatic stale-output
removal, and native PostgreSQL/pgvector and Neo4j connectors. It is Apache-2.0
licensed and supports custom target connectors. It is not a distributed
transaction coordinator: target writes can be atomic within one backend, but not
across PostgreSQL and Neo4j. For that reason, PostgreSQL remains the authoritative
source and outbox, and the existing durable graph worker remains the only component
authorized to mutate the production graph.

This is a medium-sized refactor rather than a dependency-only change. A safe batch
MVP is estimated at 7-10 engineering days. The full production system described
here is estimated at 15-25 engineering days, or approximately 3-5 weeks for one
experienced engineer, excluding long-running provider backfills.

## Problem statement

The current pipeline reliably handles a newly inserted canon file when an operator
runs every stage, but it does not provide complete reconciliation semantics:

- File changes update `lore_documents.body_md` and legacy Graphiti document status,
  but do not reset the `processing_status` used by episode creation.
- Episode upserts change text without clearing the previous embedding.
- Embedding generation processes only episodes whose embedding is `NULL`.
- Files removed or renamed below `lore_docs/canon` are not reconciled out of the
  relational or graph-derived state.
- A changed episode is requeued by the database fingerprint trigger, but the
  current graph processor refuses to overwrite a Neo4j episode whose content no
  longer matches the PostgreSQL episode.
- There is no file watcher, deployment hook, or scheduled canon-ingestion service.

The new system must treat PostgreSQL and Neo4j as derived views of the current canon
corpus while preserving enough immutable revision and attempt evidence to explain
how each view was produced.

## Current operator workflow

Until this project is implemented, the supported path is additive and manual. For
a brand-new Markdown file beneath `lore_docs/canon/`, run:

```bash
make pipeline-canon CONFIRM_GRAPH_SYNC=RUN_DURABLE_GRAPH_SYNC
```

Then inspect `make status`, `make embedding-status`, and `make graph-sync-status`.
The confirmation token is mandatory because the final stage can call the configured
provider and write durable Neo4j state. `make semantic-pipeline` is only an alias
for `pipeline-canon` and requires the same token. No watcher or deployment hook
runs this automatically. Existing-file edits, renames, and deletions remain outside
the clean incremental guarantee described above.

## Goals

1. Detect canon additions, edits, shortened documents, renames, and deletions.
2. Recompute only artifacts affected by source or processing-profile changes.
3. Never return stale chunks or embeddings from superseded canon revisions.
4. Reconcile Graphiti episodes without duplicate identities or silent stale facts.
5. Preserve the durable graph attempt, provider-call, retry, and quality ledgers.
6. Recover after interruption without manual flag resets or destructive cleanup.
7. Keep `lore_docs/canon` as the fail-closed production corpus boundary.
8. Support read-only planning and status operations that make no provider calls.
9. Support both an explicit one-shot update and an opt-in live watcher.
10. Provide cross-store audits and a backup-backed rollback path.

## Non-goals

- Replacing Graphiti, the lore relationship policy, or the Neo4j query model during
  the initial migration.
- Replacing chat agents, retrieval orchestration, validation agents, or correction
  workflows.
- Ingesting drafts, meta documentation, PDFs, or non-Markdown files.
- Automatically changing the active embedding or Graphiti provider profile.
- Providing a distributed transaction across PostgreSQL and Neo4j.
- Removing the existing graph rebuild and backup systems.

## Architectural decisions

### PostgreSQL remains authoritative

CocoIndex will reconcile the filesystem into PostgreSQL only. A PostgreSQL
transaction will publish the current document/revision/episode state together with
durable graph actions. Neo4j mutations remain asynchronous and are completed by the
existing leased Graphiti worker.

This keeps the cross-store failure boundary explicit:

1. Canon and embedding state commits in PostgreSQL.
2. A durable graph action becomes eligible.
3. The Graphiti worker reserves provider calls, performs the graph mutation, and
   records independently verified success.
4. Audits compare the desired PostgreSQL state with the observed Neo4j state.

### Revisions are immutable

A document update creates a new immutable revision rather than changing the source
identity beneath previously processed episodes. PostgreSQL retains old revisions
for provenance and rollback, while retrieval selects only the active revision.

Proposed identities:

- `document_id`: stable identity for the canonical relative path.
- `revision_id`: deterministic identity derived from `document_id` and the full
  SHA-256 content hash.
- `episode_id`: immutable identity derived from the revision, chunker profile,
  episode ordinal, and episode-content hash.
- `source_fingerprint`: the existing normalized episode-text fingerprint used by
  graph synchronization.
- `embedding_profile_fingerprint`: the existing immutable embedding identity.
- `chunker_profile_fingerprint`: versioned chunking implementation and parameters.

For the first release, a rename is treated as deletion plus addition. Preserving
identity across renames can be added later through an explicit, validated stable ID
in document frontmatter; filename/content heuristics must not guess identity.

### Old rows are retired before they are physically removed

Existing graph attempt rows intentionally use restrictive foreign keys and
append-only evidence. Superseded episode rows must therefore be marked inactive,
not immediately deleted. Retrieval queries will require active document, revision,
and episode state. Retention cleanup, if added later, must preserve or archive the
durable ledger first.

### Processing profiles are dependencies

The following values participate in change detection and invalidation:

- Chunker implementation version and all chunking parameters.
- Embedding provider, model, revision, implementation, dimensions,
  normalization, encoding, and distance metric.
- Graphiti prompt, schema, entity/edge contracts, extraction bounds, provider
  route, and embedding profile.

A profile change must produce a visible plan before any provider request. Existing
embedding shadow-space and graph rebuild controls remain authoritative for provider
or dimension migrations.

### Automation is opt-in

The initial default is a one-shot reconciliation command. Live watching is enabled
only by an explicit deployment setting and retains provider budgets, retry limits,
and systemic circuit breakers. Saving a file must never silently bypass the current
paid-provider or graph-worker authorization model.

## Proposed data model

The exact migration design will be finalized after the shadow spike, but the model
must expose these concepts.

### `lore_document_revisions`

One immutable row for every observed canon document revision.

Suggested fields:

- `id UUID PRIMARY KEY`
- `document_id UUID NOT NULL`
- `content_hash TEXT NOT NULL`
- `body_md TEXT NOT NULL`
- `metadata JSONB NOT NULL`
- `observed_at TIMESTAMPTZ NOT NULL`
- `superseded_at TIMESTAMPTZ`
- unique `(document_id, content_hash)`

### `lore_documents`

Continue to represent stable source identity, with additions such as:

- `current_revision_id UUID`
- `source_state TEXT` with `active` or `deleted`
- `last_seen_ingestion_run_id UUID`
- a unique canonical `source_file`

The existing body and hash columns can remain as a compatibility projection during
cutover, then be retired only after all readers use revisions.

### `episodes`

Episodes become immutable revision artifacts. Suggested additions:

- `revision_id UUID NOT NULL`
- `active BOOLEAN NOT NULL DEFAULT TRUE`
- `content_hash TEXT NOT NULL`
- `chunker_profile_fingerprint TEXT NOT NULL`
- `embedding_profile_fingerprint TEXT`
- unique immutable episode identity rather than an update-in-place dependency on
  `(document_id, episode_index)`

The old `(document_id, episode_index)` uniqueness rule must be replaced or scoped
to the active revision. Retrieval must explicitly filter active canon episodes.

### `graph_sync_actions`

Extend or supersede the current one-row-per-episode job model with an action-aware
outbox:

- `action`: `add`, `supersede`, or `delete`
- immutable episode/revision identity
- desired source and sync-profile fingerprints
- lifecycle state, lease, retry generation, and attempt counters
- dependency ordering where a replacement must be verified before retirement is
  finalized

Existing run, attempt, provider-intent, result, and relationship-quality rows must
remain append-only. Migrations must reconcile old `graph_sync_jobs` into the new
contract without losing history.

### `canon_ingestion_runs`

Record sanitized operational evidence for each reconciliation:

- mode: `plan`, `update`, `live`, `shadow`, or `recovery`
- source inventory fingerprint
- processing profile fingerprints
- added, changed, unchanged, renamed-as-delete/add, and deleted counts
- episode and embedding delta counts
- start, completion, and terminal state
- error class and bounded sanitized summary

Do not store credentials, vectors, prompts, responses, or full lore text in this
ledger.

## Graph revision semantics gate

Graph update behavior is the highest-risk decision and must be proven before schema
activation.

The preferred model is:

1. Each active revision chunk has an immutable Graphiti episode UUID.
2. A changed document produces new episode UUIDs rather than overwriting old
   episode content.
3. New revision episodes are added in deterministic document/episode order so
   Graphiti can invalidate contradicted temporal facts.
4. Old episode associations are retired only after replacement episodes verify.
5. Deleting canon emits explicit graph cleanup actions.

The spike must test Graphiti episode deletion and replacement for:

- A changed fact that explicitly contradicts the old fact.
- A fact removed without a replacement statement.
- A shared entity or relationship supported by multiple documents.
- Node summary text derived partly from a deleted episode.
- A previously invalidated fact whose invalidating episode is removed.

If targeted Graphiti operations cannot make the production graph represent active
canon exactly, choose one of these controlled fallbacks:

1. Mark graph edits/deletions as requiring the existing backup-gated full rebuild.
2. Add source-support ownership metadata and a document-scoped repair operation.
3. In a separately approved project, replace Graphiti-derived storage with a
   CocoIndex-owned current-state property graph.

The initial project must not silently substitute generic LLM triple extraction for
Graphiti's temporal and relationship-quality behavior.

## Operator interface

Target commands, names subject to repository convention review:

```bash
sage-ingest plan       # Read-only delta; no provider or target writes
sage-ingest update     # One-shot source-to-PostgreSQL reconciliation
sage-ingest live       # Opt-in filesystem watch and bounded reconciliation
sage-ingest status     # Read-only run and artifact status
sage-ingest audit      # Filesystem/PostgreSQL/Neo4j reconciliation
```

Make targets should wrap these commands during migration:

```bash
make canon-sync-plan
make canon-sync
make canon-sync-status
make canon-sync-audit
```

The existing `load-canon`, `create-episodes`, and `generate-embeddings` targets
should initially remain as deprecated wrappers. They can be removed only after the
rollback bake period and documentation update are complete.

## Implementation phases

### Phase 0 - Semantics and shadow spike

Estimated effort: 2-4 engineering days.

- [ ] Pin a candidate CocoIndex release only in an isolated spike environment.
- [ ] Confirm Python, asyncpg, pgvector, Docker, and licensing compatibility.
- [ ] Implement canon-only local filesystem discovery with resolved-path and
      symlink-escape rejection.
- [ ] Wrap the existing semantic chunker as a deterministic transformation.
- [ ] Wrap the existing configured embedder and bind its full profile fingerprint
      as a declared dependency.
- [ ] Write only to shadow PostgreSQL tables; do not touch production episode or
      graph state.
- [ ] Measure add, no-op, edit, shortened-file, rename, deletion, chunker-change,
      and embedding-profile-change deltas.
- [ ] Confirm unchanged chunks avoid provider calls and deleted chunks disappear
      from the declared target state.
- [ ] Exercise process termination during transformation and target application.
- [ ] Run the Graphiti revision-semantics cases against an isolated graph.

Exit gate:

- A written decision records whether Graphiti targeted replacement is exact enough
  or whether edits/deletes require a controlled rebuild.
- Shadow results are deterministic across two clean runs.
- No production provider request, database write, or graph mutation occurs.

### Phase 1 - Schema and reconciliation contracts

Estimated effort: 2-3 engineering days.

- [ ] Add immutable numbered migrations for revisions, active episode state,
      ingestion runs, profile metadata, and graph actions.
- [ ] Define stable IDs and fingerprints in both Python and SQL where applicable.
- [ ] Replace update-in-place uniqueness assumptions without dropping old evidence.
- [ ] Add canon-only constraints for every new artifact path.
- [ ] Update retrieval queries to select only active canon revisions and episodes.
- [ ] Add migration reconciliation checks and rollback-only live-schema rehearsal.
- [ ] Update backup inventory and restore verification for the new tables.

Exit gate:

- Migrations pass isolated integration tests and a rollback rehearsal.
- Existing active corpus counts, vectors, graph jobs, and attempt history remain
  unchanged before activation.
- Every retrieval path has an active-corpus guard.

### Phase 2 - Source, chunk, and embedding flow

Estimated effort: 3-5 engineering days.

- [ ] Implement the production CocoIndex app with one component per canon file.
- [ ] Create immutable revisions and declare the active revision for each source.
- [ ] Produce revision-specific episodes with deterministic identities.
- [ ] Integrate embedding preflight before constructing an adapter or making a
      provider request.
- [ ] Reuse memoized embeddings only when the complete embedding profile and chunk
      input match.
- [ ] Retire stale episode occurrences when a revision is superseded or deleted.
- [ ] Publish graph actions in the same PostgreSQL transaction as active-state
      changes.
- [ ] Add plan, update, status, and recovery entrypoints with sanitized output.
- [ ] Add Make and Docker integration while leaving live mode disabled by default.

Exit gate:

- New, edited, shortened, renamed, and deleted files converge in PostgreSQL.
- No inactive episode is available to vector, lexical, or hybrid retrieval.
- A repeated no-op run performs zero embedding provider calls.

### Phase 3 - Graph action lifecycle

Estimated effort: 3-5 engineering days.

- [ ] Extend durable claim and lease models to include graph action type and
      revision identity.
- [ ] Preserve reserve-before-network provider accounting for every Graphiti call.
- [ ] Add idempotent add, supersede, and delete processing based on Phase 0's
      approved semantics.
- [ ] Enforce replacement ordering and token fencing across source revisions.
- [ ] Prevent stale workers from verifying superseded revisions.
- [ ] Extend relationship-quality evidence to revision actions where applicable.
- [ ] Extend graph audit to active revisions, expected retired episodes, source
      support, and unexpected Neo4j records.
- [ ] Add crash injection before and after each PostgreSQL, provider, and Neo4j
      boundary.

Exit gate:

- Every graph action converges after interruption without duplicate episode IDs or
  false PostgreSQL success.
- Active PostgreSQL revisions and Neo4j state reconcile under the approved graph
  semantics.
- Existing provider budgets, retry generations, quarantine, and systemic pause
  behavior remain enforced.

### Phase 4 - Automation and operations

Estimated effort: 2-3 engineering days.

- [ ] Add an opt-in, role-specific live-sync container or process.
- [ ] Debounce filesystem bursts and serialize changes for one canonical path.
- [ ] Define deployment authorization for automatic embedding and graph provider
      calls; retain an inert default.
- [ ] Expose ingestion lag, pending graph actions, failures, retries, and last clean
      audit in operational readiness.
- [ ] Add bounded shutdown and restart recovery.
- [ ] Update deployment, quickstart, pipeline, troubleshooting, and security docs.
- [ ] Deprecate legacy commands with actionable replacement messages.

Exit gate:

- Live mode survives service restart and filesystem event bursts.
- Read-only modes never create clients that can make provider or target writes.
- Operator documentation includes enable, disable, drain, recover, audit, and
  rollback procedures.

### Phase 5 - Shadow rollout and cutover

Estimated effort: 2-4 engineering days, excluding provider runtime.

- [ ] Create and independently verify PostgreSQL and Neo4j backups.
- [ ] Run a full shadow backfill under recorded source and processing profiles.
- [ ] Compare document, revision, episode, embedding, and retrieval results with the
      current pipeline.
- [ ] Run reviewed retrieval and graph-quality benchmarks.
- [ ] Rehearse cutover and rollback against restored copies.
- [ ] Activate the new read path only after clean count, fingerprint, retrieval,
      and graph audits.
- [ ] Observe a bake period covering at least one add, edit, shorten, rename, and
      deletion cycle.
- [ ] Remove or freeze legacy write paths after the bake period.

Exit gate:

- The current production canon corpus is fully represented under one recorded set
  of chunker, embedding, and graph profiles.
- Cross-store audit is clean, operational readiness has no critical alerts, and
  rollback evidence is current.

## Test matrix

### Source reconciliation

- New Markdown file below a recognized canon category.
- New Markdown file below an unrecognized canon category.
- Unchanged file with changed filesystem modification time.
- Content edit with unchanged title.
- Title edit and content edit.
- File shortened from many episodes to fewer episodes.
- File expanded with unchanged leading sections.
- Empty file and whitespace-only file.
- Rename within canon.
- Move between canon categories.
- File deletion.
- Symlink escaping canon.
- Non-Markdown file and draft/meta file.
- Two paths with identical content.

### Profile invalidation

- Chunk size, overlap, threshold, or chunker-version change.
- Embedding provider, model, revision, dimension, encoding, or normalization change.
- Graph prompt, schema, ontology, extraction bound, or provider-route change.
- Profile change during an active run.
- Attempted mixed-profile writes into an active vector or graph space.

### Failure and concurrency

- Crash before and after embedding provider dispatch.
- Crash before and after PostgreSQL target commit.
- Crash before and after Graphiti provider dispatch.
- Crash before and after Neo4j mutation and verification.
- Duplicate filesystem events.
- Concurrent one-shot and live runs.
- Lease expiry and stale worker completion.
- Provider timeout, authentication error, rate limit, malformed output, and
  verification failure.
- Database or graph unavailable during reconciliation.

### Retrieval and graph correctness

- Inactive revisions never appear in lexical, vector, hybrid, agent, or MCP reads.
- Source attribution resolves to the active document revision.
- Deleted source content is absent from retrieval.
- Changed facts have the expected current temporal state.
- Removed facts do not remain current without active source support.
- Shared entities and relationships survive retirement of only one supporting
  document.
- Audits detect missing, unexpected, duplicate, stale-profile, and stale-revision
  graph records.

## Observability and safety requirements

- Every mutating run has an immutable, sanitized run identity.
- Every provider request is reserved before network I/O and completed separately.
- Metrics report documents and episodes added, updated, retired, and unchanged;
  embeddings requested/reused; graph actions by state; and reconciliation lag.
- Logs and ledgers exclude source lore, prompts, responses, vectors, credentials,
  raw provider errors, and unbounded filesystem paths.
- The live service uses a dedicated container role and health check.
- File events are hints only; each run computes a complete desired-state inventory
  so missed or duplicated events cannot cause drift.
- Destructive graph rebuilds retain their existing backup and exact-confirmation
  gates.
- CocoIndex internal state is backed up or reproducibly rebuildable; it must never
  become the sole copy of canon or durable graph evidence.

## Migration and rollback strategy

### Migration

1. Pin and validate CocoIndex without modifying production requirements.
2. Populate shadow tables from the current canon corpus.
3. Compare deterministic identities, chunks, embeddings, and retrieval quality.
4. Apply additive schema migrations after verified backups.
5. Dual-run legacy and new planners read-only; allow only one writer.
6. Backfill revisions and active episode mappings without rewriting existing
   vectors or graph evidence unless separately authorized.
7. Activate the new PostgreSQL write path.
8. Drain and audit graph actions under the approved profile.
9. Activate the new retrieval filter/path.
10. Enable live watching only after one-shot cutover remains clean through the bake
    period.

### Rollback

1. Disable the live watcher and stop claiming new graph actions.
2. Allow any currently leased action to finish or expire under token fencing.
3. Restore the prior application read path while retaining new revision rows.
4. Use the verified database/graph backups if graph activation changed derived
   state that cannot be reversed through audited actions.
5. Do not delete new ledgers during rollback; retain them as operational evidence.

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| CocoIndex v1 maturity or API churn | Pin the validated version; isolate it behind Sage adapters; require the shadow spike and restart tests. |
| PostgreSQL/Neo4j cross-target inconsistency | Keep PostgreSQL authoritative, publish an outbox transactionally, and retain durable graph retries and audits. |
| Graphiti cannot exactly retract an edited document | Make graph semantics a Phase 0 gate; require controlled rebuild or source-ownership repair when targeted operations are insufficient. |
| Duplicate or unstable chunk identities | Use deterministic revision-scoped identities and test repeated clean runs. |
| Stale embeddings after content or profile changes | Make text and the full embedding profile part of the memoization key and store the profile fingerprint with every active vector. |
| Missed filesystem events | Treat watch events as triggers for full desired-state reconciliation, not as authoritative mutations. |
| Provider-cost bursts | Debounce changes, retain hard provider budgets, expose plans, and keep live provider calls opt-in. |
| Legacy readers expose retired data | Inventory every retrieval query and enforce active-corpus guards before activation. |
| Migration breaks durable history | Use additive immutable migrations, backup verification, isolated integration tests, and rollback-only live rehearsals. |

## Definition of done

The project is complete only when all of the following are true:

- Adding a canon file makes it searchable through embeddings and Graphiti within
  the configured synchronization SLA.
- Editing a canon file creates a new immutable revision and exposes no stale
  episode or vector through production retrieval.
- Shortening or deleting a file retires every obsolete derived artifact.
- A no-op reconciliation produces no embedding or graph provider calls.
- Changes to processing code or profiles invalidate exactly the documented scope.
- Every supported crash point converges on retry without duplicates, false success,
  or manual state resets.
- Drafts, meta files, non-Markdown inputs, and escaped symlinks cannot acquire
  revisions, episodes, embeddings, or graph actions.
- PostgreSQL-to-Neo4j audits are clean for active and deliberately retired state.
- Backups, restore rehearsal, operator runbooks, monitoring, and rollback evidence
  are complete.
- Legacy write paths are disabled or removed after the agreed bake period.

## External references

- [CocoIndex documentation](https://cocoindex.io/docs/index)
- [CocoIndex target-state reconciliation](https://cocoindex.io/docs/programming_guide/target_state/)
- [CocoIndex PostgreSQL connector](https://cocoindex.io/docs/connectors/postgres/)
- [CocoIndex Neo4j connector](https://cocoindex.io/docs/connectors/neo4j/)
- [CocoIndex custom target connectors](https://cocoindex.io/docs/advanced_topics/custom_target_connector/)
- [CocoIndex crash recovery and cross-target transaction boundary](https://cocoindex.io/docs/faq/)
- [Graphiti](https://github.com/getzep/graphiti)
