# Agent Evals

Quality gates for PitchTwin's agents. Each agent's output is checked against a
golden set of cases through three hard gates:

- **schema** — output matches the agent's Pydantic schema (deterministic)
- **factual_consistency** — no self-contradiction; claimed skills exist in the source (deterministic)
- **hallucination** — an LLM judge confirms every concrete claim is grounded in the source

## Run

```bash
python -m evals.run --agent matching     # evaluate one agent
python -m evals.run --all                # evaluate all registered agents
python -m evals.run --agent matching --samples 3   # majority-vote the judge (tames variance)
python -m evals.run --agent matching --json out.json   # also write the JSON report
```

Needs an LLM provider configured in `.env` (the judge + agents call the model).

### Exit codes (for CI)

| Code | Meaning |
|------|---------|
| 0 | all gates passed |
| 1 | a hard gate failed (e.g. a hallucination was caught) or a regression vs baseline |
| 3 | infrastructure error (provider unreachable / bad credentials) — never a false pass |
| 2 | (US3) coverage failure |

## Baselines & regressions

A baseline is a committed snapshot of each agent's per-case pass/fail at a
known-good point, stored at `evals/baselines/current/<agent>.json`.

```bash
python -m evals.run --agent matching --update-baseline   # capture/refresh (explicit only)
python -m evals.run --agent matching                     # compare; new failures are flagged "<-- REGRESSION"
```

- The **first run** for an agent with no baseline auto-captures one (no false regression).
- On later runs, a case that **passed in the baseline but fails now** is reported as a
  REGRESSION. Hard gates always bind: any FAIL (regression or not) exits non-zero.
- Updating a baseline is **never automatic** — it requires `--update-baseline`, and it
  **refuses to capture a run that has any failure or infrastructure error** (fix first, then
  baseline — no rubber-stamping). Commit baselines to git so changes are reviewable.

## Add a golden case

Drop a JSON file in `evals/golden/<agent>/` — no code change needed.

```json
{
  "id": "my_case",
  "agent": "matching",
  "description": "...",
  "tags": ["happy"],
  "source": { "structured_profile": {...}, "client_context": {...} },
  "input":  { "structured_profile": {...}, "client_context": {...} },
  "expectations": { "must_not_claim": ["Kubernetes"] }
}
```

- `source` = every fact the output is allowed to use (the judge sees only this).
- `input` = the exact arguments passed to the agent.
- Schema: `specs/004-agent-eval-framework/contracts/golden-case.schema.json`.

## Offline checks (no API key)

```bash
pytest tests/test_evals_meta.py -v   # verifies the gates catch seeded failures
```

## Layout

```
evals/
├── run.py              # CLI entry point
├── harness.py          # AGENT_REGISTRY: uniform invoke() across agent signatures
├── evaluators/         # base, schema_validator, factual_consistency, hallucination_detector
├── golden/<agent>/     # JSON cases (5+ per agent)
└── baselines/current/  # regression baselines (US2)
```

The hallucination judge runs through the project's `LLMClient` (same provider as the
agents). Use `--samples N` for judge majority voting to tame non-determinism.
