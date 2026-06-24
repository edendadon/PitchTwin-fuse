# Brainstorm Context: Agent Eval Framework (Golden Set + Baseline Runner)

## Problem Statement

PitchTwin's value depends on 8 LLM agents (`profile`, `client_research`, `matching`,
`writer`, `gap`, `combined`, `persona`, `debrief`) producing correct, grounded,
schema-valid output. Today the only safety net is `tests/test_agents.py`, which feeds a
`MockLLMClient` canned JSON and asserts a key exists — it proves the *plumbing* works, not
that a *real model* produces good output, and it cannot detect quality regressions when a
prompt, model, or provider changes.

The constitution already mandates the solution (Principle V): "Golden set evaluation cases
exist for every agent before implementation. Baseline captured on first run.
`python -m evals.run --agent <name>` must pass in CI. Regression detection is mandatory."
This brainstorm scopes *how* to build that framework: the golden-set structure, the
baseline runner, the scoring/guardrail model, and — critically — how to keep LLM
non-determinism from making evals flaky or expensive.

## Key Concepts

- **Golden set**: a curated collection of input cases per agent, each paired with
  *expectations* (not necessarily a single "correct" string — LLM output varies).
  Expectations range from hard structural facts to soft quality rubrics.
- **Baseline**: a recorded snapshot of metrics (scores, latency, tokens, cost, pass-rate)
  from a known-good run, stored in-repo. Future runs diff against it.
- **Regression detection**: a new run fails CI if a hard gate breaks or a tracked metric
  drops below baseline beyond a tolerance band.
- **Guardrail / hard gate** (constitution II & IV): a *must-pass* check — schema validity,
  no hallucination (every claim traceable to input), token-budget, factual consistency.
  A guardrail failure is a hard build failure, never a "score went down a bit".
