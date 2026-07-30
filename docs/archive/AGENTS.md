# Repository Guidelines

## Project Structure & Module Organization
- `canon/` holds approved lore; `drafts/` and `meta/` capture in-flight worldbuilding and design notes that feed the pipelines.
- Primary code lives in `luminari-sage/`: `src/agents`, `src/api`, `src/graphiti`, and `src/pipeline` power the hybrid GraphRAG service; `scripts/` automates document loading, episode creation, and embedding sync; `schemas/` defines payload contracts.
- Docker images pull dependencies from `requirements-core.txt`; add new runtime libraries there so the container build includes them.
- Tests sit in `luminari-sage/tests/` and root-level `test_*.py`; UI prototypes and assets live under `luminari-sage/ui/` and `docs/` summarizes operational playbooks.

## Build, Test, and Development Commands
- Start the local stack from `luminari-sage/`: `docker-compose up --build` brings up API, Postgres, Neo4j, and supporting services.
- Run an end-to-end lore ingestion pass once containers are healthy: `make semantic-pipeline` (or `make pipeline-canon` / `pipeline-draft` for focused runs).
- Use `make status` or `make logs` for runtime visibility, and `make semantic-reset` before reprocessing large canon changes.

## Coding Style & Naming Conventions
- Target Python 3.11, four-space indentation, and type-hinted public functions; keep agent prompts and schema enums in `SCREAMING_SNAKE_CASE`.
- Format and lint before committing: `black src tests` and `ruff check src scripts` (CI expects both to pass).
- Modules, files, and fixtures stay snake_case; classes and Pydantic models are PascalCase; environment variables follow UPPER_SNAKE and are defined in `.env` files ignored by git.

## Testing Guidelines
- `pytest` (configured via `pytest.ini`) is the default test runner; markers include `unit`, `integration`, `data_dependent`, and `slow`—scope your runs with `pytest -m "unit and not slow"` during rapid iteration.
- Mirror existing conversation coverage when adding agents or pipelines by extending suites such as `tests/test_multi_quest.py` and top-level scenario tests.
- Integration suites require the docker stack plus seeded data; use the document loaders in `scripts/` before running `pytest -m integration`.

## Commit & Pull Request Guidelines
- Follow the conventional commit pattern visible in history (`fix:`, `feat:`, `chore:`); keep scopes clear and messages imperative.
- Each PR should summarize behavior changes, document required configuration, and include links to relevant lore files or tickets.
- Attach evidence of validation (command logs, `pytest` output, or screenshots for UI) and note any remaining risks; request review once lint, tests, and pipelines pass locally.

## Security & Configuration Notes
- Secrets stay in environment files and local `.env` overrides—never commit credentials embedded in Postman collections or `mcp-client-config.json`.
- When sharing datasets, scrub `canon/` exports of unpublished material and coordinate schema updates with the Graphiti configuration in `luminari-sage/config/`.

## Debugging Patterns & Reminders
- **Run code inside containers.** Use `docker exec -it luminari-sage-api-1 bash -lc "python …"` (or the relevant service) so you inherit the same dependencies, API keys, and env vars as production. Host-level Python often lacks these.
- **Tail container logs first.** `docker logs --tail 200 luminari-sage-api-1` surfaces syntax errors (e.g., import failures) and is faster than reproducing via the UI.
- **Check recent deployments.** If a push introduced issues, confirm the latest commit hash on `main` and watch the API container restart before retesting.
- **Prefer existing tooling.** Reach for `make status`, `docker-compose logs`, or the focused LangChain tools (`search_lore`, `answer_lore_question`) when reproducing lore issues.
