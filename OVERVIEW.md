# PitchTwin — Overview

**Your CV, came to life.**

## What it does

PitchTwin helps a technology consultant win an engagement. Give it a consultant's
profile and a client's brief, and it produces two things:

1. **A tailored proposal package** — a reframed CV, a personalized bio, ready-to-say
   talking points, a relevance map (which of the consultant's experiences matter most
   for *this* client), and an honest gap analysis.
2. **An interactive "twin"** — a shareable chat link the client can talk to before the
   meeting. The twin answers as the consultant, but is grounded strictly in the real
   profile: it never invents experience the consultant doesn't have. When the client
   ends the chat, PitchTwin generates a **debrief** for the consultant summarizing what
   the client cared about.

Everything runs through a small set of LLM "agents", each with one job (parse the
profile, research the client, match, write, find gaps, play the twin, debrief).

## How it works

```
Consultant profile ─┐
                    ├─(parallel)─► combine: match + write + gap ─► Proposal package
Client brief ───────┘                                            └─► auto-creates a twin link

Client ↔ Twin chat  (grounded in the profile, one LLM call per message)
        └─ on "End conversation" ─► Debrief report for the consultant
```

Built with Flask (web + routes), SQLite (storage), and a provider-agnostic LLM client
that supports LiteLLM (default), Google Gemini, and Groq.

## Run it

### Local (Python 3.11+)

```bash
# Install uv if needed: https://docs.astral.sh/uv/getting-started/installation/
uv sync
cp .env.example .env          # then add an API key for your chosen provider
uv run python app.py
```

Open http://localhost:5000.

### Docker

```bash
cp .env.example .env          # add your API key
docker-compose up --build
```

### Configuration

Set these in `.env`. `LLM_PROVIDER` chooses the backend (default `litellm`); you only
need the key for the provider you pick.

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `litellm` \| `gemini` \| `groq` (default `litellm`) |
| `LITELLM_API_KEY`, `LITELLM_BASE_URL`, `LITELLM_MODEL` | LiteLLM proxy settings (model defaults to `kimi-k2.5`) |
| `GEMINI_API_KEY` | Google Gemini key (uses `gemini-2.0-flash`) |
| `GROQ_API_KEY` | Groq key (uses `llama-3.3-70b-versatile`) |
| `FLASK_SECRET_KEY` | Flask session secret |
| `FLASK_DEBUG` | `1` for debug mode |
| `DB_PATH` | SQLite path (default `data/pitchtwin.db`) |

## Try the demo

1. Open http://localhost:5000.
2. Click **Load sample profile & brief** in the demo banner.
3. Follow the link → **Create proposal for NovaPay Financial**.
4. Hit **Generate Proposal Package** (takes ~60s).
5. Review the tailored CV, bio, talking points, and gap analysis.
6. Click **Open Client Twin Link**, open it in a new tab, and chat as the client.
7. Click **End conversation**, then **View Debrief** back on the proposal page.

## Tests

```bash
python3 tests/test_agents.py
```

Tests use a mock LLM client, so they run offline with no API key.
