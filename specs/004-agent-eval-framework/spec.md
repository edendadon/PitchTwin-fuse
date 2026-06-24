# Feature Specification: Agent Eval Framework

**Feature Branch**: `004-agent-eval-framework`

**Created**: 2026-06-24

**Status**: Draft

**Input**: User description: "Create evals/ directory with golden/ cases per agent (5 each), evaluators/ (schema_validator, factual_consistency, hallucination_detector), run.py CLI, baselines/current/. 7 agents × 5 cases = 35 golden cases from demo data + manual variation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evaluate one agent against hard quality gates (Priority: P1)

An engineer who changed a prompt, model, or agent runs the evaluation for that one agent and gets a clear pass/fail verdict driven by the non-negotiable gates: the output is structurally valid, it invents nothing beyond the source input, and it does not contradict the source. This is the constitution's mandated `python -m evals.run --agent <name>` contract.

**Why this priority**: This is the minimum viable safety net. Without it, no change to any agent can be trusted, and the constitution's "must pass in CI" requirement is unmet. It delivers value alone — even with one agent covered, that agent is protected against the worst failure modes (broken output shape, hallucination, contradiction).

**Independent Test**: Run the evaluation for a single agent that has golden cases. Confirm a clean output passes, a fabricated/hallucinated output fails, and a malformed output fails — each with a readable reason. No baseline or other agents required.

**Acceptance Scenarios**:

1. **Given** an agent with golden cases and a well-behaved model, **When** the engineer runs the eval for that agent, **Then** every case passes all three gates and the command reports success with a per-case summary.
2. **Given** a golden case whose source profile contains no AWS experience, **When** the agent output claims AWS expertise, **Then** the hallucination gate fails the case and identifies the fabricated claim.
3. **Given** an agent output missing a required field or with an out-of-range value, **When** the eval runs, **Then** the schema gate fails the case and names the offending field.
4. **Given** any gate fails on any case, **When** the run completes, **Then** the command signals overall failure (non-zero result) suitable for blocking a merge.

---

### User Story 2 - Detect regressions against a recorded baseline (Priority: P2)

A maintainer captures a known-good baseline of evaluation results, then on later runs the framework compares against it and surfaces regressions — cases that newly fail, or tracked metrics that have degraded beyond an accepted tolerance — so unintended quality drops are caught before merge.

**Why this priority**: Gates catch absolute failures; baselines catch *relative* decline (a prompt tweak that quietly makes outputs worse). The constitution makes regression detection mandatory. It builds on P1 but is independently demonstrable.

**Independent Test**: Capture a baseline, run again unchanged → zero regressions reported. Deliberately degrade an agent's behavior, run again → the regression is reported and the run fails.

**Acceptance Scenarios**:

1. **Given** no baseline exists yet, **When** the maintainer runs with the baseline-capture action, **Then** a baseline snapshot is stored and the run does not report false regressions.
2. **Given** a stored baseline, **When** an unchanged agent is re-evaluated, **Then** zero regressions are reported.
3. **Given** a stored baseline, **When** an agent's output quality is degraded (a previously passing case now fails, or a metric drops beyond tolerance), **Then** the run reports the specific regression and signals failure.
4. **Given** an intentional, reviewed improvement that changes results, **When** the maintainer explicitly updates the baseline, **Then** the new results become the reference and no accidental update can occur without that explicit action.

---

### User Story 3 - Full golden-set coverage across all agents (Priority: P3)

The team maintains at least five golden cases for every agent — derived from the demo profile and brief plus manual variations including adversarial and edge inputs — and can evaluate the entire suite with a single command to get one aggregate verdict.

**Why this priority**: Breadth of coverage is what makes the gate meaningful across the whole product. It depends on the P1 machinery existing, and grows over time, so it ranks below the core runner and regression detection.

**Independent Test**: Confirm each of the seven agents has ≥5 committed golden cases (≥35 total), then run the whole suite in one command and receive a single aggregate pass/fail with per-agent breakdown.

**Acceptance Scenarios**:

