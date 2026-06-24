# Implementation Plan: Agent Eval Framework

**Branch**: `004-agent-eval-framework` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/004-agent-eval-framework/spec.md`

## Summary

Build an `evals/` package that gates every PitchTwin agent on three hard checks — output **schema validity** (Pydantic), **factual consistency** (deterministic), and **no hallucination** (LLM-judge) — driven by a golden set of JSON cases (≥5 per agent, ≥35 total) seeded from the demo profile/brief plus manual variation. A pytest-based runner exposed as `python -m evals.run --agent <name>` (constitution Principle V) executes cases, applies the evaluators as hard gates, compares results against an in-repo baseline (`evals/baselines/current/`) for regression detection, and exits non-zero on any gate failure, regression, or missing coverage so CI can block merges.

The technical approach (from user input): Python, pytest-style runner, JSON golden cases, Pydantic for schema validation, LLM-judge for hallucination detection, integrating with the in-progress agent harness (Issue #1). Because that harness is only partially migrated, the framework introduces a thin **agent adapter registry** that invokes each agent uniformly today and becomes a clean seam for the harness once it lands.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: pytest (eval engine), Pydantic v2 (schema gate), pydantic-ai + `agents/pydantic_ai_setup.create_model()` and `llm_client.LLMClient` (agent invocation + LLM-judge), LiteLLM provider (existing). No new runtime deps beyond pytest (already a dev dependency).
**Storage**: In-repo JSON files only — golden cases under `evals/golden/<agent>/`, baselines under `evals/baselines/current/`, run artifacts under `evals/.reports/` (gitignored). No database; isolated from the app's SQLite.
**Testing**: pytest is both the eval execution engine and the framework's own meta-test harness (`tests/` continues to hold app unit/integration tests).
**Target Platform**: Local developer machines and CI (Linux).
**Project Type**: Single-project CLI/tooling package added at repo root (`evals/`).
**Performance Goals**: Single-agent run (5 cases) gives fast feedback; wall-clock dominated by LLM latency at temperature 0. Full suite (35 cases) runnable in one command for gated/scheduled use.
**Constraints**: Deterministic settings (temperature 0) where the provider supports them; benign LLM variance must not produce false regressions (tolerance band + optional repeated sampling); a missing API key / unreachable provider reports an **infrastructure error distinct from an eval failure** and never a false pass; no mutation of app runtime state.
**Scale/Scope**: 7 agents × ≥5 cases = ≥35 golden cases at launch; golden set and agent coverage grow over time.

All Technical Context unknowns are resolved in [research.md](./research.md) (harness integration approach, evaluator determinism split, runner↔pytest wiring, regression tolerance defaults). No NEEDS CLARIFICATION remain.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|-----------|--------|
| I. Determinism Over Speed | Evaluators run at temperature 0; bounded case sets; tolerance bands instead of exact-match for variance; no unbounded loops. | PASS |
| II. Validation at Every Boundary | This feature *is* the eval gate; Pydantic schema validation of every agent output is FR-005. | PASS |
| III. Observability by Default | Runner records per-case metrics (latency, pass/fail, tokens/cost where the client exposes them) into the baseline and run report. Token/cost capture is best-effort until `LLMClient` surfaces usage. | PASS (note) |
| IV. No Hallucination — Grounded Outputs Only | hallucination_detector (LLM-judge) + factual_consistency enforce grounding as hard gates (FR-006/007); adversarial golden cases verify it. | PASS |
| V. Test-First for Agents | Delivers the mandated golden set + `python -m evals.run --agent <name>` CI gate + regression detection verbatim. | PASS |

**Result**: No violations. Complexity Tracking section left empty.

*Post-Phase-1 re-check*: design introduces only the adapter registry and evaluators package — no new projects, no added persistence, no constitutional violations. Still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/004-agent-eval-framework/
├── spec.md              # Feature specification
├── brainstorm-context.md# Promoted brainstorm
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI + JSON schemas)
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
evals/
├── __init__.py
├── run.py                       # CLI entry: `python -m evals.run [--agent N|--all] [--update-baseline] [--samples K] [--json PATH]`
├── conftest.py                  # pytest fixtures: case discovery, adapter, evaluators, JSON result hook
├── test_eval.py                 # parametrized hard-gate tests over (agent, case, evaluator)
├── harness.py                   # AGENT_REGISTRY adapter — uniform invoke() across legacy + pydantic-ai agents (Issue #1 seam)
├── report.py                    # human-readable report, JSON artifact, baseline load/diff/update, coverage check
├── evaluators/
│   ├── __init__.py
│   ├── base.py                  # Verdict model + Evaluator protocol
│   ├── schema_validator.py      # Pydantic validation against the agent's output schema
│   ├── factual_consistency.py   # deterministic: enum/range/internal-contradiction + source checks
│   ├── hallucination_detector.py# LLM-judge: claims grounded in source input?
│   └── schemas.py               # eval-side Pydantic output schemas for not-yet-migrated agents
├── golden/
│   ├── profile/           (5 JSON cases)
│   ├── client_research/   (5)
│   ├── matching/          (5)
│   ├── writer/            (5)
│   ├── gap/               (5)
│   ├── persona/           (5)
│   └── debrief/           (5)
└── baselines/
    └── current/                 # <agent>.json baseline snapshots (version-controlled)

tests/
└── test_evals_meta.py           # meta-tests: framework detects seeded hallucination/schema/regression failures
```

