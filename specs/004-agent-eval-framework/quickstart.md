# Quickstart: Agent Eval Framework

## Prerequisites

- Project deps installed (`uv sync` / `pip install -r requirements.txt`); `pytest` and `pydantic` are present.
- An LLM provider configured in `.env` (LiteLLM by default) — required for live agent + judge calls. Without it, the runner exits `3` (infrastructure error), never a false pass.

## Run evals for one agent

```bash
python -m evals.run --agent matching
```

You get a per-case PASS/FAIL/ERROR/SKIP breakdown across the three gates (schema, factual_consistency, hallucination), a per-agent rollup, and an exit code (`0` pass, `1` gate failure/regression, `2` missing coverage, `3` infra error).

## Run the whole suite (CI gate)

```bash
python -m evals.run --all
echo $?   # 0 = all agents green
```

## Capture / update a baseline

First run for an agent auto-captures a baseline. To deliberately refresh after a reviewed change:

```bash
python -m evals.run --agent writer --update-baseline
```

Baselines live in `evals/baselines/current/<agent>.json` and are committed to git. Updating is never automatic.

## Tame judge variance

```bash
python -m evals.run --all --samples 3   # majority-vote the hallucination judge
```

## Add a golden case

1. Copy an existing case: `cp evals/golden/matching/happy_novapay.json evals/golden/matching/my_case.json`.
2. Edit `id`, `description`, `tags`, `source`, `input`, and any `expectations` (e.g. `must_not_claim`). Validate against `contracts/golden-case.schema.json`.
3. Re-run `python -m evals.run --agent matching`. No framework code changes needed.

## Verify the framework itself catches failures (meta-tests)

```bash
pytest tests/test_evals_meta.py -v
```

These assert that a seeded hallucinated output fails the hallucination gate, a malformed output fails the schema gate, and a degraded result is flagged as a regression.

## Acceptance mapping

| Spec criterion | How to verify here |
|----------------|--------------------|
| SC-001 coverage (≥5/agent, ≥35) | `python -m evals.run --all` → coverage section; exit `2` if short |
| SC-002 single-agent verdict | `python -m evals.run --agent <name>` |
| SC-003 hallucination caught | adversarial golden case + meta-test → gate FAIL |
| SC-004 schema-invalid caught | malformed meta-test → schema FAIL |
| SC-005 stable re-run | run twice vs baseline → 0 regressions |
| SC-006 regression flagged | degrade output in meta-test → regression reported |
| SC-007 aggregate verdict | `--all` one command, per-agent breakdown |
| SC-008 CI gate | branch on `$?` |
| SC-010 persona declines + grounded | persona adversarial case → declines and PASS grounding |
