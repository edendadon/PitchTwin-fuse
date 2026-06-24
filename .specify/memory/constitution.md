<!--
### SYNC IMPACT REPORT
- Version change: 1.0.0 → 1.1.0
- List of modified principles:
  - I. Determinism Over Speed (Added explicit rationale)
  - II. Validation at Every Boundary (Added explicit rationale)
  - III. Observability by Default (Added explicit rationale)
  - IV. No Hallucination — Grounded Outputs Only (Added explicit rationale)
  - V. Test-First for Agents (Added explicit rationale)
- Added sections:
  - Governance/Amendment Procedure (Expanded)
  - Governance/Versioning Policy (Expanded)
  - Governance/Compliance Review Expectations (Expanded)
- Removed sections: None
- Templates requiring updates:
  - ✅ `.specify/templates/plan-template.md`
  - ✅ `.specify/templates/spec-template.md`
  - ✅ `.specify/templates/tasks-template.md`
- Follow-up TODOs: None
-->

# PitchTwin Constitution

## Core Principles

### I. Determinism Over Speed
Every agent and workflow must produce predictable, repeatable outputs. Bounded retries, explicit timeouts, circuit breakers, and max-iteration guards prevent unbounded loops. Non-deterministic behavior (streaming, LLM variance) is isolated behind validation gates.
* **Rationale**: LLMs are inherently non-deterministic. Without strict deterministic boundaries, automated systems quickly become untestable and unreliable.

### II. Validation at Every Boundary
All agent inputs and outputs are validated via Pydantic schemas. Guardrails (schema, hallucination, token limits, factual consistency) run post-execution. No data flows between agents without validation. Eval gates run on every change.
* **Rationale**: Early detection of schema mutations or low-quality LLM outputs prevents corrupted state from propagating down the multi-agent execution pipeline.

### III. Observability by Default
Every agent call emits structured traces: trace_id, latency_ms, tokens_in/out, cost_usd, guardrail results, status. Checkpoints persist to SQLite after each workflow phase. Debug endpoint `/debug/trace/<id>` exposes full execution graph.
* **Rationale**: To debug, optimize, and audit agent-driven systems, developers must have granular, immediate insight into the internal state and LLM prompt/response history.

### IV. No Hallucination — Grounded Outputs Only
Persona Agent and all proposal-generation agents must only reference experiences, skills, and projects explicitly present in the consultant profile. Output validators cross-reference claims against source data. Fabrication is a hard failure.
* **Rationale**: In professional match-making and client-facing chat simulations, any hallucinated experience or fabricated skill completely destroys trust in the platform.

### V. Test-First for Agents
Golden set evaluation cases exist for every agent before implementation. Baseline captured on first run. `python -m evals.run --agent <name>` must pass in CI. Regression detection is mandatory.
* **Rationale**: We cannot safely iterate on agent prompts and logic without automated testing and a baseline reference to measure regression.

## Development Workflow

### SDD Loop (Spec-Driven Development)
All new features follow: `/spec.brainstorm` → `/spec.specify` → `/spec.plan` → `/spec.tasks` → `/spec.implement` → `/spec.verify`. Each step produces an artifact reviewed before proceeding.

### Change Workflow
Modifications to existing code use: `/change.specify` → `/change.implement` → `/change.verify` → `/change.levelup`. Lightweight, no file artifacts for ad-hoc tasks.

### Agent Harness Contract
All agents implement the `Agent` base class with `InputSchema`, `OutputSchema`, `execute()`, and guardrail hooks. Migration is incremental — Profile and Client Research agents first.

### Orchestration as DAG
Pipeline defined as directed acyclic graph of `AgentNode`, `ParallelNode`, `HumanGateNode`. Checkpointing, timeout budgets, circuit breakers, and resume-from-failure are mandatory.

## Governance

- **Supersession**: The Constitution is the supreme authority of the project and supersedes all other development practices, codebase configurations, and guidelines.
- **Amendment Procedure**:
  - Any proposed amendment must be documented via `/change.specify` or similar process.
  - The amendment requires a semantic version bump and a clear migration plan for any affected agent or pipeline component.
  - Amendments must be approved and merged into the main repository branch before they take effect.
- **Versioning Policy**: Semantic versioning (MAJOR.MINOR.PATCH) is strictly enforced:
  - **MAJOR**: Backward-incompatible governance or principle removals, or fundamental redefinitions.
  - **MINOR**: New principles or sections added, or materially expanded guidelines.
  - **PATCH**: Typo fixes, wording clarifications, and non-semantic refinements.
- **Compliance Review Expectations**:
  - All PRs must verify that agent evaluations pass, traces remain clean, and zero schema violations occur.
  - Any complexity introduced into the codebase must be justified against the hackathon P0/P1/P2 priorities.
  - Runtime guidance in `AGENTS.md` and the Constitution must be kept in perfect sync.

**Version**: 1.1.0 | **Ratified**: 2026-06-24 | **Last Amended**: 2026-06-24
