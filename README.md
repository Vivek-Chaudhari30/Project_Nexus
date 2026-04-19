# Project Nexus

Multi-agent orchestration platform that decomposes natural-language goals into a
DAG of sub-tasks, routes each to the best LLM, executes code in an isolated
sandbox, verifies results, and reflects until quality ≥ 0.85.

> Demo: _[video link placeholder]_

---

## Architecture

```
User Goal
    │
    ▼
┌─────────┐   task_plan   ┌────────────┐   research   ┌──────────┐
│ Planner │──────────────▶│ Researcher │─────────────▶│ Executor │
└─────────┘               └────────────┘               └──────────┘
    ▲                                                        │
    │ replan (quality < 0.85)                      code_output│
    │                                                        ▼
┌──────────┐  quality_score  ┌──────────┐  verified_output  │
│Reflector │◀────────────────│ Verifier │◀──────────────────┘
└──────────┘                 └──────────┘
    │
    │ quality ≥ 0.85 (or 3 iterations)
    ▼
 Output

Infrastructure:
  Postgres ── durable sessions, checkpointer, audit log
  Redis    ── embedding cache (7-day TTL), loop detection, rate limits
  Pinecone ── semantic memory (per-user namespace, quality ≥ 0.70)
  Sandbox  ── gRPC + iptables-isolated Python execution (non-root, read-only FS)
  nginx    ── reverse proxy: /api → backend, /ws → backend WS, / → React SPA
```

**Model routing:**
| Agent      | Model                  | Reason              |
|------------|------------------------|---------------------|
| Planner    | Claude Sonnet 4        | Complex reasoning   |
| Researcher | Gemini 2.5 Flash       | Fast extraction     |
| Executor   | GPT-4o                 | Code generation     |
| Verifier   | Claude Sonnet 4        | Fact-checking       |
| Reflector  | Claude Sonnet 4        | Self-critique       |

---

## Prerequisites

| Tool | Version |
|------|---------|
| Docker | ≥ 24 |
| Docker Compose | ≥ 2.20 |
| GNU Make | any |
| Python | 3.12 (for scripts only) |

API keys required: Anthropic, OpenAI, Google AI, Tavily, Pinecone.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-org>/project-nexus.git
cd project-nexus

# 2. Configure
cp .env.example .env
#  Fill in: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY,
#           TAVILY_API_KEY, PINECONE_API_KEY, JWT_SECRET,
#           POSTGRES_PASSWORD (min 32 chars)

# 3. Launch all services
make up

# 4. Apply database migrations
make migrate

# 5. Open the UI
open http://localhost
```

---

## Make Commands

```bash
make up          # docker compose up --build (all services)
make down        # docker compose down
make migrate     # apply SQL migrations in backend/db/migrations/
make test        # pytest backend/tests + vitest frontend/src
make lint        # ruff + mypy (backend) + eslint (frontend)
make eval        # run scripts/eval_accuracy.py against http://localhost
```

---

## Running Tests

```bash
# Backend (unit + integration — no containers required)
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm test
```

Integration tests mock Postgres and Redis at the dependency layer, so no
containers are needed. Graph integration tests mock all five agent `.run()`
methods with deterministic canned responses.

---

## Accuracy Evaluation

```bash
# Against a running stack
python scripts/eval_accuracy.py --base-url http://localhost

# Custom credentials
python scripts/eval_accuracy.py --email you@example.com --password yourpassword123
```

Six eval cases cover: research, code generation, analysis, writing, multi-step
pipelines, and cross-session memory recall. Exit code 0 = all pass (quality ≥ 0.85).

---

## Development Reset

```bash
# Wipe Pinecone vectors + Postgres session data (dev only)
python scripts/reset_memory.py

# Non-interactive
python scripts/reset_memory.py --yes

# Partial
python scripts/reset_memory.py --skip-pinecone   # Postgres only
python scripts/reset_memory.py --skip-postgres   # Pinecone only
```

---

## Project Layout

```
backend/
  agents/        Planner, Researcher, Executor, Verifier, Reflector
  api/           FastAPI routes, auth, deps, WebSocket handler
  core/          graph, state, memory, context, checkpointer, loop_detector
  db/            postgres, redis, pinecone clients + migrations
  prompts/       agent system prompts (markdown)
  tools/         web_search, code_executor, …
frontend/
  src/
    components/  GoalInput, PipelineVisualizer, StreamLog, QualityMeter, …
    hooks/       useNexusStream, useSessions
    pages/       Home, Session
    lib/         api.ts, types.ts
sandbox/
  server.py      gRPC execution server (non-root, iptables isolation)
infra/
  docker-compose.yml
  nginx/nginx.conf
  postgres/init.sql
scripts/
  eval_accuracy.py
  reset_memory.py
docs/
  ADRs/          Architecture Decision Records
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_USER` | yes | Postgres username |
| `POSTGRES_PASSWORD` | yes | Postgres password (≥ 32 chars) |
| `POSTGRES_DB` | yes | Postgres database name |
| `ANTHROPIC_API_KEY` | yes | Claude API key |
| `OPENAI_API_KEY` | yes | OpenAI API key |
| `GOOGLE_API_KEY` | yes | Google AI API key |
| `TAVILY_API_KEY` | yes | Tavily web search key |
| `PINECONE_API_KEY` | yes | Pinecone API key |
| `PINECONE_INDEX` | no | Index name (default: `nexus-memory`) |
| `JWT_SECRET` | yes | HS256 signing secret (`openssl rand -hex 32`) |
| `LOG_LEVEL` | no | `INFO` (default) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | OpenTelemetry collector endpoint |

---

## Key Design Rules

- **Quality gate**: output ships only when quality ≥ 0.85 or 3 iterations exhausted.
- **Max iterations**: hard cap of 3; sets `disclaimer="max_iterations_reached"` on exit.
- **Memory writes**: Pinecone receives a vector only if quality ≥ 0.70.
- **Sandbox**: all LLM-generated code executes in an isolated container with a
  read-only filesystem, 128 MB `/tmp` tmpfs, `NET_ADMIN` for iptables rules,
  and `no-new-privileges` secopt.
- **Checkpointer**: every agent transition writes to Postgres. If a checkpoint
  fails, the session aborts — replay is always possible.
- **One ModelRouter**: all LLM calls go through `backend/core/models.py`.
- **Prompts in files**: every system prompt lives in `backend/prompts/`.

See [CLAUDE.md](CLAUDE.md) for the full architecture rules and coding conventions.
