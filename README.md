# rag-platform

A minimal RAG (Retrieval-Augmented Generation) learning project demonstrating an end-to-end pipeline:

```
User Question
  → [Lexicon Gate]  AhoCorasick: sensitive word blocking / direct QA / synonym expansion
  → [Hybrid Search] BM25 (keyword) + Vector (semantic), weighted fusion for Top-K
  → [Generation]    OpenAI-compatible LLM, answers solely from retrieved passages
```

> 📐 Full architecture and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).  
> 中文文档见 [README.zh](README.zh).

## Tech Stack

- **Storage**: PostgreSQL + pgvector, vector search via `cosine_distance` SQL (no full-load into memory).
- **Embedding**: Ollama out-of-process HTTP encoding (lightweight, only `requests`), falls back to sentence-transformers in-process when Ollama is unavailable.
- **Lexicon Gate**: AhoCorasick for sensitive word blocking / direct QA / synonym expansion. Cached in Redis with dual-timestamp polling rebuild; falls back to in-memory mode without Redis. Source: `data/lexicon.json`.
- **Retrieval**: Hybrid — vector recall via pgvector `cosine_distance` SQL fused with BM25 scores using min-max normalization + weighted combination.
- **Generation**: OpenAI-compatible LLM constrained to answer solely from retrieved passages with "don't know" guardrails.
- **Audit**: Record status flag `active` / `disabled`.

## Directory Structure

```
rag-platform/
├── app/
│   ├── main.py        # FastAPI routes: /ingest /chat /search /lexicon/reload
│   ├── config.py      # Env-based settings
│   ├── models.py      # SQLModel tables: Document / Chunk / QAPair
│   ├── db.py          # PostgreSQL(+pgvector) engine; init_db creates vector extension
│   ├── embed/         # Dual backend (Ollama primary / sentence-transformers fallback)
│   │   ├── __init__.py
│   │   ├── base.py    # EmbedBackend abstract base
│   │   ├── core.py    # Backend selection + dimension guard + public API
│   │   ├── ollama_backend.py   # Ollama HTTP backend (primary)
│   │   └── st_backend.py       # sentence-transformers backend (fallback)
│   ├── bm25.py        # Okapi BM25 from scratch
│   ├── lexicon.py     # AhoCorasick lexicon gate (Redis-cached, fallback to memory)
│   ├── retriever.py   # pgvector + BM25 hybrid retrieval
│   ├── generator.py   # OpenAI-compatible LLM generation
│   ├── splitter.py    # Text chunking
│   └── schemas.py     # Request/response models
├── frontend/          # Vite + Vue 3 SPA (chat / ingest / search panels)
│   ├── package.json
│   ├── vite.config.js # /api proxy to :8000
│   ├── index.html
│   └── src/
│       ├── App.vue
│       ├── api.js
│       ├── style.css
│       └── components/
│           ├── ChatPanel.vue
│           ├── IngestPanel.vue
│           └── SearchPanel.vue
├── data/
│   └── lexicon.json   # Sample lexicon (sensitive words / synonyms / direct QA)
├── pyproject.toml     # uv dependency manifest (source of truth)
├── uv.lock
├── docker-compose.yml # PostgreSQL(+pgvector) + Redis
├── .env.example
├── Makefile           # Unified entry: uv backend + npm frontend + docker infra
```

> `requirements.txt` is kept as a pip fallback; `pyproject.toml` is the source of truth.

## Quick Start (uv)

```bash
# 0. Start local infrastructure (PostgreSQL+pgvector / Redis)
make infra-up

# 1. Create .venv and install dependencies
uv sync

# 2. Configure (real LLM key required — no mock provided)
cp .env.example .env
#    Edit .env: OPENAI_API_KEY=sk-xxx, optionally change OPENAI_BASE_URL

# 3. Start the backend
uv run uvicorn app.main:app --reload --port 8000

# 4. Init database (auto-creates tables + pgvector extension on first /health call)
curl http://localhost:8000/health
```

> pip alternative: `python -m venv .venv && pip install -r requirements.txt`  
> Stop infra: `make infra-down` (volumes preserved); Logs: `make infra-logs`

## Frontend (Vite + Vue)

Three panels: Chat / Ingest / Search. The Vite dev server proxies `/api/*` to the backend.

### One-Click Start (recommended)

```bash
make install-frontend        # first-time dependency install (cd frontend && npm install)
make up                      # launches backend (:8000) + frontend (:5173) in background
#    Open http://localhost:5173
#    Frontend proxies /api/* to :8000 — no CORS hassle

make status                  # check running status
make down                    # stop both processes
make restart                 # down + up
```

### Foreground (for debugging)

```bash
make run                     # :8000 hot-reload (Ctrl+C to exit)
make dev                     # :5173 dev server (Ctrl+C to exit)
```

Build static assets (can be hosted independently):

```bash
make build                   # output: frontend/dist
make preview                 # preview production build
```

## Try It

```bash
# Ingest a document
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"title":"Refund Policy","content":"We support 7-day no-reason returns. Refunds go back to your original payment method. Business hours: 09:00-22:00 daily."}'

# Direct QA (lexicon hit, no LLM call)
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"business hours"}'

# Sensitive word blocking
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"Tell me about violence"}'

# LLM-based answer
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"How long for refund to arrive?"}'

# Debug: search only
curl "http://localhost:8000/search?q=refund"
```

## Tests

Tests live in `tests/`, run with `uv run pytest`. 13 cases total:

- **Unit tests** (`tests/test_unit.py`, 7 cases): BM25 ranking, lexicon gate (blocking / direct QA / synonym expansion), text splitting, min-max normalization. **Zero infrastructure required** — runs in CI / sandbox.
- **Integration tests** (`tests/test_integration.py`, 6 cases, marked `@pytest.mark.integration`): full chain against real PostgreSQL+pgvector (`/health → /ingest → /search → /chat → /lexicon/reload`). **Auto-skip** without infra.

```bash
make test          # all: unit always runs + integration (skipped if no PG)
make test-unit     # unit only (CI / no PG)
```

Key points:
- Integration tests use an **isolated `rag_test` database** (fixture connects to `postgres` maintenance DB and `CREATE DATABASE` on demand) — never touches the dev `rag` database.
- Integration tests inject a stub embedding via `monkeypatch` — no dependency on Ollama / sentence-transformers.

## Code Quality (lint / format)

`make lint` lints both backend and frontend — currently all green, zero warnings:

```bash
make lint          # ruff (backend) + eslint (frontend), exit code 0
make lint-fix      # auto-fix (ruff --fix + eslint --fix)
make fmt           # ruff format (backend only)
```

- **Backend**: ruff on `app tests` (line-length=100).
- **Frontend**: ESLint 9 flat config with `flat/essential` — catches real errors only, no style noise.

## Learning Path

1. Read the architecture dataflow diagram and Tech Stack section above.
2. Run the 4 curl examples above, observe the `source` field (blocked / direct_qa / llm).
3. Edit `data/lexicon.json` then call `POST /lexicon/reload` to hot-reload.
4. Next steps: add streaming output; swap lexicon source from JSON to a database table.
