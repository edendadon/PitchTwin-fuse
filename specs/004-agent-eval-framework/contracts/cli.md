# Contract: `python -m evals.run` CLI

The constitutional entry point (Principle V). `evals/run.py` is also runnable as `python evals/run.py`.

## Synopsis

```
python -m evals.run --agent <name>        # evaluate one agent against its golden set
python -m evals.run --all                 # evaluate all 7 agents, aggregate verdict
python -m evals.run --agent <name> --update-baseline   # capture/refresh baseline (explicit)
python -m evals.run --all --samples 3     # majority-vote the LLM-judge over 3 samples
python -m evals.run --all --json out.json # also write machine-readable report to out.json
```

## Options

| Flag | Type | Default | Meaning |
|------|------|---------|---------|
| `--agent <name>` | string | — | Agent to evaluate. One of: `profile`, `client_research`, `matching`, `writer`, `gap`, `persona`, `debrief`. Mutually exclusive with `--all`. |
| `--all` | flag | — | Evaluate every registered agent. |
| `--update-baseline` | flag | off | Write current results to `evals/baselines/current/<agent>.json` instead of failing on regression. Required to change a baseline. |
| `--samples <K>` | int | 1 | Run the LLM-judge K times per case; majority vote. Tames judge variance. |
| `--json <path>` | path | none | Write the machine-readable RunReport to `<path>` (always also written under `evals/.reports/`). |

Either `--agent` or `--all` is required.

## Exit codes

| Code | Condition |
|------|-----------|
| `0` | All evaluated cases pass all hard gates; no regressions; coverage satisfied (or `--update-baseline` used). |
| `1` | At least one hard-gate FAIL, or a regression vs baseline. |
| `2` | Coverage failure: a selected agent has zero / fewer than 5 golden cases (not overridable except by adding cases). |
| `3` | Infrastructure ERROR (provider unreachable / missing credentials). Distinct from eval failure; never reported as pass. |
| `4` | Usage error (bad/missing selector or unknown agent name). |

## Output

- **stdout**: human-readable report — per-case PASS/FAIL/ERROR/SKIP with reasons, per-agent rollup, regressions, coverage, overall verdict.
- **file**: JSON RunReport (see data-model `RunReport`) under `evals/.reports/<timestamp>.json` and, if `--json` given, at that path.

## Behavioral guarantees

- Runs in isolation: no app DB mutation, app server not required (FR-015).
- First run for an agent with no baseline auto-captures the baseline and does not report regressions (FR-011 edge).
- A model/provider failure yields exit 3 with a named infra cause, never a false pass (FR-018).
