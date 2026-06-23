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