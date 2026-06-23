# PitchTwin — Agent Instructions

## Quick Start

```bash
# Local (Python 3.11+)
pip install -r requirements.txt
cp .env.example .env
# Edit .env with GEMINI_API_KEY or GROQ_API_KEY or LITELLM_API_KEY
python3 app.py

# Docker
docker-compose up --build
```

Open http://localhost:5000

## Commands

| Task | Command |
|------|---------|
| Run tests | `python3 tests/test_agents.py` |
| Run app locally | `python3 app.py` |
| Run with Docker | `docker-compose up --build` |
| Health check | `curl http://localhost:5000/api/health` |

## Architecture

**7 Agents** (in `agents/`):
- `profile_agent.py` — Parse raw CV → structured JSON
- `client_research_agent.py` — Analyze client brief → context JSON
- `matching_agent.py` — Rank profile relevance to client
- `writer_agent.py` — Generate tailored CV, bio, talking points
- `gap_agent.py` — Identify skill/experience gaps
- `persona_agent.py` — Powers client-facing chat twin (grounded in profile)
- `debrief_agent.py` — Summarize conversation for consultant

**Orchestration** (`orchestrator.py`):
- Phase 1: Profile + Client Research run in parallel (threading)
- Phase 2: Combined agent (matching + writer + gap in one LLM call)
- Phase 3: Persona Agent (per message, on-demand)
- Phase 4: Debrief Agent (triggered on session end)

**Data Layer** (`db.py`, `models.py`): SQLite with tables `consultant_profiles`, `proposals`, `twin_sessions`

**LLM Client** (`llm_client.py`): Wrapper for Gemini/Groq/LiteLLM via `LLMULTIMM_PROVIDER` env var (`gemini` | `groq` | `litellm`)

## Key Files

```
app.py              # Flask routes
orchestrator.py     # Pipeline runner + threading
llm_client.py       # LLM wrapper (Gemini/Groq/LiteLLM)
db.py               # SQLite init + CRUD
models.py           # Dataclasses: Profile, Proposal, TwinSession
agents/             # 7 specialized agents
spec/               # spec.plan, spec.tasks, spec.arch
tests/test_agents.py # Unit tests with mock LLM
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key |
| `LITELLM_API_KEY` | LiteLLM proxy key |
| `LITELLM_BASE_URL` | LiteLLM endpoint (default: https://litellm.tikalk.dev/v1) |
| `LITELLM_MODEL` | Model name (default: kimi-k2.5) |
| `LLM_PROVIDER` | `gemini` \| `groq` \| `litellm` (default: `litellm`) |
| `FLASK_SECRET_KEY` | Session secret |
| `FLASK_DEBUG` | `1` for debug |
| `DB_PATH` | SQLite path (default: `data/pitchtwin.db`) |

## Hackathon Priorities (Issues)

- **P0**: [#1 Agent harness](https://github.com/edendadon/PitchTwin-fuse/issues/1), [#2 DAG orchestrator](https://github.com/edendadon/PitchTwin-fuse/issues/2)
- **P1**: [#3 Constitution](https://github.com/edendadon/PitchTwin-fuse/issues/3), [#4 Evals](https://github.com/edendadon/PitchTwin-fuse/issues/4), [#5 Streaming twin + human gate](https://github.com/edendadon/PitchTwin-fuse/issues/5)
- **P2**: [#6 Observability](https://github.com/edendadon/PitchTwin-fuse/issues/6)

## Conventions

- **Python 3.11**, type hints where practical
- Agents are pure functions: `run_<agent>(input, llm_client) -> dict`
- All LLM calls via `llm_client.call()` or `call_json()` with retries
- No hallucination: Persona Agent system prompt enforces grounding in profile only
- Tests use `MockLLMClient` — no real API calls

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **PitchTwin-fuse** (218 symbols, 535 relationships, 15 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/PitchTwin-fuse/context` | Codebase overview, check index freshness |
| `gitnexus://repo/PitchTwin-fuse/clusters` | All functional areas |
| `gitnexus://repo/PitchTwin-fuse/processes` | All execution flows |
| `gitnexus://repo/PitchTwin-fuse/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
