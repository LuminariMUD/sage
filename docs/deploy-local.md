# Local development deployment

This is the durable setup and recovery guide for running the complete Sage
stack on a developer workstation. It intentionally contains no secret values.
Keep the real `.env` mode `0600` and never commit it.

## Current checkpoint

- Date: 2026-08-06
- Work branch: `codex/local-dev-stack`
- Repository: <https://github.com/LuminariMUD/sage>
- All five long-running services are currently healthy: PostgreSQL, Neo4j,
  Ollama, API/MCP, and the static chat UI.
- PostgreSQL contains 14 lore documents and 611 episodes. All 611 episodes have
  768-dimensional embeddings.
- The active incremental Graphiti pass was last audited at 51 linked episodes
  and 560 pending. Neo4j had exactly 51 episode nodes, 51 populated stable IDs,
  and 51 distinct stable IDs. One 3B extraction
  (`50480869-ff15-41b2-b1ae-a4f1a81b88c8`) exhausted structured-output retries;
  it remains unsynced and has no orphan Neo4j episode, ready for a later 7B
  retry. A live post-hardening extraction completed in about 29 seconds with
  exactly one matching stable ID in each store.
- The development image builds successfully. The fast deterministic suite is
  green: 62 passed, 5 service-dependent skips, and 99 live/slow tests excluded.
- Black and Ruff checks pass across all 130 Python files in `src` and `tests`.
- An authenticated desktop/mobile browser check now passes through the real
  LangChain/Ollama chat path: message creation and the SSE stream both return
  `200`, an answer renders, and there are no console/page errors, leaked API
  keys, or horizontal overflow.

Resume work from this checkpoint by running:

```bash
git switch codex/local-dev-stack
docker compose ps --all
make status
```

## Local architecture

| Role | Local component |
| --- | --- |
| REST API | FastAPI + Uvicorn on `127.0.0.1:8003` |
| MCP server | FastAPI/Uvicorn process on `127.0.0.1:8004` |
| Developer UI | Static chat UI on `127.0.0.1:8080` |
| Chat, creative, tools | Ollama `qwen2.5:7b` |
| Graphiti extraction | Ollama `qwen2.5:3b` |
| Embeddings | Ollama `nomic-embed-text` (768 dimensions) |
| Vector/document data | PostgreSQL 18 + pgvector |
| Knowledge graph | Neo4j 2026.06 Community + Graphiti |

The local profile does not require a cloud LLM. The 3B extraction model was
selected after a live benchmark on the workstation's 8 GB GPU: it produced
coherent entities and facts in roughly 16 seconds after model load, while the
7B model generally took around a minute per episode. Chat and creative work
remain on 7B for better response quality.

Ollama is configured with a 12,288-token context, two parallel slots, and at
most two resident models. Graphiti responses are capped at 4,096 output tokens
and 25 entities/relationships per episode to prevent runaway local generation.

## Prerequisites

- Docker Engine with Compose v2
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

Keep `LLM_PROVIDER=ollama`, `GRAPHITI_PROVIDER=ollama`, and
`USE_LOCAL_EMBEDDINGS=true` for the fully local profile. An OpenAI key is not
needed for the intended local execution path.

Start the complete development stack:

```bash
make dev
```

`make dev` builds the development API image, starts the databases and Ollama,
pulls the three required models through the one-shot `ollama-init` service, and
starts API/MCP and UI only after their dependencies are ready. Model pulls are
idempotent on later starts.

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
make sync-to-graphiti
```

Or run/resume the complete sequence:

```bash
make semantic-pipeline
make resume
```

Monitor progress without changing data:

```bash
make embedding-status
make graphiti-status
docker compose exec -T api \
  python src/scripts/sync_episodes_to_graphiti.py --status
```

Graph sync defaults to incremental mode, marks PostgreSQL rows complete only
after proving exactly one Neo4j episode has both the expected stable UUID and
source description, and skips a failed episode for the remainder of one
invocation so a bad row cannot cause an infinite retry loop. A pre-existing
exact link is resumed without repeating LLM extraction; any missing or ambiguous
link fails closed. Bulk mode works in bounded batches, but should normally be
reserved for an empty graph:

```bash
docker compose exec -T api python \
  src/scripts/sync_episodes_to_graphiti.py --bulk --batch-size 5
```

## Safety and recovery

- `make down` preserves data.
- `make clean-logs` truncates only Sage application log files; it never prunes
  Docker volumes.
- `make clear-graph`, `make clear-all`, and reset targets intentionally mutate
  stored data. Read their prompts/output before confirming them.
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

1. Let the active incremental pass finish, retry any quarantined 3B rows with
   the 7B tool model, and verify all 611 PostgreSQL UUIDs are linked exactly
   once.
2. Perform a clean preserved-volume restart audit, rerun all gates, update this
   runbook with the final counts, and publish the final checkpoint.
