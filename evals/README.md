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
| 1 | a hard gate failed (e.g. a hallucination was caught) |
| 3 | infrastructure error (provider unreachable / bad credentials) — never a false pass |
| 2 | (US3) coverage failure |

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

Tuning knobs: `EVALS_JUDGE_TEMPERATURE` (opt-in; some models reject ≠1),
`--samples` for judge majority voting.
