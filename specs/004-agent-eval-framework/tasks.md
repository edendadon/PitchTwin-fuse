---
description: "Task list for Agent Eval Framework"
---

# Tasks: Agent Eval Framework

**Input**: Design documents from `/specs/004-agent-eval-framework/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Included — the framework's own meta-tests verify it catches seeded hallucination/schema/regression failures (constitution Principle V, quickstart).

**Organization**: By user story (P1 → P2 → P3) for independent implementation and testing.

## Format: `[ID] [P?] [SYNC/ASYNC] [Story?] Description with file path`

- **[P]**: parallelizable (different files, no incomplete dependencies)
- **[SYNC]**: human review required · **[ASYNC]**: delegable
- Paths are repo-relative.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [ASYNC] Create the `evals/` package skeleton: `evals/__init__.py`, `evals/evaluators/__init__.py`, `evals/golden/<agent>/` directories for all 7 agents, `evals/baselines/current/`, and a `.gitignore` entry for `evals/.reports/`.
- [ ] T002 [P] [ASYNC] Ensure the eval suite is excluded from the app's normal pytest run (keep `pyproject.toml` `testpaths=["tests"]`) and register a `pytest` marker namespace for evals so `evals/` is only collected via the runner.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [SYNC] Implement the agent adapter registry in `evals/harness.py`: `AGENT_REGISTRY` mapping agent name → entry (`invoke(case) -> output`, `source` extractor, output kind structured|text, output schema or None). The uniform `invoke()` MUST hide both call signatures (legacy `run_*(inputs, llm_client)` vs migrated `run_*(inputs)`), apply temperature-0 settings where the provider allows, and raise a distinct `InfraError` on provider/auth/network failure (per research R1, R5, R7). Registry starts empty; entries added per agent in US1/US3.
- [ ] T004 [P] [ASYNC] Implement `evals/evaluators/base.py`: the `Verdict` Pydantic model (`evaluator`, `status` ∈ PASS|FAIL|ERROR|SKIP, `reason`, `evidence`) and an `Evaluator` protocol `evaluate(case, output) -> Verdict` (per data-model).
- [ ] T005 [P] [ASYNC] Implement the golden-case loader in `evals/harness.py` (or `evals/loader.py`): read `evals/golden/<agent>/*.json`, validate each against `contracts/golden-case.schema.json`, and reject cases whose `agent` ≠ directory or whose `id` is non-unique.
- [ ] T006 [ASYNC] Implement `evals/conftest.py`: fixtures that discover cases via the loader, read the selected agent(s) from an env var set by `run.py`, and a `pytest_runtest_logreport`/`pytest_terminal_summary` hook that writes per-case results to `evals/.reports/<timestamp>.json` (no new dependency — research R3).

**Checkpoint**: Registry, verdict model, loader, and pytest plumbing exist — user stories can begin.

---

## Phase 3: User Story 1 - Evaluate one agent against hard quality gates (Priority: P1) 🎯 MVP

**Goal**: `python -m evals.run --agent <name>` runs an agent's golden cases through the three hard gates and returns a clear pass/fail with reasons.

**Independent Test**: Run `python -m evals.run --agent matching`; a clean output passes all gates, a fabricated output fails the hallucination gate, a malformed output fails the schema gate.

### Tests for User Story 1

- [ ] T007 [P] [SYNC] [US1] Meta-test in `tests/test_evals_meta.py`: a seeded fabricated output FAILs the hallucination gate and a malformed/out-of-range output FAILs the schema gate (write first; expected to fail until evaluators land).

### Implementation for User Story 1

- [ ] T008 [P] [ASYNC] [US1] Implement `evals/evaluators/schema_validator.py`: validate output via the agent's Pydantic `OutputSchema` (`model_validate`); return FAIL with field path on error, SKIP when the agent has no structured schema (per contracts/evaluators.md).
- [ ] T009 [P] [ASYNC] [US1] Implement `evals/evaluators/factual_consistency.py`: deterministic enum/range checks, internal-contradiction checks (e.g. item in both top & secondary matches), and source-membership for closed-set fields (skills/tech asserted must appear in `case.source`).
- [ ] T010 [SYNC] [US1] Implement `evals/evaluators/hallucination_detector.py`: a pydantic-ai judge `Agent` from `create_model()` at temperature 0 with output `{grounded: bool, fabricated_claims: []}`; honor `expectations.must_decline`; support `--samples K` majority vote; raise `InfraError` (not PASS) if the judge model is unreachable (research R4, R7).
- [ ] T011 [ASYNC] [US1] Implement `evals/test_eval.py`: parametrize over (agent, case) for the selected agent(s), invoke via `AGENT_REGISTRY.invoke`, and assert the three evaluators as hard gates (one assertion per evaluator, with the Verdict reason surfaced on failure).
- [ ] T012 [SYNC] [US1] Implement `evals/run.py` CLI: argparse for `--agent/--all/--update-baseline/--samples/--json`; set the agent-selection env var; call `pytest.main()` over `evals/test_eval.py`; map results to the exit-code contract (0 pass, 1 gate fail, 3 infra error, 4 usage). Baseline/coverage exit codes wired in US2/US3.
- [ ] T013 [ASYNC] [US1] Register the `matching` agent in `AGENT_REGISTRY` (reuse `MatchingOutput`) and author 5 golden cases in `evals/golden/matching/` from demo data + variation: happy (NovaPay), edge (sparse profile), and ≥1 adversarial (`must_not_claim` a skill absent from `source`).

**Checkpoint**: `python -m evals.run --agent matching` runs end-to-end and the gates fire correctly. MVP complete.

---

## Phase 4: User Story 2 - Detect regressions against a recorded baseline (Priority: P2)

**Goal**: Capture a baseline; later runs flag newly-failing cases and signal failure; explicit `--update-baseline` refreshes it.

**Independent Test**: Capture a baseline, re-run unchanged → 0 regressions; degrade an output → regression reported and run fails.

### Tests for User Story 2

- [ ] T014 [P] [SYNC] [US2] Meta-test in `tests/test_evals_meta.py`: capturing a baseline then re-running unchanged reports 0 regressions; a degraded (previously-passing now-failing) case is reported as a regression.

### Implementation for User Story 2

- [ ] T015 [SYNC] [US2] Implement `evals/report.py`: build the `RunReport` (per data-model), load/write `evals/baselines/current/<agent>.json`, compute regressions (baseline-pass→now-fail; pass-rate drop), render the human report and the machine-readable JSON; first-run-with-no-baseline auto-captures instead of comparing.
- [ ] T016 [SYNC] [US2] Integrate `report.py` into `evals/run.py`: wire `--update-baseline` (explicit-only capture) and regression detection into the exit-code contract (exit 1 on regression); print the baseline diff so changes are reviewable (FR-011, FR-013, research R6).

**Checkpoint**: Baseline capture + regression detection work for any agent.

---

## Phase 5: User Story 3 - Full golden-set coverage across all agents (Priority: P3)

**Goal**: ≥5 golden cases for every one of the 7 agents (≥35 total) and a single-command aggregate verdict with coverage enforcement.

**Independent Test**: Inspect coverage (every agent ≥5 cases, ≥35 total); `python -m evals.run --all` yields one aggregate pass/fail with per-agent breakdown; an agent with no cases fails with exit 2.

### Tests for User Story 3

- [ ] T017 [P] [SYNC] [US3] Meta-test in `tests/test_evals_meta.py`: an agent with zero golden cases causes the runner to report missing coverage and exit 2.

### Implementation for User Story 3

- [ ] T018 [P] [ASYNC] [US3] Implement `evals/evaluators/schemas.py`: eval-side Pydantic output models `ProfileOutput`, `ClientContextOutput`, `GapOutput`, `DebriefOutput` derived from each agent's documented output format; import/reuse `MatchingOutput` and `WriterOutput` from the agents (research R2).
- [ ] T019 [ASYNC] [US3] Register the remaining 6 agents in `AGENT_REGISTRY` (`profile`, `client_research`, `writer`, `gap`, `persona`, `debrief`), including persona's free-text invocation (build system prompt + call `run_persona_agent`) and schema SKIP for persona.
- [ ] T020 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/profile/` (happy from sample profile, edge sparse/near-empty profile, variation second industry).
- [ ] T021 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/client_research/` (happy NovaPay brief, edge terse brief, variation different industry/tone).
- [ ] T022 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/writer/` including ≥1 adversarial `must_not_claim` (source lacks a tempting skill).
- [ ] T023 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/gap/` including a case where required skills are absent from the profile (honest gap expected).
- [ ] T024 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/persona/` including the adversarial `must_decline` case (asked about a topic absent from profile → honest declination, passes grounding — SC-010).
- [ ] T025 [P] [ASYNC] [US3] Author 5 golden cases in `evals/golden/debrief/` including the empty-transcript edge case.
- [ ] T026 [SYNC] [US3] Implement coverage enforcement + `--all` aggregation in `evals/run.py`/`evals/report.py`: detect agents with <5 or 0 cases, report missing coverage, exit 2; aggregate per-agent results into one overall verdict (FR-002, FR-016).

**Checkpoint**: All 7 agents covered (≥35 cases); `--all` gives one aggregate verdict; coverage gaps fail.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T027 [P] [ASYNC] Capture initial baselines for all agents (`python -m evals.run --all --update-baseline`) and commit `evals/baselines/current/*.json`.
- [ ] T028 [P] [ASYNC] Document eval usage: add a short "Running evals" section to `README.md`/`AGENTS.md` linking `quickstart.md`.
- [ ] T029 [ASYNC] Run the `quickstart.md` walkthrough end-to-end and fix any drift between docs and behavior.
- [ ] T030 [P] [SYNC] Add the CI gate: a workflow step running `python -m evals.run --all` that blocks merge on non-zero exit (SC-008); document the live-vs-scheduled execution choice (research R5/spec assumption).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no dependencies.
- **Foundational (P2)**: depends on Setup; BLOCKS all user stories (registry, verdict model, loader, conftest).
- **US1 (P3)**: depends on Foundational. Delivers the MVP runner + 3 gates + matching coverage.
- **US2 (P4)**: depends on Foundational; builds on US1's runner (regression layer on top of the run loop).
- **US3 (P5)**: depends on Foundational; reuses US1's evaluators/registry. Independent of US2.
- **Polish (P6)**: depends on the desired stories being complete (T027 needs US1+US2; T030 needs US3 for `--all`).

### Within Each User Story

- Meta-tests written first (T007, T014, T017) and expected to fail until implementation lands.
- Evaluators (T008–T010) before the parametrized runner test (T011) and CLI (T012).
- `report.py` (T015) before its runner integration (T016).
- Eval-side schemas (T018) + registration (T019) before authoring cases that rely on them; coverage enforcement (T026) after all cases exist.

### Parallel Opportunities

- T004 + T005 (different files) run in parallel after T003.
- US1 evaluators T008 + T009 run in parallel; T010 (judge) independent file, also [P]-eligible but [SYNC].
- US3 golden-case authoring T020–T025 are all [P] (distinct directories).
- Across stories: once Foundational completes, US1 and US2-prep and US3 case-authoring can proceed by different people, integrating at T016/T026.

---

## Parallel Example: User Story 3 golden cases

```bash
Task: "Author 5 golden cases in evals/golden/profile/"
Task: "Author 5 golden cases in evals/golden/client_research/"
Task: "Author 5 golden cases in evals/golden/writer/"
Task: "Author 5 golden cases in evals/golden/gap/"
Task: "Author 5 golden cases in evals/golden/persona/"
Task: "Author 5 golden cases in evals/golden/debrief/"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & VALIDATE**: `python -m evals.run --agent matching` exercises all three gates. Demo-ready MVP.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → single-agent gating works (MVP).
3. US2 → regression detection on top.
4. US3 → full 7-agent coverage + aggregate `--all` + CI gate.

Each story is independently testable and adds value without breaking prior stories.

---

## Notes

- [P] = different files, no incomplete dependencies.
- [SYNC] tasks (T003 harness, T007/T014/T017 meta-tests, T010 judge, T012/T016/T026 runner contract, T015 report, T030 CI) require human review per the plan's triage.
- The harness registry (T003) and the LLM-judge (T010) are the two highest-risk integration points — review carefully.
- Persona is free-text: schema gate SKIPs; grounding enforced by the judge.
- Commit after each task or logical group; capture baselines (T027) only after the suite is green.