1. **Given** the golden set, **When** coverage is inspected, **Then** every agent has at least five cases and the total is at least 35.
2. **Given** all agents have cases, **When** the full suite runs, **Then** results are reported per agent and aggregated into one overall verdict.
3. **Given** a newly added agent with no golden cases, **When** the suite runs, **Then** the missing coverage is reported and treated as a failure (every agent must have cases).
4. **Given** an engineer wants to add a case, **When** they copy an existing case definition and edit its input and expectations, **Then** the new case is picked up with no change to framework code.

---

### Edge Cases

- **Malformed model output**: the model returns non-parseable or truncated output → the schema gate fails the case with a clear reason rather than crashing the run.
- **Provider unavailable / missing credentials**: the model cannot be reached → the run reports an infrastructure error distinct from an evaluation failure, and never reports a false pass.
- **Non-determinism**: the same input yields different output across runs → stability is handled so that benign variance does not cause false regressions (e.g., via tolerance bands and/or repeated sampling).
- **Degenerate inputs**: empty transcript for the debrief agent, or a near-empty profile → cases assert the expected graceful handling.
- **Adversarial grounding (persona)**: the client asks about something absent from the profile → the expected behavior is an honest "not in my background" response, which must pass the hallucination gate (not be penalized).
- **Free-text vs structured output**: the persona agent returns prose, not structured data → gates that assume structure adapt or are scoped appropriately for that agent.
- **First run with no baseline**: comparison is skipped and a baseline is captured instead, so the first run never reports phantom regressions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The framework MUST evaluate a single named agent against its golden set via a command-line entry point matching the constitution's contract (`run.py`, invocable as `python -m evals.run --agent <name>`).
- **FR-002**: The framework MUST support evaluating all agents in one invocation and producing an aggregate verdict.
- **FR-003**: The framework MUST maintain a golden set of at least five cases per agent for the seven agents (≥35 cases total), each case defining an input and its expectations, stored as in-repo, version-controlled artifacts.
- **FR-004**: Golden cases MUST be derived from the existing demo data (sample profile and brief) plus manually authored variations, including adversarial grounding cases and edge inputs.
- **FR-005**: The framework MUST provide a **schema** evaluator that checks each agent's output for required fields, correct structure/types, and valid value ranges/enumerations.
- **FR-006**: The framework MUST provide a **hallucination** evaluator that verifies the output references only entities and facts present in the case's source input, and flags any fabricated claim as a hard failure.
- **FR-007**: The framework MUST provide a **factual-consistency** evaluator that verifies the output does not contradict the source input or itself.
- **FR-008**: Each evaluator MUST return a structured verdict per case — pass/fail with a human-readable reason and supporting evidence (e.g., the offending field or claim).
- **FR-009**: A case MUST be marked failed if any hard-gate evaluator (schema, hallucination, factual-consistency) fails; an agent's run MUST be marked failed if any of its cases fail a hard gate.
- **FR-010**: The framework MUST be able to capture a baseline snapshot of evaluation results into an in-repo baselines location (`baselines/current/`).
- **FR-011**: The framework MUST compare a run against the stored baseline and report regressions — cases that newly fail and tracked metrics that degrade beyond a defined tolerance.
- **FR-012**: The command MUST signal overall failure (non-zero exit) when any hard gate fails or any regression is detected, and success otherwise, so it can gate continuous integration.
- **FR-013**: Updating the baseline MUST require an explicit, deliberate action so results cannot be silently rubber-stamped.
- **FR-014**: The framework MUST produce both a human-readable report and a machine-readable result artifact for each run.
- **FR-015**: The framework MUST run in isolation from the live application and its production data, and MUST NOT mutate runtime state.
- **FR-016**: The framework MUST report missing coverage (any agent without golden cases) and treat it as a failure, enforcing that every agent has cases.
- **FR-017**: Adding or editing a golden case MUST be possible by editing case definition files alone, without modifying framework code.
- **FR-018**: The framework MUST distinguish infrastructure errors (e.g., provider unavailable) from genuine evaluation failures in its reporting.

### Key Entities *(include if feature involves data)*