**Structure Decision**: A single new top-level package `evals/` (separate from `tests/`, which keeps app unit/integration tests). The runner uses pytest as its execution + reporting engine; `run.py` wraps `pytest.main()` to add `--agent` selection, baseline diff, coverage enforcement, and the final exit code. `harness.py` is the integration seam: a registry mapping each agent name to a uniform `invoke(case) -> output` that hides today's dual call signatures and adopts the Issue #1 `Agent` base class transparently once it exists.

## Triage Framework: [SYNC] vs [ASYNC] Classification

**Execution Strategy**: Hybrid — human-reviewed design for the judge and the harness seam; agent-delegated for mechanical authoring and deterministic checks.

### Preliminary Task Classification

| Task Category | Estimated [SYNC] Tasks | Estimated [ASYNC] Tasks | Rationale |
|---------------|----------------------|----------------------|-----------|
| Business Logic (evaluators) | 2 | 1 | LLM-judge hallucination design + factual-consistency policy are quality/grounding-critical ([SYNC]); schema_validator is mechanical ([ASYNC]). |
| Data Operations (golden cases, baselines) | 1 | 2 | Baseline diff/tolerance policy reviewed ([SYNC]); 35 golden JSON cases + eval-side schemas authored by agent then reviewed ([ASYNC]). |
| UI Components | 0 | 0 | None (CLI text output only). |
| Integrations (harness adapter, runner↔pytest) | 1 | 1 | Adapter registry across dual signatures is the risky integration seam ([SYNC]); pytest parametrization/report hook is mechanical ([ASYNC]). |
| Infrastructure (CLI, report, CI wiring) | 1 | 1 | CI gate wiring + exit-code contract reviewed ([SYNC]); report formatting ([ASYNC]). |

### Triage Decision Criteria Applied

**High-Risk [SYNC] Classifications:**

- **hallucination_detector (LLM-judge)** — grounding is a constitutional hard gate (Principle IV); the judge prompt/rubric and pass/fail thresholds directly determine whether fabrication is caught. Human review required.
- **harness.py adapter registry** — must invoke 7 agents with two different signatures correctly (legacy takes `llm_client`; migrated do not) and stay forward-compatible with Issue #1. A wrong call silently invalidates an agent's evals.
- **Baseline regression policy** — tolerance bands and the explicit-update rule guard against both false positives and rubber-stamping; needs deliberate sign-off.
- **CLI exit-code / CI gate contract** — determines what blocks merges.

**Agent-Delegated [ASYNC] Classifications:**

- Authoring the 35 golden JSON cases from demo data + variation (mechanical, schema-conformant, reviewable).
- `schema_validator.py` and eval-side Pydantic schemas for the legacy agents (derived from each agent's documented output format).
- `factual_consistency.py` deterministic checks (enum membership, numeric ranges, internal contradiction).
- pytest parametrization in `test_eval.py`, the JSON result hook in `conftest.py`, and `report.py` formatting.

### Triage Audit Trail

| Task | Classification | Primary Criteria | Risk Level | Rationale |
|------|----------------|------------------|------------|-----------|
| Design + implement hallucination LLM-judge | [SYNC] | Grounding gate, non-determinism | High | Constitutional hard gate; judge reliability gates the whole suite. |
| Implement harness adapter registry | [SYNC] | Integration correctness | High | Two agent signatures + future harness; wrong invocation invalidates evals. |
| Define baseline diff + tolerance policy | [SYNC] | Regression correctness | Med | Balances flakiness vs missed regressions; guards rubber-stamping. |
| Wire `run.py` CLI + exit codes + CI gate | [SYNC] | Merge-blocking behavior | Med | Determines CI semantics. |
| Author 35 golden cases | [ASYNC] | Mechanical authoring | Low | Schema-conformant, reviewed in PR. |
| Implement schema_validator + eval schemas | [ASYNC] | Deterministic mapping | Low | Derived from documented output formats. |
| Implement factual_consistency deterministic checks | [ASYNC] | Deterministic rules | Low | Enum/range/contradiction logic. |
| pytest parametrization + JSON hook + report.py | [ASYNC] | Mechanical plumbing | Low | Standard pytest + formatting. |
| Meta-tests for the framework | [ASYNC] | Verification | Low | Assert framework catches seeded failures. |

## Complexity Tracking

> No constitution violations — section intentionally empty.