- **Quality metric / soft signal**: a graded judgment (e.g. "talking points are specific
  and client-relevant: 4/5") used for drift tracking, not binary pass/fail.
- **Grounding validator**: the reusable check behind Principle IV — does the output
  reference only entities present in the source profile? Used both as a runtime guardrail
  and as an eval gate.
- **LLM-as-judge**: using a model to score output against a rubric when no deterministic
  check captures the quality dimension.
- **Eval vs unit test**: unit tests (existing `MockLLMClient`/`FakeLLMClient`) are
  deterministic plumbing checks; evals exercise real model behavior and judge quality.
  They are separate suites with separate triggers.

## Approaches Considered

### Approach A: Deterministic assertion-based evals
- **How it works**: Each golden case declares machine-checkable expectations only — output
  validates against the agent's Pydantic `OutputSchema`; required fields non-empty; enums
  in range (e.g. `gap.severity ∈ {high,medium,low}`, `overall_fit_score ∈ 0..10`);
  `must_contain` keywords; grounding check (no entity outside the input profile);
  token/latency budgets. No judge model. Baseline = pass-rate + perf metrics.
- **Tradeoffs**: Fast, free, fully deterministic, trivially CI-friendly, no API key needed
  if run against recorded fixtures. But blind to quality nuance — a CV that is schema-valid
  and grounded yet bland or poorly targeted passes.
- **Risks**: Gives false confidence; teams stop improving prompt quality because "evals are
  green". Keyword checks are brittle proxies for relevance.
- **Best for**: Hard gates (schema, grounding, budgets) and the persona agent's
  no-hallucination constraint — exactly the constitution's *must-pass* layer.

### Approach B: LLM-as-judge rubric scoring
- **How it works**: Each golden case carries a rubric (dimensions + anchors, e.g.
  relevance, grounding, tone-match, honesty-of-gaps). A judge model scores the agent's
  output 1–5 per dimension. Baseline = mean scores per dimension; regression = score drop
  beyond tolerance.
- **Tradeoffs**: Captures the quality the product actually sells; tolerant of wording
  variance. But the judge is itself non-deterministic, costs tokens on every run, needs its
  own calibration, and can drift if the judge model changes.
- **Risks**: Flaky thresholds → false regressions; judge bias/sycophancy; cost scales with
  cases × dimensions × samples; "judging the judge" problem.
- **Best for**: Soft quality dimensions on generative agents (writer, persona, debrief,
  combined) where no structural check suffices.

### Approach C: Hybrid layered runner (hard gates + scored metrics + baseline diff)
- **How it works**: Two-tier evaluation per case. **Tier 1 — gates** (Approach A):
  schema + grounding + budget; any failure = hard fail, non-zero exit. **Tier 2 — metrics**
  (heuristic where possible, LLM-judge where not): graded scores tracked against a stored
  baseline with per-metric tolerance. Runner: `evals/run.py` exposing
  `python -m evals.run --agent <name>` (per constitution), `--all`, `--update-baseline`
  (first run / intentional change), `--samples N` (average over runs to tame variance).
  Golden cases live in `evals/golden/<agent>/*.json|yaml`; baselines in
  `evals/baselines/<agent>.json`. Exit non-zero on any gate failure OR metric regression
  beyond tolerance.
- **Tradeoffs**: Matches the constitution exactly (hard hallucination/schema failures +
  regression detection). More moving parts than A; cost of B only on the dimensions that
  need it. Tiering lets PRs run cheap gates while quality scoring runs nightly.
- **Risks**: More framework surface to build and maintain; baseline-update discipline
  required so people don't rubber-stamp regressions.
- **Best for**: The actual requirement — this is the recommended direction.

## Architecture Notes

- **Module layout**: new top-level `evals/` package — `run.py` (CLI entry, the
  `python -m evals.run` target), `golden/<agent>/` (cases), `baselines/<agent>.json`,
  `gates.py` (schema/grounding/budget checks), `metrics.py` (heuristics + judge),
  `report.py` (human + machine output). Distinct from `tests/` (unit) by design.
- **Agent contract dependency**: the cleanest gate (schema validation) depends on agents
  exposing Pydantic `OutputSchema` (constitution "Agent Harness Contract", and the new
  `agents/pydantic_ai_setup.py` + `pydantic-ai` dependency signal this migration is
  starting). Until an agent has a schema, its gate falls back to ad-hoc dict checks.
- **LLM access**: reuse `pydantic_ai_setup.create_model()` / `LLMClient` so evals hit the
  same LiteLLM proxy the app uses. The judge can be a separate (cheaper/stronger) model id.
- **Grounding validator is shared infrastructure**: the same function powers the runtime
  guardrail (Principle IV) and the eval gate — build once, call from both.
- **Observability hook**: the Logfire tracing just added (`observability.py`) already
  captures latency; extend `LLMClient` to surface `tokens_in/out` + `cost_usd` so the
  baseline can track the perf/cost metrics Principle III names.
- **Determinism strategy**: pin judge + agent `temperature=0`; for residual variance,
  `--samples N` and tolerance bands rather than exact match. Consider a record/replay
  ("cassette") layer so PR-time CI replays recorded LLM responses deterministically and
  offline, while a nightly job runs live against the real model.
- **Targets the live path**: the running pipeline uses `combined_agent`, not the separate
  matching/writer/gap agents — the golden set must cover `combined` (and persona/debrief)
  to reflect production, even though the legacy three still exist.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM non-determinism → flaky evals / false regressions | H | H | temp=0; `--samples N` averaging; tolerance bands; judge/grounding not exact-match |
| Eval cost/time on every PR (tokens, latency) | H | M | Tiered: cheap gates on PR via recorded fixtures; full live scoring nightly |
| LLM-as-judge unreliable / biased | M | H | Anchored rubrics; calibrate judge against a few human-labeled cases; pin judge model |
| Baseline rubber-stamping (regressions merged via `--update-baseline`) | M | H | Version baselines in git; require PR justification + review to update |
| Schema gate blocked by agents lacking `OutputSchema` | M | M | Incremental: ad-hoc dict gate now, tighten as pydantic migration lands (profile + research first) |
| Golden-set authoring effort for 8 agents | M | M | Seed from `data/sample_profile.json` + `sample_brief.json`; start 3–5 cases/agent; grow on real failures |
| CI needs real API key / network → secret exposure, outages | M | M | Record/replay fixtures for PR runs; live key only in gated nightly job |

## Open Questions

- **CI execution model**: replay recorded fixtures (deterministic, offline) on PRs with
  live runs nightly, or run live on every PR? (Drives cost, flakiness, secret handling.)
- **Per-agent metric choice**: which agents need LLM-judge scoring (writer, persona,
  debrief, combined?) vs deterministic-only (profile, client_research, matching, gap)?
- **Thresholds**: what pass bar per gate and what regression tolerance per metric
  (absolute drop? % drop? std-dev band)?
- **Golden case format**: JSON (matches existing `data/*.json`) or YAML (more readable for
  multi-line prompts/rubrics)?
- **Eval target granularity**: evaluate per-agent functions, the `combined` agent, and/or
  the full pipeline end-to-end?
- **Baseline scope**: one baseline per agent, or per (agent × model) so provider swaps are
  comparable?
- **Persona specifics**: how to score a *string* (not JSON) response, and how to construct
  adversarial "ask about something not in the profile" grounding cases?

## Recommended Direction

**Approach C — the hybrid layered runner.** It is the only option that satisfies the
constitution as written: hard, non-negotiable gates for schema validity and the
no-hallucination constraint (a *hard failure*, per Principle IV), plus baseline-tracked
quality metrics for regression detection (Principle V). Approach A alone can't catch
quality drift; Approach B alone can't give the deterministic hallucination/schema gates the
constitution demands and is too flaky/costly to be the sole CI signal.

Build it incrementally to manage cost and effort:
1. **Skeleton + gates first** — `evals/run.py` with `python -m evals.run --agent <name>`,
   schema + grounding + budget gates, 3–5 golden cases per agent seeded from existing
   sample data, baseline captured via `--update-baseline`. This satisfies "must pass in CI"
   immediately and cheaply.
2. **Add scored metrics** — heuristics first, LLM-judge for the generative agents that need
   it, with tolerance bands.
3. **Add record/replay** so PR CI is deterministic and offline; reserve live runs for a
   nightly job.

Start the golden set with `combined`, `persona`, and `debrief` (the agents on the live
pipeline + twin path), then backfill the rest.