- **Golden Case**: one evaluation scenario for a specific agent — an identifier, the agent it targets, a description, the input/source data, and the expectations to check against. Sourced from demo data and manual variation.
- **Evaluator**: a single check applied to an agent's output for a case (schema, hallucination, factual-consistency), producing a verdict. Hard-gate evaluators determine pass/fail.
- **Evaluation Run**: the execution of one or all agents over their golden sets, yielding per-case verdicts and aggregate results and metrics.
- **Baseline**: a stored snapshot of a prior run's results and metrics, used as the reference for regression comparison; updated only by explicit action.
- **Eval Report**: the aggregated output of a run — per-case verdicts, per-agent and overall pass/fail, regressions versus baseline, and any infrastructure errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All seven agents each have at least five committed golden cases (at least 35 total).
- **SC-002**: Evaluating a single agent returns an unambiguous pass/fail verdict with a per-case summary in a single command.
- **SC-003**: 100% of seeded fabricated/hallucinated outputs are detected and fail the run.
- **SC-004**: 100% of seeded malformed or schema-invalid outputs are detected and fail the run.
- **SC-005**: Re-running an unchanged agent against an existing baseline reports zero regressions (no false positives from normal variance).
- **SC-006**: A deliberately degraded output (a known regression) is flagged against the baseline in 100% of seeded cases.
- **SC-007**: The full suite for all agents runs from a single command and yields one aggregate pass/fail with a per-agent breakdown.
- **SC-008**: Continuous integration can block a merge based solely on the run's success/failure signal.
- **SC-009**: An engineer can add a new golden case in under 10 minutes by copying and editing an existing case definition, with no framework code change.
- **SC-010**: An adversarial "ask about something not in the profile" persona case both produces an honest declination and passes the hallucination gate.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Model non-determinism causes flaky evals / false regressions | High | High | Deterministic mode (temperature 0); tolerance bands and/or repeated sampling; gates phrased as grounding/consistency rather than exact-match |
| Evaluation cost/time grows with cases and agents | High | Medium | Single-agent runs for fast feedback; full-suite runs reserved for gated/scheduled execution |
| Hallucination/factual checks miss subtle fabrications | Medium | High | Source-grounded checks with explicit evidence; adversarial golden cases that intentionally tempt fabrication |
| Baseline rubber-stamping hides regressions | Medium | High | Baselines version-controlled; updates require explicit action and review |
| Schema gate blocked by agents lacking a defined output contract | Medium | Medium | Begin with the current output shapes; tighten as the agent schema migration lands (profile and research first) |
| Golden-set authoring effort for seven agents | Medium | Medium | Seed from existing demo data; start at five cases per agent and grow on real failures |

## Assumptions

- The **seven agents** in scope are: profile, client research, matching, writer, gap, persona, and debrief. The combined agent is a runtime optimization that merges matching + writer + gap into one call; its coverage derives from those three agents' cases, and evaluating it directly is a future enhancement, not part of this feature.
- Evaluations run against the project's configured model provider through the existing client abstraction, using deterministic settings where supported. A record/replay ("cassette") layer for fully offline, deterministic CI is **out of scope** for this feature and noted as a future enhancement; initial CI may run live or on a scheduled basis.
- The **hard gates** for this feature are schema validity, no-hallucination (grounding), and factual consistency, evaluated as binary pass/fail. Graded quality scoring (e.g., LLM-as-judge rubrics) is **out of scope** for this slice and deferred to a later phase (per the brainstorm's layered approach).
- Golden case inputs are seeded from `data/sample_profile.json` and `data/sample_brief.json`, plus manually authored variations covering additional industries, adversarial grounding, and edge inputs.
- Baselines are stored in-repo under `baselines/current/`; regression tolerance for non-deterministic metrics uses a documented default band, with exact thresholds finalized during planning.
- The framework is separate from the existing unit tests (`tests/`) and does not require the web application to be running.
- The grounding and consistency checks are intended to be reusable as runtime guardrails (per the constitution), though wiring them into the live request path is outside this feature's scope.
