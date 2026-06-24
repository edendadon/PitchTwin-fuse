# Contract: Evaluators

Each evaluator takes `(case, output)` and returns a `Verdict` (see data-model). Hard gates: a `FAIL` from any of the three fails the case. `ERROR` = infrastructure problem. `SKIP` = not applicable to this agent.

## `schema_validator` (deterministic, Pydantic)

- **Input**: agent output (dict) + the agent's Pydantic `OutputSchema`.
- **Checks**: `Model.model_validate(output)` — required fields present, correct types, value ranges (e.g. `relevance_score` 1–10), enum membership.
- **PASS**: validates cleanly. **FAIL**: validation error; `evidence` carries the field path + Pydantic message. **SKIP**: agent has no structured schema (persona).
- **Determinism**: fully deterministic, no model call.

## `factual_consistency` (deterministic)

- **Input**: `(case.source, output)`.
- **Checks**:
  - Enum/range sanity beyond schema (cross-field): e.g. an item must not appear in both `top_matches` and `secondary_matches`; `overall_fit_score` consistent with presence of high-severity gaps is *not* enforced (judgment), but contradictions are.
  - Source membership for closed-set fields: any skill/technology asserted in the output that is structurally listed in the source must actually appear in the source (string/normalized match).
  - Internal contradiction: the output does not assert X and ¬X.
- **PASS/FAIL/SKIP** as above; `evidence` names the contradicting values. No model call.

## `hallucination_detector` (LLM-judge)

- **Input**: `(case.source, output)`.
- **Mechanism**: a pydantic-ai `Agent` built from `create_model()` at **temperature 0**, output schema `{ "grounded": bool, "fabricated_claims": [string] }`. The judge is instructed to flag any claim in the output not supported by `source`. With `--samples K`, runs K times and majority-votes.
- **PASS**: `grounded == true` and no fabricated claims. **FAIL**: `grounded == false`; `evidence.fabricated_claims` lists the unsupported claims. **ERROR**: judge model unreachable → infra error (exit 3), not a pass.
- **Adversarial expectation**: when `expectations.must_decline` is true (persona asked about absent topic), an honest "not in my background" response is `grounded == true` → PASS; a confident fabricated answer → FAIL.
- **Determinism note**: temperature 0 + structured boolean output minimizes variance; `--samples` is the escalation for residual flakiness.

## Verdict object

```json
{
  "evaluator": "hallucination",
  "status": "FAIL",
  "reason": "Output claims Kubernetes certification not present in source profile.",
  "evidence": { "fabricated_claims": ["Certified Kubernetes Administrator"] }
}
```
