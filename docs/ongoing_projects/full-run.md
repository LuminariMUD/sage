# Full Canon Ingestion Run

## Objective

Fully ingest the current `lore_docs/canon` corpus into every serving layer:
PostgreSQL source records, semantic episodes, full-text indexes, embeddings,
pgvector retrieval, and the durable Neo4j/Graphiti graph. Preserve an auditable
recovery path and do not declare completion until the cross-store audits pass.

This file is the live run journal. Timestamps use Asia/Jerusalem unless marked
as UTC. It intentionally records failures and incomplete findings as well as
successful gates.

## Corpus inventory

Inventory taken on 2026-08-10:

- 26 Markdown files under `lore_docs/canon`.
- 72,554 words and 475,088 bytes.
- PostgreSQL initially contained 16 canon documents and 1,185 episodes.
- Ten source files were absent from PostgreSQL:
  - `canon/cultures/living_customs_of_lumia.md`
  - `canon/cultures/tales_told_against_the_dark.md`
  - `canon/cultures/the_courts_of_hunger.md`
  - `canon/factions/DEITIES.md`
  - `canon/factions/THE_TWO_ORDERS_OF_DIVINITY.md`
  - `canon/factions/the_three_embers.md`
  - `canon/locations/the_ashenport_road.md`
  - `canon/world/relics_and_the_art_of_making.md`
  - `canon/world/the_feyveil_and_the_otherworld.md`
  - `canon/world/the_roads_of_magic.md`
- Seven existing source records had hashes different from their files:
  - `canon/cultures/languages_of_the_homelands.md`
  - `canon/cultures/races_of_lumia.md`
  - `canon/cultures/the_crystal_dwarves_of_nagburim.md`
  - `canon/factions/the_villian_hierarchy.md`
  - `canon/locations/the_thirteen_homelands.md`
  - `canon/timeline/ages.md`
  - `canon/timeline/timeline.md`

## Recovery and graph-rebuild controls

- Created and verified backup
  `backups/pre-canon-refresh-20260809T215401Z` before destructive graph work.
- Backup verification included PostgreSQL scratch restore, offline Neo4j dump
  consistency checks, SHA-256 checksums, and cleanup of scratch resources.
- Initial Neo4j audit found 1,205 `Episodic` nodes versus 1,185 PostgreSQL
  episodes. The 20 nodes without stable IDs were verified benchmark/test
  artifacts (four instances each of five known test episode names).
- Deleted exactly those 20 null-stable-ID test nodes after the verified backup.
- The resulting pre-rebuild graph audit was clean at 1,185/1,185 episodes.
- Opened controlled rebuild operation
  `86c5a09e-8181-4dbe-a54a-1fe5700f19a4`.
- Target graph sync profile:
  `sync:sha256:047f36d980e514f169003816262ef8eebc611d5a806f20bf403c7ba393bd5dc4`.
- Target embedding profile:
  `embedding:sha256:656eec8aa2aa4cedc0af78937f2a2a482452379294e268d85e95b37c771df02b`.

## Issues, errors, and bugs found

### Canon loader defects

The first live loader attempt exposed three defects. Seven new documents loaded,
but the three new `world/` documents and all seven changed documents failed:

1. `world/` mapped to the nonexistent PostgreSQL enum value
   `worldbuilding`; the deployed enum uses `world`.
2. The changed-document update referenced a nonexistent
   `graphiti_processed_at` column.
3. Changed documents retained `processing_status = 'completed'`, so the episode
   creator skipped their revised content.

Fixes in `src/scripts/load_documents.py`:

- Map `world/` to `world`.
- Refresh title, type, body, summary, metadata, and content hash on change.
- Reset `graphiti_status` and `processing_status` to `pending` and clear
  `processed_at`.
- Remove the invalid column reference.

The corrected rerun processed all 26 documents with zero errors, and source
paths plus SHA-256 hashes matched the files exactly.

The broader warning audit also found that loader metadata used deprecated
`datetime.utcnow()` and emitted timezone-naive modification times. The loader
now writes both `loaded_at` and `file_modified_at` as timezone-aware UTC ISO-8601
values.

### Stale vector risk on episode updates

The episode UPSERT replaced text but retained the old embedding. A changed
episode could therefore serve a vector for different text.

Fix in `src/scripts/create_episodes_from_documents.py`: set `embedding = NULL`
when stored text differs from incoming text. The embedding generator then
backfills the correct vector.

### Residual duplicate episode after rechunking

Exact source-to-episode recomputation produced 2,429 expected chunks while the
database contains 2,430 episodes. There are no missing expected chunks. The
single extra row is episode `eda9056b-32a1-498c-8cf8-07f5c35bd78c`, index 54
for `canon/cultures/races_of_lumia.md`; its text is an exact duplicate of a
current expected chunk.

The row has historic durable attempts, and the append-only attempt ledger
correctly prevents ad-hoc deletion. It is not stale content, but it can produce
duplicate retrieval/graph evidence. This run preserves ledger integrity and
tracks the row as a data-model improvement opportunity rather than bypassing
the lifecycle.

### Neo4j stable-ID constraint bootstrap bug

Graphiti initialization created a normal `Entity.stable_id` index before asking
Neo4j to create a uniqueness constraint on the same label/property. Neo4j
rejects the constraint because the standalone index already occupies that
schema, producing a repeated `ClientError` warning.

Fix in `src/graphiti/__init__.py`:

- Create the uniqueness constraint directly and let it own its backing range
  index.
- Remove creation of the conflicting standalone index.
- Replaced the live index after confirming 131 entity nodes had zero populated
  stable IDs and no duplicates.
- Added `tests/graphiti/test_initialization.py` as regression coverage.

The live constraint is now online as `entity_stable_id_unique`.

### GraphRAG relationship endpoint enrichment bug

The live Crystal Dwarves RAG smoke test initially returned valid relationship
UUIDs but rendered every `target_name` as `Unknown`. The API looked for the
target entity's display name/type in generic relationship properties instead of
the entity records it had already fetched by UUID. Generic edge `name`/`type`
properties are also not valid endpoint identity fallbacks.

Fix in `src/api/main.py`:

- Resolve target display fields from the fetched `EntityResponse` UUID map.
- Accept only explicit `target_name` and `target_type` properties as a fallback
  when the endpoint entity is unavailable.
- Added `tests/test_rag_graph_enrichment.py` for entity-map precedence and safe
  fallback behavior.

The repeated authenticated live request returned 15 relationships with zero
unknown target names and zero unknown target types.

### Graph extraction semantic-quality findings

Synchronization and structural audits do not prove that every model-extracted
entity is grounded correctly. A targeted source trace found:

- `AAN conference` occurs nowhere in the 26-file canon corpus, but the model
  extracted it from four Crystal Dwarf episodes. A later graph-wide snapshot
  found four entity UUIDs carrying that name with the mutually inconsistent
  types `Event`, `Organization`, `Race`, and `Person`.
- `Lumia` occurs in the source, but its current entity is typed `Person` rather
  than a world/location.
- At 77 successful attempts, relationship policy evidence covered 100% of
  attempts but rejected 299 of 507 proposals (58.974%): 177 missing endpoints,
  115 unknown relationship types, and 7 duplicates. The 208 accepted proposals
  remain structurally valid, but the policy does not currently prove entity-name
  grounding or type correctness.
- In a graph-wide snapshot near 100 synchronized episodes, 37 of 396 examined
  entity/episode links had an entity name with no literal case-insensitive
  grounding in the linked episode, and 22 entity nodes had names absent from the
  entire current canon corpus. A missing literal occurrence is a review signal,
  not by itself proof of hallucination, because aliases and reasonable derived
  labels can also produce it. Obvious source-absent examples included `AAN
  conference`, `Dr. Amara Osei`, `Dr. Osei's colleague`, and `Captain Morrow
  'Deepdrinker' Vane`.
- The same snapshot contained 72 exact case-insensitive duplicate-name groups
  spanning 204 entity nodes; 35 groups carried conflicting entity types.
  Examples included 17 `Divine Knight Concordance` nodes, 10 `Pale Throne`
  nodes, and 7 `Crimson Spindle` nodes.

Inspection of the installed `graphiti_core` text-extraction prompt identified a
conclusive contamination source. Its few-shot example contains `Dr. Amara Osei`
and `AAN conference`, while one of its generic qualification examples contains
`Dr. Osei's colleague`. Those exact three names are absent from canon and were
nevertheless created in the graph. The prompt correctly tells the model to use
only current text, but the local 7B model is leaking example entities into its
structured response.

A repeatable read-only audit now replaces those one-off queries. It scopes Neo4j
entities to episodes whose durable PostgreSQL job state is `synced`, applies a
documented Unicode/case/whitespace literal-grounding rule, emits exact counts and
bounded samples without source text, and labels findings `review_required`
rather than asserting that every nonliteral alias is a hallucination. Live
snapshots from `make graph-semantic-audit-json` found:

- At 123 synchronized episodes: 448 entities, 75 duplicate-name groups spanning
  213 nodes, 34 conflicting-type groups, 25 nodes absent from the full canon, 103
  ungrounded entity/episode links, and 15 entities with no domain-type label.
