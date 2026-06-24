# Agent Evals

Quality gates for PitchTwin's agents. Each agent's output is checked against a
golden set of cases through three hard gates:

- **schema** — output matches the agent's Pydantic schema (deterministic)
- **factual_consistency** — no self-contradiction; claimed skills exist in the source (deterministic)
- **hallucination** — an LLM judge confirms every concrete claim is grounded in the source

## Run

```bash
uv run python -m evals.run --agent matching     # evaluate one agent
uv run python -m evals.run --all                # evaluate all 7 agents
uv run python -m evals.run --all --workers 6    # ...in parallel (default is 6)
uv run python -m evals.run --all --workers 1    # serial (one case at a time)
uv run python -m evals.run --agent matching --samples 3   # majority-vote the judge (tames variance)
uv run python -m evals.run --agent matching --json out.json   # also write the JSON report
```

Needs an LLM provider configured in `.env` (the judge + agents call the model).

**Parallelism:** `--all` runs cases concurrently via pytest-xdist — `--workers`
defaults to **6** (so plain `--all` is already parallel). The full 35-case suite
runs in ~9 min at `-n6` vs ~54 min serial. Lower `--workers` if you hit provider
rate limits; use `--workers 1` for deterministic serial debugging.

### Exit codes (for CI)

| Code | Meaning |
|------|---------|
| 0 | all gates passed |
| 1 | a hard gate failed (e.g. a hallucination was caught) or a regression vs baseline |
| 3 | infrastructure error (provider unreachable / bad credentials) — never a false pass |
| 2 | (US3) coverage failure |

## Baselines & regressions

A **baseline** is a committed snapshot of each agent's per-case pass/fail at a
known-good point, stored as `evals/baselines/current/<agent>.json`. Later runs
diff against it so you can tell a *new* failure (a regression you just introduced)
from a *pre-existing* one.

### Step 1 — get a green run

`--update-baseline` refuses to capture if any case fails (no rubber-stamping), so
first make the agent pass:

```bash
uv run python -m evals.run --agent matching
# → "PASSED — all hard gates green."  (exit 0)
```

### Step 2 — create / refresh the baseline

```bash
uv run python -m evals.run --agent matching --update-baseline    # one agent
uv run python -m evals.run --all --update-baseline               # all agents
```

This writes `evals/baselines/current/matching.json`:

```json
{
  "agent": "matching",
  "captured_at": "2026-06-24T09:58:41Z",
  "cases": { "happy_novapay": {"passed": true}, "...": {"passed": true} }
}
```

Commit it so the baseline is reviewable in PRs:

```bash
git add evals/baselines/current/ && git commit -m "evals: capture matching baseline"
```

### Step 3 — check against the baseline

Just run normally — any agent that has a baseline is compared automatically:

```bash
uv run python -m evals.run --agent matching      # or --all
```

- A case that **passed in the baseline but fails now** is marked
  `<-- REGRESSION` and listed under `REGRESSIONS (...)`.
- The run **exits non-zero** on any hard-gate failure (regression or not), so CI
  blocks the merge.

```text
Eval results: 4/5 passed
  [PASS] matching:happy_novapay
  [FAIL] matching:edge_sparse  <-- REGRESSION
          hallucination: output contains claims not supported by source
REGRESSIONS (1): matching:edge_sparse
FAILED — hard gate failure (includes regressions).
```

### Notes

- **First run, no baseline:** the runner auto-captures one and reports no
  regression (nothing to compare against yet).
- **Updating is always explicit** (`--update-baseline`) and only on a clean run —
  so a regression can never silently become the new "normal".
- Exit codes: `0` pass · `1` gate fail / regression · `2` coverage (<5 cases) ·
  `3` infrastructure error (provider unreachable).

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
