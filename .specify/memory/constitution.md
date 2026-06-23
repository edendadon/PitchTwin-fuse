# PitchTwin Constitution

## Core Principles

### I. Determinism Over Speed
Every agent and workflow must produce predictable, repeatable outputs. Bounded retries, explicit timeouts, circuit breakers, and max-iteration guards prevent unbounded loops. Non-deterministic behavior (streaming, LLM variance) is isolated behind validation gates.

### II. Validation at Every Boundary
All agent inputs and outputs are validated via Pydantic schemas. Guardrails (schema, hallucination, token limits, factual consistency) run post-execution. No data flows between agents without validation. Eval gates run on every change.

### III. Observability by Default
Every agent call emits structured traces: trace_id, latency_ms, tokens_in/out, cost_usd, guardrail results, status. Checkpoints persist to SQLite after each workflow phase. Debug endpoint `/debug/trace/<id>` exposes full execution graph.

### IV. No Hallucination — Grounded Outputs Only
Persona Agent and all proposal-generation agents must only reference experiences, skills, and projects explicitly present in the consultant profile. Output validators cross-reference claims against source data. Fabrication is a hard failure.

### V. Test-First for Agents
Golden set evaluation cases exist for every agent before implementation. Baseline captured on first run. `python -m evals.run --agent <name>` must pass in CI. Regression detection is mandatory.

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

- Constitution supersedes all other practices.
- Amendments require: documentation, version bump, migration plan for affected agents.
- All PRs must verify: evals pass, traces clean, no schema violations.
- Complexity must be justified against hackathon P0/P1/P2 priorities.
- Runtime guidance in `AGENTS.md` and `.specify/memory/constitution.md` must stay in sync.

**Version**: 1.0.0 | **Ratified**: 2026-06-24 | **Last Amended**: 2026-06-24