- At 141 synchronized episodes after serialization: 467 entities, the same 75
  duplicate-name groups, 214 nodes in those groups, the same 34 conflicting-type
  groups, 28 source-absent nodes, 111 ungrounded links, and 17 entities without a
  domain-type label.
- At 167 synchronized episodes: 522 entities, the same 75 duplicate-name groups
  spanning 218 nodes, 35 conflicting-type groups, 30 source-absent nodes, 124
  ungrounded links, and 17 entities without a domain-type label. Of 1,029 named
  links with an available episode source, 905 (87.949%) pass the proposed
  literal policy. Of 522 evaluable entities, 477 (91.379%) have at least one
  passing link and 45 have none. This is an existing-link projection, not a
  promise of rebuild output: identity resolution can change under a filtered
  profile.
- At 184 synchronized episodes: 577 entities, the same 75 duplicate-name groups
  spanning 218 nodes, 35 conflicting-type groups, 32 source-absent nodes, 133
  ungrounded links, and 18 entities without a domain-type label. The expanded
  audit separates those 133 links into 46 whose resolved entity name is absent
  from all canon and 87 whose resolved name appears elsewhere in canon. The
  latter class can include legitimate canonical-name/short-alias resolution and
  must not be treated as prompt contamination without source tracing.
- At 241 synchronized episodes after a quiet ten-minute interval: 696 entities,
  the same 75 duplicate-name groups spanning 226 nodes, the same 35
  conflicting-type groups, 37 source-absent nodes, 169 ungrounded links, and 17
  entities without a domain-type label. Of the ungrounded links, 51 resolve to
  names absent from all canon and 118 resolve to names present elsewhere in
  canon. Existing-link literal retention measured 89.351% and entity retention
  92.529%. The flat duplicate/conflicting group counts over this 57-episode
  interval continue to support sequential graph maintenance, but the eight
  additional nodes inside pre-existing duplicate groups and five additional
  source-absent nodes show that serialization alone is not a complete semantic
  repair.

The 18-episode delta added no duplicate-name or conflicting-type group, which is
consistent with serialization improving identity maintenance, but it still
added grounding and missing-type signals. More observations and a final snapshot
are required before deciding whether exact canonicalization is sufficient or a
second controlled rebuild is necessary.

A versioned remediation is implemented but intentionally inactive for the
current v1 operation:

- `literal_v1` filters only node-extraction responses, before entity resolution,
  to names literally present in the current episode under the same documented
  Unicode/case/whitespace normalization as the audit.
- It rejects malformed responses fail-closed and logs only proposed/accepted
  counts, never names or source text.
- On a verified policy-enabled write, its content-free proposed, accepted, and
  rejected entity counts flow into the existing append-only attempt-result
  fields atomically with graph verification. This required no migration and is
  inactive under the current `off` profile.
- A context-local episode binding keeps the filter safe even if unrelated
  provider calls overlap; relationship and attribute responses pass through
  unchanged.
- `GRAPH_ENTITY_GROUNDING_POLICY=off` preserves the exact deployed v1 sync
  fingerprint. Explicitly enabling `literal_v1` produces a different profile,
  preventing mixed provenance.
- The worker passes the profile-resolved policy into Graphiti rather than
  independently rereading configuration at the mutation boundary.

The current process remains on `off`; changing it mid-run would invalidate
provenance. The enabled policy must be benchmarked and, if accepted, used only in
a fresh backup-gated graph operation after the active rebuild becomes terminal.
The filter runs before identity resolution, while the semantic audit observes
the resolved entity name afterward. Therefore the current graph's 88.465%
existing-link projection is a conservative diagnostic, not an exact recall
estimate for `literal_v1`; enabled-profile proposal telemetry and a controlled
benchmark are required for that decision.

### Grounding-policy benchmark evidence

The fixed-corpus, non-persistent Graphiti benchmark now applies the
profile-selected entity-grounding policy at the same pre-resolution extraction
boundary as production. Its benchmark contract and fingerprint include the
policy ID, and its output aggregates only content-free proposal, acceptance,
rejection, recall, and relationship counts. The benchmark remains confirmation-
gated, provider-call-bounded, and performs no PostgreSQL or Neo4j writes.

The prior three-case v2 corpus is preserved. A new v3 corpus adds a bounded,
ASCII-normalized canon-derived Crystal Dwarf regression case plus 12 negative
expectations covering the three upstream prompt-example names conclusively
observed in the live graph. Any extracted forbidden entity now fails the
candidate even if positive recall remains high; extracted names and facts are
not emitted.

Live `qwen2.5:7b` evidence at concurrency one:

- On v2, the first `literal_v1` run retained 5/5 proposals and passed entity
  recall at 0.833, but failed relationship recall at 0.333. The `off` control
  produced the same entity recall and passed relationship recall at 0.667. A
  second `literal_v1` replicate also reached 0.667 relationship recall and
  passed. This shows material single-run relationship variance unrelated to
  entity rejection.
- On v3, both `literal_v1` and `off` produced 0.889 entity recall, zero matches
  across 12 forbidden checks, and 0.25 relationship recall. The enabled run
  recorded complete evidence and accepted all 13 proposals; this replicate did
  not elicit the intermittent prompt leak.
- The live graph remains conclusive evidence that the leak exists, but these
  small standalone runs do not yet prove its frequency or prove the enabled
  profile consistently meets the full extraction gate. `literal_v1` therefore
  remains implemented but not authorized for a rebuild.

These are extraction-quality defects under the immutable active profile, not
queue/audit drift. Changing prompts or filtering behavior mid-run would mix
semantics under one provenance fingerprint, so this run records the defect and
keeps synchronization provenance intact. Before this ingestion can be declared
complete, the final graph must receive a repeatable grounding, duplicate-name,
and type-consistency audit. Artifacts must then be dispositioned through an
auditable canonicalization step or a controlled new-profile rebuild rather than
a silent mid-run policy change.

### Concurrent Graphiti writer contract violation

Inspection of the installed upstream `Graphiti.add_episode` contract found that
episodes must be added sequentially and each call awaited before the next one.
The active rebuild had two independent writers. Atomic PostgreSQL claims kept
episode ownership safe, but they did not serialize Graphiti's cross-episode
entity-resolution and maintenance work. Concurrent writes are therefore a
plausible contributor to the high exact-name duplication and conflicting-type
counts above; they do not explain source-absent model hallucinations by
themselves.

Corrective action on 2026-08-10:

- Gracefully stopped non-owner worker 2, disabled its restart policy, and kept
  run owner `6608eb9d6211:1` as the sole Graphiti writer.
- The stopped worker exited with code zero and no restart. Its leased episode
  `02a41779-e794-45e5-989c-10e626020159` entered `retry_wait` with the sanitized
  durable failure `shutdown/worker_shutdown`.
- The immediate cross-store audit was clean and proved the interrupted write
  left no Neo4j node for a non-synchronized job and no null or duplicate
  episodic stable ID.
- Used the supported `retry-waiting` lifecycle command to make exactly that job
  eligible. The surviving writer reclaimed it, completed attempt 3, and
  independently verified it at `2026-08-09 22:58:50.669716+00`.
- The resulting queue returned to zero `retry_wait` and zero quarantined jobs;
  the intentional shutdown remains visible in append-only run telemetry.
- Hardened `GraphSyncRepository` so an active run can be rejoined and jobs can
  be claimed only by its recorded owner. A differently identified second writer
  now fails before claiming work. Focused unit tests and isolated PostgreSQL
  integration tests pass.
- Deliberately kept the active v1 sync fingerprint unchanged. Changing mounted
  profile identity mid-run would make a same-container restart and the finalizer
  reject the valid active operation. A future controlled operation must version
  the single-writer policy in its new profile instead.

This correctness correction roughly halves available extraction concurrency
and extends the ETA, but preserves one semantic writer for the rest of the
immutable-profile run.

### Operational observations that are not ingestion failures

- Detached one-off worker, watchdog, and finalizer containers show `unhealthy`
  because they inherit the API HTTP healthcheck but do not serve the API port.
  Process state, logs, durable heartbeat, leases, and audits are authoritative.
- Docker reports four older exited graph containers plus the intentionally
  stopped current worker 2 as orphans. They consume no CPU/GPU and are not
  interfering with the sole active writer.
- Docker warned that the `docker stop --time` spelling used for the graceful
  worker stop is deprecated in favor of `--timeout`; the stop itself completed
  successfully.
- `make retrieval-corpus-check-json` reports corpus drift because
  `benchmarks/episode_retrieval_v1.json` deliberately pins a manually judged
  historical 14-document/611-episode snapshot. It should be versioned through
  a new human-reviewed benchmark, not silently rewritten by ingestion.
- Durable claims are ordered by episode creation time. Changed older documents
  begin graph synchronization before newly inserted documents. Direct queue
  reprioritization was avoided because it would bypass lifecycle controls.
- An unfiltered fast-test warning audit exposed eight unrelated remaining
  warnings after the loader timestamp fix: one Pydantic-v2 deprecation inside
  the installed `graphiti_core` package, four pytest tests that return booleans
  instead of asserting/returning `None`, and three correction-agent calls using
  the deprecated constructor-level OpenAI-key compatibility path. These do not
  affect this ingestion run, but they should not remain hidden indefinitely by
  the repository-wide `--disable-warnings` setting.
