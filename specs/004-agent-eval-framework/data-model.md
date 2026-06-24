# Phase 1 Data Model: Agent Eval Framework

Entities are in-repo JSON artifacts and in-memory Pydantic models. No database.

## GoldenCase (on disk: `evals/golden/<agent>/<case_id>.json`)

One evaluation scenario for one agent.

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | Unique within the agent; matches filename stem; kebab/snake case. |
| `agent` | string | One of the 7 registered agent names; must equal the parent directory. |
| `description` | string | Human summary of what the case probes. |
| `tags` | string[] | Subset of `{happy, edge, adversarial}`; ≥1 required. |
| `source` | object | The ground-truth source data the output must stay faithful to (e.g. the structured profile and/or client context). Used by hallucination + factual gates. |
| `input` | object | The exact arguments passed to the agent for this case (shape depends on the agent — see contracts). |
| `expectations` | object | Optional per-case overrides: `must_not_claim` (string[]), `must_decline` (bool, persona), `expected_enums`, notes. Defaults come from the agent's schema + global rules. |

**Validation**: loader rejects a case whose `agent` ≠ directory, whose `id` is non-unique, or whose `input` is missing. Each agent directory MUST contain ≥5 cases (coverage gate, FR-016).

## OutputSchema (in code: `evals/evaluators/schemas.py` + reused agent models)

Pydantic v2 models defining valid agent output. Reused: `MatchingOutput`, `WriterOutput` (imported from the agents). Defined eval-side until the harness owns them: `ProfileOutput`, `ClientContextOutput`, `GapOutput`, `DebriefOutput`. Persona: none (free text).

Key constraints carried by these models (examples):
- scores: `relevance_score` 1–10, `overall_fit_score` 0–10.
- enums: match `type ∈ {experience, project, skill}`; `severity ∈ {high, medium, low}`; `gap_type ∈ {missing_skill, limited_experience, no_direct_industry_exposure, certification_missing}`.
- required non-empty lists where the agent must produce content (e.g. `talking_points`).

## Verdict (in memory; emitted in reports)

Result of one evaluator on one case.

| Field | Type | Rules |
|-------|------|-------|
| `evaluator` | string | `schema` \| `factual_consistency` \| `hallucination`. |
| `status` | enum | `PASS` \| `FAIL` \| `ERROR` (infra) \| `SKIP` (n/a, e.g. schema on persona). |
| `reason` | string | Human-readable explanation. |
| `evidence` | object | Offending field/path, fabricated claims list, contradicting values, judge raw verdict. |

## CaseResult (in memory; rolled into reports + baseline)

| Field | Type | Rules |
|-------|------|-------|
| `agent` | string | |
| `case_id` | string | |
| `verdicts` | Verdict[] | One per evaluator run. |
| `passed` | bool | True iff no hard-gate verdict is FAIL/ERROR. |
| `metrics` | object | `latency_ms`; `tokens_in/out`, `cost_usd` when the client exposes them; `samples` if >1. |

## Baseline (on disk: `evals/baselines/current/<agent>.json`)

Reference snapshot for regression comparison. Committed to git; updated only via `--update-baseline`.

| Field | Type | Rules |
|-------|------|-------|
| `agent` | string | |
| `captured_at` | string (ISO-8601) | Stamped at capture. |
| `cases` | object | Map `case_id -> { passed: bool, metrics: {...} }`. |

**Regression** (vs current run): a baseline-passing case now failing; an aggregate pass-rate drop; metric drift beyond tolerance (informational for v1). Missing baseline → capture instead of compare (no false regression).

## RunReport (on disk: `evals/.reports/<timestamp>.json`, gitignored; human report to stdout)

| Field | Type | Rules |
|-------|------|-------|
| `selector` | string | `--agent <name>` or `all`. |
| `results` | CaseResult[] | All evaluated cases. |
| `coverage` | object | Per-agent case counts; flags agents under 5 / with zero. |
| `regressions` | object[] | Case-level regressions vs baseline. |
| `infra_errors` | object[] | Cases that hit `ERROR`. |
| `summary` | object | Totals, per-agent pass/fail, overall verdict, exit code. |

## Relationships

```
GoldenCase (≥5 per agent) ──run via AGENT_REGISTRY.invoke──▶ agent output
        │                                                      │
        └── source ───────────────┐                            ▼
                                   ▼                    [schema_validator]──┐
                          [hallucination judge]         [factual_consistency]├─▶ Verdict[] ─▶ CaseResult
                                   └────────────────────────────────────────┘                   │
                                                                                                 ▼
                                                                          Baseline ◀──diff──▶ RunReport ─▶ exit code
```
