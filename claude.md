# CLAUDE.md — Project Nexus
 
> This file is read by Claude Code at the start of every session. Keep it
> accurate. If architecture changes, update this file in the same commit.
 
## What We're Building
 
Project Nexus is a multi-agent orchestration platform. A user submits a
natural-language goal; the system decomposes it into a DAG of sub-tasks, routes
each sub-task to the best LLM (Claude Sonnet 4, GPT-4o, or Gemini 2.5 Flash),
gathers research via tools, executes via CodeAct in a sandbox, verifies against
sources, and reflects on quality — looping up to 3 times until a quality score
of 0.85 is reached.
 
We are competing with Manus AI on **accuracy** (not autonomy). Our edge comes
from: (1) a 5-agent pipeline vs their 3, (2) cross-session memory in Pinecone,
(3) multi-model routing, (4) a quality-gated reflection loop.
 
## Repo Layout (at a glance)
 
- `backend/` — Python 3.12, FastAPI, LangGraph orchestrator, agents, tools
- `frontend/` — React 18 + TS + Tailwind, Vite
- `sandbox/` — isolated gRPC code execution container
- `infra/` — docker-compose, nginx, postgres init
- `scripts/` — eval + maintenance tooling
- `backend/prompts/` — agent system prompts (markdown, loaded at startup)
 
## Commands
 
```bash
make up          # docker compose up --build
make down        # docker compose down
make migrate     # apply SQL migrations in backend/db/migrations/
make test        # pytest backend/tests + vitest frontend
make lint        # ruff + mypy + eslint
make eval        # run scripts/eval_accuracy.py
```
 
## Non-Negotiable Architectural Rules
 
1. **One ModelRouter.** All LLM calls go through `backend/core/models.py`.
   Never instantiate a ChatAnthropic / ChatOpenAI / ChatGoogleGenerativeAI
   elsewhere.
 
2. **One NexusState.** All agents read/write the shared state. No agent holds
   private state between invocations. See `backend/core/state.py`.
 
3. **Prompts live in files, not code.** Every system prompt is a markdown
   file in `backend/prompts/`, loaded once at process start. Never inline
   system prompts in Python.
 
4. **Context assembly is centralized.** `backend/core/context.py` is the ONLY
   place that builds user messages for agents. If you need new context for an
   agent, extend the corresponding `build_*_context` function.
 
5. **Tools register themselves.** New tools use the `@tool` decorator in
   `backend/tools/__init__.py`. Don't hardcode tool lists in agents.
 
6. **Sandbox is sacred.** Never execute LLM-generated code outside the sandbox
   container. The Phase 5 subprocess stub was removed in Phase 6 — don't
   reintroduce it.
 
7. **Checkpointer is sacred.** Every agent transition writes to the Postgres
   checkpointer. If a checkpoint fails to write, abort the session — never
   continue without it. Replay must work.
 
8. **Quality gate is 0.85.** Do not tune this value without updating the spec
   and the eval script. Do not add fallbacks that let lower-quality output
   ship silently.
 
9. **Max 3 iterations.** The reflection loop hard-caps at 3. Anything more
   and we return output with a `disclaimer` flag.
 
10. **Pinecone writes only at quality >= 0.70.** Polluting memory with low-
    quality past runs hurts every future session.

11. **Provider mode is toggled only through ModelRouter.** Never hardcode a
    model provider anywhere else. The toggle endpoint (`POST /api/v1/config/
    provider-mode`) and `backend/core/models.py` are the single source of
    truth for which LLMs are active. The active router can be hot-swapped at
    runtime via `set_model_router()` without a server restart.
 
## Coding Conventions
 
- **Python**: 3.12, type hints everywhere, ruff + mypy strict. Async-first —
  no sync I/O in request paths.
- **TypeScript**: strict mode on. No `any`. Types mirroring backend schemas
  live in `frontend/src/lib/types.ts` and are hand-kept in sync (for now).
- **SQL**: snake_case. UUIDs for all primary keys except audit_log (BIGSERIAL
  for insert throughput).
- **Commits**: conventional commits (feat:, fix:, chore:, refactor:). Each
  phase from the spec's Section 10 gets its own commit or small PR.
- **Tests**: pytest for backend, vitest for frontend. Integration tests use
  real Postgres + Redis in Docker (not mocks). LLM calls are mocked with
  deterministic canned responses.
 
## Environment Variables
 
All required vars are documented in `.env.example`. On first clone:
 
```bash
cp .env.example .env
# fill in API keys
make up
```
 
## When You're Stuck
 
- **Agent returns malformed JSON**: check `backend/prompts/{agent}.md` —
  the "Respond ONLY with valid JSON" line must be the final instruction.
- **LangGraph infinite loop**: inspect the loop_detector logs. If two
  iterations produce identical task_plan hashes, the system is by design
  aborting and returning with `disclaimer=loop_detected`.
- **Sandbox timeouts on simple code**: check that `iptables-setup.sh`
  hasn't blocked a domain the code needs. Allowlist is in
  `sandbox/egress_allowlist.txt`.
- **"Cannot find module langgraph.checkpoint.postgres_async"**: you're on
  langgraph < 0.3. Upgrade.
 
## Do NOT
 
- Do NOT add a sync version of any endpoint.
- Do NOT store API keys in code or in the frontend bundle.
- Do NOT bypass the Verifier because "the Executor output looks fine."
- Do NOT increase max_iterations beyond 3 to force a passing score.
- Do NOT quote search results verbatim in outputs — paraphrase and cite.
- Do NOT add features not in the spec without updating the spec first.
 
## Change Log Pointer
 
Every architectural deviation from this file goes in `docs/ADRs/`
(Architecture Decision Records). If you're about to break a rule above,
write the ADR first.