- Recomputing all semantic chunks for the exact episode audit used roughly
  1,200–1,450% API-container CPU for about three minutes. That interval
  coincided with a short rolling Graphiti throughput dip from 2.8 to 1.2
  episodes/minute; causality is not proven, but full recomputation should be
  treated as a potentially contending operation during local model ingestion.
- A later fully quiet ten-minute window fell to 1.3 verified episodes/minute
  without any failure or infrastructure drift. Its 12 completed attempts
  averaged 46.498 seconds (p50 49.374, p95 65.838, maximum 70.780) and 21
  provider calls, with one complex attempt reaching 40 calls. GPU utilization
  was 91% at 86 C and the active lease remained valid. The slowdown is therefore
  consistent with variable episode/extraction complexity, not a stalled worker;
  short-window ETA should remain advisory.
- The first read-only Neo4j entity-coverage query used a `CASE` aggregate form
  rejected by the deployed Cypher parser. It made no mutation; simpler predicate
  queries completed the same audit successfully.
- The first read-only PostgreSQL recovery-row query referenced the nonexistent
  legacy-style column `attempt_count`; the durable column is
  `job_attempt_count`. The corrected query verified the intended row and neither
  query mutated state.
- Direct host `pytest` cannot import the installed container-only
  `graphiti_core` dependency. The dependency-complete API-container test path is
  authoritative; all new tests pass there.
- The API runtime image does not install the Ruff development module, so an
  attempted in-container `python -m ruff` check failed before examining files.
  The checked-in source was unchanged; host-toolchain Ruff format and lint then
  passed, and tests remained authoritative inside the dependency-complete API
  container.
- A read-only catalog audit initially queried the nonexistent
  `embedding_index_states.active_profile_fingerprint` column; the deployed
  column is `profile_fingerprint`. PostgreSQL stopped that statement without
  mutation. The corrected query proved the episode space active and both legacy
  384-dimensional spaces explicitly retired.
- Initial direct `cypher-shell` diagnostics found that the Neo4j image does not
  place the binary on `PATH` and exposes bootstrap credentials through
  `NEO4J_AUTH`, not `NEO4J_USER`/`NEO4J_PASSWORD`. Retrying with the absolute
  binary path and in-container credential parsing succeeded without printing
  credentials.
- The first attempt to inspect the installed versioned prompt treated its
  `VersionWrapper` as a plain function and raised a read-only `TypeError`.
  Inspecting the wrapper's `.func` target succeeded and exposed the prompt-leak
  examples above; no runtime state was changed.
- The current rebuild was prepared against the original verified 1,185-episode
  backup and then safely inherited 1,245 newly created jobs. Its lifecycle has
  no terminal abort/supersede transition, while a new 2,430-episode rebuild
  correctly requires a fresh matching backup. The checked-in migration workflow
  also rejects applying uncommitted migrations. This run will not bypass either
  guard merely to clear the partial graph early.
- The first focused test after adding the fourth v3 benchmark case retained the
  old three-case aggregate expectation (`4` proposed edges instead of `5`). It
  failed without provider or store access, was corrected to the exact new
  aggregate, and the complete focused suite then passed.

## Completed ingestion layers

### PostgreSQL and episodes

- All 26 source documents are present and canonical.
- Source paths and file hashes match exactly.
- Episode creation processed the ten new and seven changed documents without
  failure.
- Stored episodes: 2,430.
- Exact expected chunks: 2,429, with zero missing chunks and the one documented
  redundant current-content duplicate above.
- Empty episode rows: zero.
- Invalid episode indexes: zero.

### Embeddings, vector, and full-text retrieval

- Regenerated 1,809 embeddings for new or changed episodes in 57 successful
  batches.
- Active vector space: `episodes.embedding`, 768 dimensions, cosine distance.
- Embedded rows: 2,430/2,430; missing rows: zero; wrong dimensions: zero.
- HNSW index `idx_episodes_embedding` is ready and valid.
- Legacy 384-dimensional chunk/query spaces are empty and marked retired.
- A schema-wide follow-up found no overlooked canon-derived legacy data:
  `chunks`, its `canonical_content` view, `entity_mentions`,
  `validation_results`, `search_queries`, and all embedding-shadow run/batch/
  item/space tables contain zero rows. Runtime retrieval uses `episodes`; the
  legacy chunk and query indexes remain catalogued only as retired spaces.
- `lore_documents.search_vector` coverage is 26/26 with its GIN index present.
- Full-text smoke tests rank the new Ashenport Road, Feyveil, and Three Embers
  files first for their identifying queries.
- Hybrid/vector RAG for “What lies along the Ashenport Road?” returned all five
  leading chunks from the new Ashenport document.
- Once a changed document was graph-synced, a live query for the Crystal Dwarves
  returned five chunks, seven graph entities, and fifteen typed relationships,
  proving PostgreSQL vector search through focused Neo4j expansion end to end.

## Durable Graphiti run

- Active run: `5d22e3d6-9131-4b63-a9d7-697b881da492`.
- One sequential writer is running against local Ollama `qwen2.5:7b`. Ollama
  parallelism remains capped at two for the 8,151 MiB RTX 5070 Laptop GPU, but a
  second Graphiti writer is no longer permitted for this run.
- A watchdog handles drain/finalization transitions.
- An audit-gated finalizer retries until the rebuild reaches
  `awaiting_audit`, then accepts only a clean exact-profile reconciliation.
- Worker 1, the watchdog, and finalizer have bounded `on-failure:10` container
  restart policies. Worker 2 is intentionally exited with restart disabled.
  Worker startup recovers expired leases through the durable API before
  claiming more work.
- GPU observation: approximately 97% utilization, 6,317 MiB VRAM, 86 C; adding
  Graphiti writers would violate the upstream sequential-write contract even if
  provider calls could use both inference slots.
- Sanitized provider validation found no compatible faster configured route;
  the only Graphiti text candidate is the current local 7B model.
- Verified throughput before serialization fluctuated around 1.6–2.0
  episodes/minute. The first post-serialization checkpoint measured 1.4
  episodes/minute with a roughly 27.7-hour rolling ETA; this is a GPU-bound
  rebuild, not a stalled queue.

### Latest checkpoint — 2026-08-10 03:22

- Total jobs: 2,430.
- Synced: 256 (10.535%).
- Leased: 1.
- Pending: 2,173.
- Retry-wait: 0.
- Quarantined: 0.
- Expired leases: 0.
- Ten-minute rolling throughput: 1.3 verified episodes/minute; approximate ETA:
  100,339 seconds (about 27.9 hours). This short-window estimate fluctuates with
  episode complexity and is not a completion guarantee.
- Failure classes: `shutdown=1`, the intentional worker-2 stop documented
  above; the affected job has since synchronized successfully.
- Partial cross-store audit: clean at 256 PostgreSQL synced IDs and 256 distinct
  Neo4j stable IDs, with zero drift findings.
- Worker 1, watchdog, and finalizer are running with zero restarts. Worker 2 is
  intentionally exited with code zero, restart disabled, and zero restarts.

### Follow-up checkpoint — 2026-08-10 03:33

- Total jobs: 2,430.
- Synced: 276 (11.358%).
- Leased: 1.
- Pending: 2,153.
- Retry-wait: 0.
- Quarantined: 0.
- Expired leases: 0.
- Ten-minute rolling throughput: 1.9 verified episodes/minute (19 verified in
  the bounded window); approximate ETA: 68,022 seconds (about 18.9 hours).
  This remains a complexity-sensitive short-window estimate rather than a
  completion guarantee.
- Outcomes remain 276 primary successes and the one previously documented
  intentional `shutdown`; there are no authentication, authorization,
  cancellation, configuration, graph-validation, internal, malformed-JSON,
  output-limit, persistence, profile-mismatch, rate-limit,
  resource-exhaustion, schema-validation, transport, or verification failures.
- Partial cross-store audit: clean at 276 PostgreSQL synced IDs and exactly 276
  Neo4j Episodic nodes with 276 distinct stable IDs. Source, sync-profile, and
  embedding-profile metadata coverage is complete for every graph episode, and
  there are zero drift findings.
- Worker 1, watchdog, and finalizer are running with zero restarts. The inherited
  HTTP healthcheck still marks these non-HTTP processes unhealthy despite their
  live heartbeats, as documented above.

### Semantic-quality checkpoint — 2026-08-10 03:46

- Synced: 305/2,430 (12.551%); one leased, 2,124 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The latest ten-minute window verified 23 episodes (2.3/minute), with a
  short-window ETA of 55,435 seconds (about 15.4 hours). Worker 1, watchdog, and
  finalizer remain running with zero restarts.
- Exact-profile cross-store reconciliation remains clean: 305 durable synced
  PostgreSQL jobs correspond to exactly 305 Neo4j Episodic nodes and 305
  distinct stable IDs, with full source/sync/embedding-profile metadata coverage
  and zero drift findings.
- The repeatable semantic audit completed normally with its designed
  `review_required` result (CLI exit 1): 867 graph entities, zero missing names
  or UUIDs, zero duplicate UUID groups, zero episodes without entities, and zero
  missing episode/source links.
- Review signals at this snapshot: 75 duplicate normalized-name groups covering
  261 nodes, 35 conflicting-type name groups, 46 entity names absent from the
  complete canon, 15 typeless entities, and 217/2,007 entity/episode links
  without literal source grounding. Those links split into 68 for names absent
  from all canon and 149 for names present elsewhere in canon; the latter can be
  legitimate cross-episode identity resolution rather than hallucination.
- The conservative literal-policy projection is 89.188% link retention and
  93.080% entity retention. Relative to the 241-episode snapshot, duplicate and
  conflict group counts are stable at 75 and 35, while the affected duplicate
  nodes and review-link counts grow with graph coverage. Typeless entities fell
  from 17 to 15 as later resolution supplied types. This remains evidence for a
  controlled next-profile evaluation, not authorization to mutate the active
  off-policy rebuild.

### Progress checkpoint — 2026-08-10 03:57

- Synced: 327/2,430 (13.457%); one leased, 2,102 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 19 episodes (1.9/minute), with a
  complexity-sensitive ETA of 66,411 seconds (about 18.4 hours).
- No new attempt failure occurred. The sole run-level `shutdown` and provider
  cancellation remain the already documented intentional worker-2 stop.
- Exact-profile reconciliation is clean at 327 PostgreSQL synced jobs and
  exactly 327 Neo4j Episodic nodes/distinct stable IDs, with complete graph
  episode profile metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 04:09

- Synced: 351/2,430 (14.444%); one leased, 2,078 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The latest ten-minute window verified 21 episodes (2.1/minute), with a
  short-window ETA of 59,400 seconds (16.5 hours). There are no new run-attempt
  failures; worker 1, watchdog, and finalizer remain running with zero restarts.
- Exact-profile cross-store reconciliation is clean at 351 PostgreSQL synced
  jobs and exactly 351 Neo4j Episodic nodes/distinct stable IDs, with complete
  graph episode metadata and zero drift findings.
- A content-free (`sample_limit=0`) semantic audit completed normally with
  `review_required`: 962 graph entities, zero missing names/UUIDs, zero duplicate
  UUID groups, zero episodes without entities, and zero missing episode/source
  links.
- Review signals: 75 duplicate normalized-name groups covering 265 nodes, 35
  conflicting-type groups, 56 entity names absent from the complete canon, 32
  typeless entities, and 230/2,242 entity/episode links without literal source
  grounding. The ungrounded links split into 78 for names absent from all canon
  and 152 for names present elsewhere in canon.
- Relative to the 305-episode snapshot, duplicate/conflict group counts remain
  fixed, projected literal link retention improves from 89.188% to 89.741%, and
  projected entity retention changes from 93.080% to 92.723%. Typeless entities
  rise from 15 to 32 and canon-absent names from 46 to 56, so both remain explicit
  final-review items. No active-run graph mutation or profile change was made.

### Progress checkpoint — 2026-08-10 04:20

- Synced: 374/2,430 (15.391%); one leased, 2,055 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 22 episodes (2.2/minute), with a
  complexity-sensitive ETA of 56,073 seconds (about 15.6 hours).
- No new attempt/provider failure occurred. The only historic run-level
  `shutdown` and provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 374 PostgreSQL synced jobs and
  exactly 374 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 04:31

- Synced: 395/2,430 (16.255%); one leased, 2,034 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 19 episodes (1.9/minute), with a
  complexity-sensitive ETA of 64,264 seconds (about 17.9 hours).
- No new attempt/provider failure occurred; the only historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 395 PostgreSQL synced jobs and
  exactly 395 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 04:36

- Synced: 402/2,430 (16.543%); one leased, 2,027 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- Exact-profile reconciliation is clean at 402 PostgreSQL synced jobs and
  exactly 402 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,075 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 266 nodes, 36
  conflicting-type groups, 57 entity names absent from canon, 33 typeless
  entities, and 262/2,586 entity/episode links without literal source grounding.
  Those links split into 79 for names absent from all canon and 183 for names
  present elsewhere in canon.
- Relative to the 351-episode snapshot, duplicate groups remain fixed, conflict
  groups rise by one, canon-absent names and typeless entities each rise by one,
  projected link retention improves from 89.741% to 89.869%, and projected
  entity retention improves from 92.723% to 93.395%. These remain review and
  next-profile evaluation evidence; no mid-run graph mutation was made.

### Progress checkpoint — 2026-08-10 04:42

- Synced: 415/2,430 (17.078%); one leased, 2,014 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 18 episodes (1.8/minute), with a
  complexity-sensitive ETA of 67,167 seconds (about 18.7 hours).
- No new attempt/provider failure occurred. The one historic run shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 415 PostgreSQL synced jobs and
  exactly 415 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 04:54

- The ten-minute window closed at 440/2,430 synced (18.107%), with 23 verified
  episodes (2.3/minute) and a complexity-sensitive ETA of 51,914 seconds (about
  14.4 hours).
- One additional job committed before reconciliation. The authoritative audit
  snapshot is 441/2,430 synced (18.148%), one leased, 1,988 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 441 PostgreSQL synced jobs and
  exactly 441 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 04:58

- Synced: 451/2,430 (18.560%); one leased, 1,978 pending, and zero
  retry-waiting, quarantined, or expired jobs. Rolling throughput at the sample
  was 2.4/minute; its complexity-sensitive ETA was 49,475 seconds (about 13.7
  hours).
- Exact-profile reconciliation is clean at 451 PostgreSQL synced jobs and
  exactly 451 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,143 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 266 nodes, 36
  conflicting-type groups, 57 entity names absent from canon, 38 typeless
  entities, and 282/2,861 entity/episode links without literal source grounding.
  Those links split into 79 for names absent from all canon and 203 for names
  present elsewhere in canon.
- Relative to the 402-episode snapshot, duplicate/conflict groups and
  canon-absent names remain fixed; typeless entities rise by five. All 20 new
  ungrounded links involve names found elsewhere in canon, while projected link
  retention improves from 89.869% to 90.143% and projected entity retention
  improves from 93.395% to 93.876%. No mid-run graph mutation was made.

### Progress checkpoint — 2026-08-10 05:05

- The ten-minute window closed at 466/2,430 synced (19.177%), with 22 verified
  episodes (2.2/minute) and a complexity-sensitive ETA of 53,564 seconds (about
  14.9 hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 467/2,430 synced (19.218%), one leased, 1,962 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 467 PostgreSQL synced jobs and
  exactly 467 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 05:17

- The ten-minute window closed at 488/2,430 synced (20.082%), with 19 verified
  episodes (1.9/minute) and a complexity-sensitive ETA of 61,327 seconds (about
  17.0 hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 489/2,430 synced (20.123%), one leased, 1,940 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 489 PostgreSQL synced jobs and
  exactly 489 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 05:22

- The threshold status sample reached 500/2,430 synced (20.576%); one more job
  committed during the audits. The authoritative snapshot is 501/2,430 synced
  (20.617%), one leased, 1,928 pending, and zero retry-waiting, quarantined, or
  expired jobs. Rolling throughput at the threshold was 2.4/minute.
- Exact-profile reconciliation is clean at 501 PostgreSQL synced jobs and
  exactly 501 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,230 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 266 nodes, 36
  conflicting-type groups, 60 entity names absent from canon, 41 typeless
  entities, and 304/3,172 entity/episode links without literal source grounding.
  Those links split into 86 for names absent from all canon and 218 for names
  present elsewhere in canon.
- Relative to the 451-episode snapshot, duplicate/conflict groups remain fixed;
  canon-absent names and typeless entities each rise by three. Projected link
  retention improves from 90.143% to 90.416%, while projected entity retention
  changes from 93.876% to 93.740%. No mid-run graph mutation was made.

### Progress checkpoint — 2026-08-10 05:29

- The ten-minute window closed at 516/2,430 synced (21.235%), with 21 verified
  episodes (2.1/minute) and a complexity-sensitive ETA of 54,686 seconds (about
  15.2 hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 517/2,430 synced (21.276%), one leased, 1,912 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 517 PostgreSQL synced jobs and
  exactly 517 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 05:41

- The ten-minute window closed at 540/2,430 synced (22.222%), with 18 verified
  episodes (1.8/minute) and a complexity-sensitive ETA of 63,000 seconds (17.5
  hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 541/2,430 synced (22.263%), one leased, 1,888 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 541 PostgreSQL synced jobs and
  exactly 541 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 05:47

- Synced: 553/2,430 (22.757%); one leased, 1,876 pending, and zero
  retry-waiting, quarantined, or expired jobs. Rolling throughput at the sample
  was 2.2/minute; its complexity-sensitive ETA was 51,191 seconds (about 14.2
  hours).
- Exact-profile reconciliation is clean at 553 PostgreSQL synced jobs and
  exactly 553 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,329 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 269 nodes, 36
  conflicting-type groups, 61 entity names absent from canon, 43 typeless
  entities, and 320/3,486 entity/episode links without literal source grounding.
  Those links split into 87 for names absent from all canon and 233 for names
  present elsewhere in canon.
- Relative to the 501-episode snapshot, duplicate/conflict group counts remain
  fixed; canon-absent names rise by one and typeless entities by two. Projected
  link retention improves from 90.416% to 90.820%, and projected entity
  retention improves from 93.740% to 94.131%. No mid-run graph mutation was
  made.

### Progress checkpoint — 2026-08-10 05:53

- Synced: 565/2,430 (23.251%); one leased, 1,864 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 20 episodes (2.0/minute), with a
  complexity-sensitive ETA of 55,950 seconds (about 15.5 hours).
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 565 PostgreSQL synced jobs and
  exactly 565 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 06:05

- Synced: 587/2,430 (24.156%); one leased, 1,842 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 20 episodes (2.0/minute), with a
  complexity-sensitive ETA of 55,290 seconds (about 15.4 hours).
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 587 PostgreSQL synced jobs and
  exactly 587 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 06:13

- The threshold status sample reached 600/2,430 synced (24.691%); one more job
  committed during the audits. The authoritative snapshot is 601/2,430 synced
  (24.733%), one leased, 1,828 pending, and zero retry-waiting, quarantined, or
  expired jobs. Rolling throughput at the threshold was 1.8/minute.
- Exact-profile reconciliation is clean at 601 PostgreSQL synced jobs and
  exactly 601 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,447 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 272 nodes, 37
  conflicting-type groups, 70 entity names absent from canon, 60 typeless
  entities, and 350/3,789 entity/episode links without literal source grounding.
  Those links split into 98 for names absent from all canon and 252 for names
  present elsewhere in canon.
- Relative to the 553-episode snapshot, conflicts rise by one, canon-absent names
  by nine, and typeless entities by 17. Projected link retention changes from
  90.820% to 90.763%, while projected entity retention changes from 94.131% to
  93.780%.
- The typeless spike has a concrete source-role root cause rather than prompt
  leakage. Episode `e907183a-90b4-4923-a46a-6568c51eaba1`, index 236 of
  `canon/locations/the_thirteen_homelands.md`, synchronized at 06:00 local
  between the two audits and accounts for 13 of the 17 new typeless nodes. Its
  names include `runtime stable ID`, `card summary`, `media key`, and
  `mechanical-purpose summary`. The source explicitly contains these terms in
  its canon/runtime integration contract, so literal grounding would accept
  them even though they are not useful world entities. No mid-run graph mutation
  was made.

### Progress checkpoint — 2026-08-10 06:18

- The ten-minute window closed at 611/2,430 synced (25.144%), with 20 verified
  episodes (2.0/minute) and a complexity-sensitive ETA of 54,570 seconds (about
  15.2 hours).
- Two more jobs committed before reconciliation. The authoritative audit
  snapshot is 613/2,430 synced (25.226%), one leased, 1,816 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 613 PostgreSQL synced jobs and
  exactly 613 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 06:30

- The ten-minute window closed at 635/2,430 synced (26.132%), with 19 verified
  episodes (1.9/minute) and a complexity-sensitive ETA of 56,685 seconds (about
  15.7 hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 636/2,430 synced (26.173%), one leased, 1,793 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 636 PostgreSQL synced jobs and
  exactly 636 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 06:40

- The threshold status sample reached 652/2,430 synced; two more jobs committed
  during the audits. The authoritative snapshot is 654/2,430 synced (26.914%),
  one leased, 1,775 pending, and zero retry-waiting, quarantined, or expired
  jobs. Rolling throughput at the threshold was 2.0/minute.
- Exact-profile reconciliation is clean at 654 PostgreSQL synced jobs and
  exactly 654 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,548 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 289 nodes, 37
  conflicting-type groups, 76 entity names absent from canon, 63 typeless
  entities, and 373/4,093 entity/episode links without literal source grounding.
  Those links split into 104 for names absent from all canon and 269 for names
  present elsewhere in canon.
- Relative to the 601-episode snapshot, duplicate/conflict group counts remain
  fixed, canon-absent names rise by six, and typeless entities rise by three.
  Projected link retention improves from 90.763% to 90.887%, and projected
  entity retention improves from 93.780% to 93.863%. The large source-role spike
  did not repeat in this interval; no mid-run graph mutation was made.
- The associated ten-minute monitor subsequently closed at 656 synced with 19
  verified episodes (1.9/minute) and an ETA of 56,022 seconds. Two more jobs
  committed before its reconciliation: the authoritative follow-up is
  658/2,430 synced (27.078%), one leased, 1,771 pending, zero retry/quarantine/
  expiry rows, exact 658-ID cross-store parity, zero drift, and zero container
  restarts.

### Progress checkpoint — 2026-08-10 06:54

- The ten-minute window closed at 683/2,430 synced (28.107%), with 23 verified
  episodes (2.3/minute) and a complexity-sensitive ETA of 45,574 seconds (about
  12.7 hours).
- One more job committed before reconciliation. The authoritative audit snapshot
  is 684/2,430 synced (28.148%), one leased, 1,745 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 684 PostgreSQL synced jobs and
  exactly 684 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 07:02

- Synced: 700/2,430 (28.807%); one leased, 1,729 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- Exact-profile reconciliation is clean at 700 PostgreSQL synced jobs and
  exactly 700 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,603 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 307 nodes, 37
  conflicting-type groups, 80 entity names absent from canon, 63 typeless
  entities, and 388/4,316 entity/episode links without literal source grounding.
  Those links split into 111 for names absent from all canon and 277 for names
  present elsewhere in canon.
- Relative to the 654-episode snapshot, duplicate/conflict group counts and
  typeless entities remain fixed; canon-absent names rise by four. Projected link
  retention improves from 90.887% to 91.010%, while projected entity retention
  changes from 93.863% to 93.762%. The source-role spike did not recur, and no
  mid-run graph mutation was made.
- The associated ten-minute monitor subsequently closed at 707/2,430 synced
  (29.095%), one leased, 1,722 pending, and zero retry/quarantine/expiry rows. It
  verified 19 episodes (1.9/minute), estimated 54,411 seconds remaining, and
  reconciled exactly to 707 distinct Neo4j stable IDs with zero drift and zero
  container restarts.

### Progress checkpoint — 2026-08-10 07:19

- The ten-minute window closed at 728/2,430 synced (29.959%), with 18 verified
  episodes (1.8/minute) and a complexity-sensitive ETA of 56,734 seconds (about
  15.8 hours).
- Two more jobs committed before reconciliation. The authoritative audit
  snapshot is 730/2,430 synced (30.041%), one leased, 1,699 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 730 PostgreSQL synced jobs and
  exactly 730 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 07:31

- The ten-minute window closed at 745/2,430 synced (30.658%), with 13 verified
  episodes (1.3/minute) and a complexity-sensitive ETA of 77,770 seconds (about
  21.6 hours). This is the known slow end of episode-complexity variance, not a
  stall: the run heartbeat remained fresh and all failure-state counters were
  zero.
- One more job committed before reconciliation. The authoritative audit snapshot
  is 746/2,430 synced (30.700%), one leased, 1,683 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 746 PostgreSQL synced jobs and
  exactly 746 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 07:35

- Synced: 750/2,430 (30.864%); one leased, 1,679 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- Exact-profile reconciliation is clean at 750 PostgreSQL synced jobs and
  exactly 750 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings. Worker 1, watchdog, and finalizer remain
  running with zero restarts.
- The content-free semantic audit completed normally with `review_required`:
  1,744 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 318 nodes, 37
  conflicting-type groups, 94 entity names absent from canon, 63 typeless
  entities, and 429/4,667 entity/episode links without literal source grounding.
  Those links split into 130 for names absent from all canon and 299 for names
  present elsewhere in canon.
- Relative to the 700-episode snapshot, duplicate/conflict group counts and
  typeless entities remain fixed; canon-absent names rise by 14. Projected link
  retention changes from 91.010% to 90.808%, and projected entity retention
  changes from 93.762% to 93.578%. No source-role spike recurred and no mid-run
  graph mutation was made.

### Progress and latency checkpoint — 2026-08-10 07:43

- Synced: 759/2,430 (31.235%); one leased, 1,670 pending, and zero
  retry-waiting, quarantined, or expired jobs.
- The bounded ten-minute window verified 12 episodes (1.2/minute), with a
  complexity-sensitive ETA of 83,550 seconds (about 23.2 hours). This is the
  lowest observed short-window rate, so it received a follow-up latency audit.
- The 12 successful attempts averaged 50.626 seconds (p50 49.241, p95 65.925,
  maximum 68.465) and 19.167 provider calls (maximum 37). This is close to the
  earlier healthy complexity sample (46.498-second average, 65.838-second p95,
  21 average provider calls) and confirms workload variance rather than service
  degradation.
- No new attempt/provider failure occurred. The one historical shutdown and
  provider cancellation remain the intentional worker-2 stop.
- Exact-profile reconciliation is clean at 759 PostgreSQL synced jobs and
  exactly 759 Neo4j Episodic nodes/distinct stable IDs, with full graph episode
  metadata and zero drift findings.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 07:55

- The bounded ten-minute window closed at 784/2,430 synced (32.263%), with 23
  verified episodes (2.3/minute), one leased, 1,645 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 42,940
  seconds (about 11.9 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 785 PostgreSQL synced jobs and reconciled exactly to 785 Neo4j Episodic
  nodes/distinct stable IDs. Graph episode metadata coverage remains complete,
  and all drift categories remain empty.
- No new attempt or provider failure occurred. The only failure-class telemetry
  remains the historic intentional worker-2 shutdown and its associated
  provider cancellation.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 08:00

- The profile-pinned structural audit was clean at 802 PostgreSQL synced jobs
  and exactly 802 Neo4j Episodic nodes/distinct stable IDs, with complete graph
  metadata and zero drift findings.
- The content-free semantic audit completed normally with `review_required`:
  1,854 graph entities, zero missing names/UUIDs, zero duplicate UUID groups,
  zero episodes without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 331 nodes, 37
  conflicting-type groups, 94 entity names absent from canon, 68 typeless
  entities, and 445/5,005 entity/episode links without literal source
  grounding. Those links split into 132 for names absent from all canon and 313
  for names present elsewhere in canon.
- Relative to the 750-episode snapshot, duplicate/conflict group counts and
  canon-absent entity names remain fixed. Projected link retention improves
  from 90.808% to 91.109%, and projected entity retention improves from
  93.578% to 93.959%.
- All five newly observed typeless entities were traced read-only to episodes
  synchronized after the prior snapshot: `Current year` from the unresolved
  present-year entry in `timeline.md`; and `The Character's Compass`,
  `structured builder`, plus two editor-prompt questions from
  `the_characters_compass.md`. This is another content-role boundary case for
  improvement 15, not missing source data or graph-identity corruption. No
  mid-run graph mutation was made.

### Dedupe-response quality warning — 2026-08-10 08:03

- The worker log exposed one upstream Graphiti entity-dedupe response that
  supplied IDs 57-68 for a valid relative-ID range of 0-13 and omitted IDs
  1-13. The installed guard skipped every out-of-range resolution, so there was
  no invalid array access or queue failure; unresolved extracted nodes then
  followed Graphiti's documented fallback and were retained as new nodes.
- Durable correlation identifies attempt
  `8074b3ee-d4ac-4e22-a422-de53d1a36def`, episode index 12 of
  `canon/cultures/the_characters_compass.md`. It completed as
  `primary_success` after 26 provider calls, accepted 22 entities, and rejected
  all five proposed relationships through the normal relationship policy.
- A read-only exact-name check found each of the episode's 22 linked entities
  unique in the current graph. The malformed resolution can still create
  semantic duplicates with differently worded names; the 13 omitted
  resolutions also coincide numerically with the 13-node increase inside
  duplicate-name groups since the 750 snapshot, but the exact-name evidence
  does not establish causation. No live cleanup was attempted.

### Progress checkpoint — 2026-08-10 08:06

- The bounded ten-minute window closed at 819/2,430 synced (33.704%), with 31
  verified episodes (3.1/minute), one leased, 1,610 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 31,181
  seconds (about 8.7 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 820 PostgreSQL synced jobs and reconciled exactly to 820 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- No additional worker warning followed the 04:50:18 UTC malformed dedupe
  response, and no new durable attempt/provider failure occurred.
- Worker 1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 08:18

- The bounded ten-minute window closed at 846/2,430 synced (34.815%), with 23
  verified episodes (2.3/minute), one leased, 1,583 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 41,322
  seconds (about 11.5 hours).
- The profile-pinned cross-store audit reconciled exactly at 846 PostgreSQL
  synced jobs and 846 Neo4j Episodic nodes/distinct stable IDs, with complete
  metadata coverage and zero drift.
- No worker warning occurred in this window, no new durable attempt/provider
  failure appeared, and worker 1, watchdog, and finalizer remain running with
  zero restarts.

### Semantic-quality checkpoint — 2026-08-10 08:19

- Exact-profile reconciliation is clean at 851 PostgreSQL synced jobs and
  exactly 851 Neo4j Episodic nodes/distinct stable IDs, with complete metadata
  coverage and zero drift.
- The semantic audit completed normally with `review_required`: 1,929 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 332 nodes, 37
  conflicting-type groups, 99 entity names absent from canon, 82 typeless
  entities, and 458/5,234 entity/episode links without literal source
  grounding. Those links split into 141 for names absent from all canon and 317
  for names present elsewhere in canon. Projected link retention is 91.250%
  and projected entity retention is 93.935%.
- Relative to the 802 snapshot, duplicate/conflict group counts remain fixed,
  duplicate-group membership rises by one, canon-absent names rise by five,
  and the typeless total rises by 14. Fifteen new typeless nodes were created
  after that snapshot, all from `the_characters_compass.md`; they are primarily
  generator/UI labels and extracted prose fragments. The net +14 means one
  older typeless node left the category, but entities have no `updated_at` or
  label-change history, so the current graph cannot distinguish a later type
  assignment from a merge/removal.
- Four of the five new canon-absent names are paraphrased or malformed source
  fragments from the same document. The fifth is a new `AAN conference` node
  linked to episode index 81 despite that name appearing nowhere in canon,
  confirming another recurrence of the installed Graphiti few-shot prompt
  artifact. No live cleanup or profile mutation was made.

### Progress checkpoint — 2026-08-10 08:29

- The bounded ten-minute window closed at 874/2,430 synced (35.967%), with 24
  verified episodes (2.4/minute), one leased, 1,555 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 38,900
  seconds (about 10.8 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 875 PostgreSQL synced jobs and reconciled exactly to 875 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- Worker 1, watchdog, and finalizer remain running with zero restarts. One new
  upstream entity-summary warning occurred and is analyzed below; it did not
  register as a durable attempt/provider failure.

### Cross-stage entity mismatch — 2026-08-10 08:30

- Graphiti warned that the LLM returned a summary for unknown entity `Trader`.
  Durable correlation identifies attempt
  `8c1ce2a5-9057-40aa-a2bd-2e58eb2b1011`, episode index 112 of
  `canon/cultures/the_characters_compass.md`. It completed as
  `primary_success` after six provider calls, accepted two entities, and
  rejected its sole proposed relationship through the normal policy.
- The stored episode contains `Trader` and contains none of `AAN conference`,
  `Dr. Osei`, or `Dr. Amara Osei`. Its graph mentions nevertheless contain only
  a new `AAN conference` Location with an empty summary and a `Dr. Osei` Person;
  both names originate in the installed Graphiti few-shot example, not canon.
  The summary stage recognized the source concept `Trader`, but the installed
  maintenance code ignores summaries whose names do not match the extracted
  node set and does not retry or flag missing expected summaries.
- This is direct entity-recall loss plus prompt contamination hidden inside a
  structurally successful job. No live cleanup or mid-run policy change was
  made; the episode and attempt IDs preserve an exact regression fixture for a
  fresh controlled profile.

### Semantic-quality checkpoint — 2026-08-10 08:40

- Exact-profile reconciliation is clean at exactly 900 PostgreSQL synced jobs
  and 900 Neo4j Episodic nodes/distinct stable IDs, with complete graph episode
  metadata and zero drift.
- The semantic audit completed normally with `review_required`: 2,022 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 334 nodes, 37
  conflicting-type groups, 104 entity names absent from canon, 89 typeless
  entities, and 473/5,482 entity/episode links without literal source
  grounding. Those links split into 149 for names absent from all canon and 324
  for names present elsewhere in canon.
- Relative to the 851 snapshot, duplicate/conflict group counts remain fixed,
  duplicate-group membership rises by two, canon-absent names rise by five,
  and typeless entities rise by seven. Nine new typeless nodes entered the
  snapshot, all from `the_characters_compass.md`; two older typeless nodes
  therefore left the category through an unversioned merge/type transition.
  The five canon-absent additions comprise the two few-shot artifacts in
  episode 112 plus three extracted paraphrase fragments.
- Projected link retention improves from 91.250% to 91.372%, and projected
  entity retention improves from 93.935% to 94.016%. No live cleanup or
  mid-run profile mutation was made.

### Progress checkpoint — 2026-08-10 08:42

- The bounded ten-minute window closed at 904/2,430 synced (37.202%), with 23
  verified episodes (2.3/minute), one leased, 1,525 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 39,809
  seconds (about 11.1 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 905 PostgreSQL synced jobs and reconciled exactly to 905 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- No worker warning followed the episode-112 summary mismatch, no new durable
  attempt/provider failure occurred, and worker 1, watchdog, and finalizer
  remain running with zero restarts.

### Progress checkpoint — 2026-08-10 08:54

- The bounded ten-minute window closed at 926/2,430 synced (38.107%), with 19
  verified episodes (1.9/minute), one leased, 1,503 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 47,495
  seconds (about 13.2 hours).
- One complex in-flight episode temporarily held eight provider-call intents;
  the attempt completed normally, every intent received a terminal call record,
  and the ledger returned to its expected one-attempt/one-call in-flight shape.
- The immediate profile-pinned cross-store audit observed the next completion
  at 927 PostgreSQL synced jobs and reconciled exactly to 927 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- No worker warning or new durable attempt/provider failure occurred, and worker
  1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 09:05

- The bounded ten-minute window closed at 948/2,430 synced (39.012%), with 19
  verified episodes (1.9/minute), one leased, 1,481 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 46,800
  seconds (13.0 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 949 PostgreSQL synced jobs and reconciled exactly to 949 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- No worker warning or new durable attempt/provider failure occurred, and worker
  1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 09:07

- Exact-profile reconciliation is clean at 953 PostgreSQL synced jobs and
  exactly 953 Neo4j Episodic nodes/distinct stable IDs, with complete graph
  metadata and zero drift.
- The semantic audit completed normally with `review_required`: 2,159 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 334 nodes, 37
  conflicting-type groups, 108 entity names absent from canon, 100 typeless
  entities, and 487/5,858 entity/episode links without literal source
  grounding. Those links split into 157 for names absent from all canon and 330
  for names present elsewhere in canon.
- Relative to the 900 snapshot, duplicate/conflict group counts and membership
  remain fixed, canon-absent names rise by four, and typeless entities rise by
  11. All 11 new typeless nodes came from `the_characters_compass.md`. The four
  canon-absent additions are source-derived paraphrase/truncation signals,
  including `Luma`; no new known few-shot name appeared in this interval.
- Projected link retention improves from 91.372% to 91.687%, and projected
  entity retention improves from 94.016% to 94.210%. No live cleanup or
  mid-run profile mutation was made.

### Progress checkpoint — 2026-08-10 09:16

- The bounded ten-minute window closed at 973/2,430 synced (40.041%), with 22
  verified episodes (2.2/minute), one leased, 1,456 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 39,737
  seconds (about 11.0 hours).
- The immediate profile-pinned cross-store audit observed the next completion
  at 974 PostgreSQL synced jobs and reconciled exactly to 974 Neo4j Episodic
  nodes/distinct stable IDs, with complete metadata coverage and zero drift.
- No worker warning or new durable attempt/provider failure occurred, and worker
  1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 09:27

- Exact-profile reconciliation is clean at 1,002 PostgreSQL synced jobs and
  exactly 1,002 Neo4j Episodic nodes/distinct stable IDs, with complete graph
  metadata and zero drift.
- The semantic audit completed normally with `review_required`: 2,241 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 336 nodes, 37
  conflicting-type groups, 111 entity names absent from canon, 114 typeless
  entities, and 504/6,118 entity/episode links without literal source
  grounding. Those links split into 161 for names absent from all canon and 343
  for names present elsewhere in canon.
- Relative to the 953 snapshot, duplicate/conflict group counts remain fixed,
  duplicate-group membership rises by two, canon-absent names rise by three,
  and typeless entities rise by 14. Four typeless runtime/role entities were
  created by the then-in-flight final `the_characters_compass.md` episode before
  the prior audit but entered scope only when it verified; the other ten came
  from `languages_of_the_homelands.md`.
- The three canon-absent additions are two source-derived paraphrase signals
  (`Apology` and `bargain with an unspoken cost`) plus another
  `AAN conference` prompt artifact from episode index 193 of
  `the_characters_compass.md`. Its durable attempt is
  `a65df33f-4016-4630-8270-a991c6001c45`, recorded as `primary_success` after
  11 provider calls with nine accepted entities.
- Projected link retention improves from 91.687% to 91.762%, and projected
  entity retention improves from 94.210% to 94.244%. No live cleanup or
  mid-run profile mutation was made.

### Progress checkpoint — 2026-08-10 09:29

- The bounded ten-minute window closed at 1,003/2,430 synced (41.276%), with 27
  verified episodes (2.7/minute), one leased, 1,426 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 31,712
  seconds (about 8.8 hours).
- A subsequent profile-pinned cross-store audit, after the semantic attribution
  work above, reconciled exactly at 1,008 PostgreSQL synced jobs and 1,008
  Neo4j Episodic nodes/distinct stable IDs, with complete metadata coverage and
  zero drift.
- No worker warning or new durable attempt/provider failure occurred, and worker
  1, watchdog, and finalizer remain running with zero restarts.

### Progress checkpoint — 2026-08-10 09:42

- The bounded ten-minute window closed at 1,040/2,430 synced (42.798%), with 27
  verified episodes (2.7/minute), one leased, 1,389 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 30,889
  seconds (about 8.6 hours).
- The immediate profile-pinned cross-store audit observed four later
  completions and reconciled exactly at 1,044 PostgreSQL synced jobs and 1,044
  Neo4j Episodic nodes/distinct stable IDs, with complete metadata coverage and
  zero drift.
- No worker warning or new durable attempt/provider failure occurred, and worker
  1, watchdog, and finalizer remain running with zero restarts.

### Semantic-quality checkpoint — 2026-08-10 09:45

- Exact-profile reconciliation is clean at 1,054 PostgreSQL synced jobs and
  exactly 1,054 Neo4j Episodic nodes/distinct stable IDs, with complete graph
  metadata and zero drift.
- The semantic audit completed normally with `review_required`: 2,288 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links.
- Review signals: 75 duplicate normalized-name groups covering 336 nodes, 37
  conflicting-type groups, 116 entity names absent from canon, 121 typeless
  entities, and 519/6,333 entity/episode links without literal source
  grounding. Those links split into 170 for names absent from all canon and 349
  for names present elsewhere in canon.
- Relative to the 1,002 snapshot, duplicate/conflict group counts and membership
  remain fixed, canon-absent names rise by five, and typeless entities rise by
  seven. All additions in both categories came from
  `languages_of_the_homelands.md`: language labels, navigational expressions,
  or source-derived paraphrases. No known few-shot artifact appeared in this
  interval.
- Projected link retention improves from 91.762% to 91.805%; projected entity
  retention changes from 94.244% to 94.187%. No live cleanup or mid-run profile
  mutation was made.

### Progress checkpoint — 2026-08-10 09:54

- The bounded ten-minute window closed at 1,073/2,430 synced (44.156%), with 24
  verified episodes (2.4/minute), one leased, 1,356 pending, and zero
  retry-waiting, quarantined, or expired jobs. Its short-window ETA was 33,925
  seconds (about 9.4 hours).
- The immediate profile-pinned cross-store audit observed two later completions
  and reconciled exactly at 1,075 PostgreSQL synced jobs and 1,075 Neo4j
  Episodic nodes/distinct stable IDs, with complete metadata coverage and zero
  drift.
- The transient provider-call intents observed mid-window all received terminal
  records. No worker warning or new durable attempt/provider failure occurred,
  and worker 1, watchdog, and finalizer remain running with zero restarts.

### User-requested safe pause — 2026-08-10 10:00

- At the user's request, the quiet monitor was terminated, watchdog and
  finalizer were stopped, and active run
  `5d22e3d6-9131-4b63-a9d7-697b881da492` was moved from `running` to
  `draining`. This immediately stopped new claims while allowing the sole
  in-flight episode to reach durable completion.
- Paused durable state: 1,082/2,430 synced (44.527%), 1,348 pending, and zero
  leased, retry-waiting, quarantined, or expired jobs. All 1,083 current-run
  attempts have terminal results (1,082 primary successes plus the historic
  intentional shutdown), and all 13,795 provider-call intents have terminal
  call records.
- The profile-pinned cross-store audit reconciles exactly at 1,082 PostgreSQL
  synced jobs and 1,082 Neo4j Episodic nodes/distinct stable IDs, with complete
  metadata coverage and zero drift.
- The exact paused semantic snapshot remains structurally sound: 2,319 graph
  entities, zero missing names/UUIDs, zero duplicate UUID groups, zero episodes
  without entities, and zero missing episode/source links. Review signals are
  75 duplicate-name groups covering 343 nodes, 37 conflicting-type groups, 119
  canon-absent names, 121 typeless entities, and 528/6,445 ungrounded links;
  projected link/entity retention is 91.808%/94.135%.
- Rebuild operation `86c5a09e-8181-4dbe-a54a-1fe5700f19a4` remains durably
  `running`, not falsely completed or failed. The run remains resumable from
  `draining` through the readiness-gated `run-resume` transition, with the same
  sync/embedding profiles and verified backup.
- Worker, watchdog, and finalizer containers are all stopped. Watchdog and
  finalizer have zero restarts; their exit 137 statuses came from the explicit
  operator stop. The worker treated a draining run as process exit 2, causing
  its bounded `on-failure:10` policy to exhaust all ten restarts before the
  container was explicitly stopped. Those restarts claimed no jobs and created
  no attempt/provider failure records.

## Verification performed

- Canon boundary, loader, embedding invalidation, graph processor, worker, graph
  rebuild, and initialization suites: 43 focused tests passed.
- Latest complete network-isolated fast gate after adding the semantic audit,
  single-writer ownership checks, gated entity-grounding policy, and v3 negative
  benchmark: 460 passed, 7 service-dependent skips, 111 intentionally
  deselected tests, and zero
  failures in 9.79 seconds.
- Semantic audit unit suite: 9 passed. Grounding policy/profile/processor/worker
  focused suite: 29 passed. Owner-only claim and recovery behavior: 2 isolated
  PostgreSQL integration tests passed; the complete durable-state integration
  suite also passes all 11 tests.
- Grounding-aware benchmark, policy, and profile suite: 33 passed, including 19
  benchmark contracts for v2 compatibility, v3 negative matching, policy
  evidence aggregation, and content-free failure output.
- Post-UTC-fix canon-boundary suite: 13 passed; its only unfiltered warning is
  the separately documented installed-`graphiti_core` Pydantic deprecation.
- Immutable database migration ledger: current, eight applied migrations and
  zero pending migrations; both status and fail-closed check commands passed.
- PostgreSQL, Neo4j, Ollama, API, and UI Compose services all report healthy.
- Repeated exact source reconciliation: 26 filesystem files and 26 PostgreSQL
  documents, with zero missing/unexpected paths, body/hash/type mismatches,
  noncanonical rows, incomplete processing states, missing stable IDs, or
  missing document full-text vectors.
- Repeated production semantic-chunk reconciliation: 2,429 expected chunks,
  zero missing or mismatched expected chunks, 2,430 stored and embedded rows,
  zero wrong vector dimensions, empty episode texts, or invalid indexes. The
  sole redundant row is the already documented current-content duplicate in
  `races_of_lumia.md`.
- Partial graph-structure audit: all observed entity UUIDs were populated and
  distinct, all entity names were nonempty, all `MENTIONS` UUIDs/group IDs were
  populated and distinct, all `MENTIONS` and `RELATES_TO` endpoints had the
  expected labels, no entity lacked an episode mention, no episode lacked a
  mention, and every Neo4j index reported `ONLINE` at 100% population.
- GraphRAG endpoint fix verification: 18 focused tests passed, lint/format/diff
  checks passed, and the live response returned zero unknown relationship target
  names or types.
- Ruff lint: passed for every changed Python file.
- Ruff formatting check: passed.
- `git diff --check`: passed.
- Operational-readiness report: `ready`, zero warning or critical alerts.
- Relationship-quality telemetry: 100% evidence coverage for successful current
  run attempts, one unmixed vocabulary fingerprint, and no provider failures.
- Provider calls and attempts remain fully recorded in the append-only ledger.

## Objective improvement opportunities

1. **First-class incremental retirement.** Add a supported episode supersession
   or tombstone lifecycle that preserves attempt history while removing obsolete
   chunks from active retrieval and graph synchronization.
2. **Exact reconciliation in episode creation.** After rechunking a changed
   document, explicitly identify no-longer-produced episode indexes rather than
   relying only on UPSERT.
3. **Document-aware graph priority.** Add a schema-backed, audited priority field
   or operator command so newly added canon can be processed first without
   manipulating timestamps or bypassing the durable queue.
4. **Purpose-built worker healthchecks.** Give non-HTTP worker/finalizer
   containers heartbeat-based checks instead of inheriting the API healthcheck.
5. **Managed supervisor configuration.** Encode worker count, restart policy,
   watchdog, and finalizer in a checked-in Compose profile or service rather than
   constructing one-off operational containers.
6. **Loader preflight coverage.** Validate every inferred document type against
   the deployed enum and validate update-column compatibility before beginning a
   live batch, preventing partial ingestion before an error is discovered.
7. **Versioned retrieval benchmark refresh.** Create a new manually reviewed
   corpus version for the 26-document snapshot while preserving the 611-episode
   historical baseline.
8. **Graph extraction throughput benchmark.** Record representative call count,
   latency, thermals, and relationship quality for approved local model/profile
   candidates before a full rebuild; do not trade extraction fidelity for speed
   without benchmark evidence.
9. **Test-warning hygiene.** Convert script-style tests to proper assertions,
   migrate correction-agent fixtures to the shared provider configuration, and
   track the upstream `graphiti_core` Pydantic-v3 compatibility fix. Consider
   narrowing `--disable-warnings` once the known warning inventory is clean.
10. **Persisted chunk manifests.** Record the configured chunking profile and a
    content-addressed expected episode manifest when processing each document.
    This would make exact reconciliation cheap and deterministic without
    re-embedding every source sentence during a live graph run.
11. **Source-grounded entity policy and type consistency.** Require extracted
    entity names to be evidenced by the current episode (with explicit,
    versioned alias rules), report accepted/rejected entity counts, test known
    world/location identities such as Lumia, and detect same-name entities with
    conflicting types. The read-only audit and profile-gated `literal_v1` filter
    are implemented; remaining work is to benchmark the enabled profile, decide
    how to handle legitimate aliases and generic `Entity` labels, and evaluate
    it through a fresh controlled rebuild rather than this active v1 run. The
    enabled path now also persists proposal/accept/reject counts in the existing
    attempt ledger.
12. **Database-level single-writer enforcement.** Application repository joins
    and claims now reject a non-owner worker. Complete the defense with a durable
    run-scoped advisory lock or database attempt guard, encode one writer in the
    supervisor, and version that policy in the next sync profile. Provider-stage
    concurrency may be evaluated separately only if graph maintenance and entity
    resolution remain serialized.
13. **Auditable rebuild abort/supersede lifecycle.** Add an explicitly confirmed,
    terminal failure transition for a stopped incomplete rebuild, with a stable
    reason code and append-only event. This should permit a fresh backup-gated
    operation without rewriting or pretending to complete the failed one. It
    must ship through the normal committed migration workflow, not an ad-hoc
    production update.
14. **Replicated extraction-quality gates.** The three-case benchmark produced
    relationship recall of both 0.333 and 0.667 under the same immutable
    candidate/contract, and the four-case v3 runs both produced 0.25. Add
    deterministic seed support where the provider honors it, repeated trials,
    component-level entity/relationship gates, and distribution/confidence
    reporting so one stochastic relationship miss cannot approve or reject a
    graph profile. Keep the new forbidden-entity gate fail-closed on every
    replicate.
15. **Content-role-aware graph extraction.** Canon documents can legitimately
    contain runtime contracts, field names, migration guidance, and
    player-presentation requirements alongside world lore. Episode 236 of
    `the_thirteen_homelands.md` caused 13 grounded but typeless schema/presentation
    entities, proving literal source grounding alone cannot distinguish these
    roles. Add explicit versioned section/chunk roles and a graph-extraction
    inclusion policy that keeps implementation guidance retrievable while
    excluding it from world-entity extraction. Cover the boundary with negative
    benchmark cases and include the policy in the sync-profile fingerprint.
16. **Fail-closed entity-dedupe response completeness.** Treat missing,
    duplicate, or out-of-range entity resolution IDs as a bounded retriable
    quality failure instead of silently retaining unresolved nodes and
    recording `primary_success`. Persist malformed/missing resolution counts in
    the append-only attempt ledger, surface them in readiness and semantic
    reports, and add adversarial contract tests for shifted absolute IDs. If a
    no-duplicate fallback is ultimately allowed, record it explicitly as a
    degraded outcome so operators can distinguish ingestion completeness from
    entity-resolution quality.
17. **Persist semantic-audit snapshots and entity mutation provenance.** Store
    compact UUID-level finding sets for each audit checkpoint and record entity
    label/merge changes with timestamps. The current aggregate audit is
    repeatable, but a live graph can change a prior entity's type or identity
    without `updated_at` or an append-only event, preventing exact delta
    attribution after the fact. Snapshot fingerprints and transition events
    would make quality regressions, recoveries, and cleanup decisions fully
    auditable without storing source text in telemetry.
18. **Cross-stage entity consistency and recall gates.** Validate that summary
    response names are a complete subset of the nodes requested for summary,
    and treat unknown or missing names as a bounded retriable quality failure.
    Combine that check with source-grounding evidence so a job cannot report
    `primary_success` when every extracted node is absent from its source while
    a later stage identifies a grounded source concept that extraction missed.
    Persist stage-specific mismatch counts and add the episode-112 regression
    above to replicated extraction benchmarks.
19. **First-class pause semantics across worker and supervisor.** A worker that
    encounters a deliberately draining run should exit successfully or enter a
    documented idle state, not return exit 2 and trigger its entire bounded
    restart budget. Add an operator pause command that atomically coordinates
    run draining, active-lease completion, monitor/supervisor suspension, and
    container stop; add the inverse readiness-gated resume command. Give
    watchdog/finalizer shells prompt signal handling so an ordinary stop does
    not require SIGKILL/exit 137, and cover the complete pause/resume lifecycle
    in integration tests.

## Remaining completion gates

- Synchronize all 2,430 durable graph jobs with zero pending, leased, retry, or
  quarantined rows.
- Let the active run drain and stop, and let the rebuild finalizer record
  `completed`.
- Re-run the exact 26-file source path/hash audit.
- Re-run embedding preflight and require 2,430/2,430 valid 768-dimensional
  vectors plus a ready HNSW index.
- Require a clean final graph audit with 2,430 PostgreSQL episodes and exactly
  2,430 distinct Neo4j episodic stable IDs.
- Re-run live full-text, vector, and GraphRAG smoke tests against newly added
  canon.
- Capture final relationship-quality and operational-readiness reports.
- Run the repeatable semantic graph audit against the final snapshot, covering
  source/episode grounding signals, exact-name duplicates, and conflicting
  entity types; disposition detected artifacts through an auditable cleanup or
  controlled profile rebuild.
- Update this journal with final evidence and disposition of every open finding.
