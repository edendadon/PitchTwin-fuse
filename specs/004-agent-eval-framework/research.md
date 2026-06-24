# Phase 0 Research: Agent Eval Framework

Resolves the Technical Context unknowns. Each decision records rationale and rejected alternatives.

## R1 — Harness integration (Issue #1) when the harness is only half-built

**Context**: `matching_agent` and `writer_agent` are migrated to pydantic-ai `Agent` with Pydantic output schemas and signature `run_*(inputs) -> dict` (no `llm_client`). The other five (`profile`, `client_research`, `gap`, `persona`, `debrief`, plus the `combined` optimization) use the legacy `run_*(inputs, llm_client) -> dict` with `call_json`/`call`. The constitution's `Agent` base class (Issue #1) does not exist yet.

**Decision**: Introduce an **agent adapter registry** (`evals/harness.py`): a dict mapping each agent name to an entry describing how to invoke it (`invoke(case) -> output`), the source-data extractor, the output kind (structured dict vs free text), and the output schema (a Pydantic model). The registry hides the dual signatures behind one `invoke()` and is the single place that changes when Issue #1's `Agent` base class lands — at that point each entry delegates to `agent.execute()`.

**Rationale**: Decouples the eval framework from the in-flight migration so work proceeds now; one well-reviewed seam ([SYNC]) instead of signature-specific logic scattered across the runner; forward-compatible with the harness contract.

**Alternatives considered**:
- *Wait for Issue #1 to finish* — blocks the mandated CI gate indefinitely; rejected.
- *Call each agent ad hoc inside the runner* — scatters signature handling, brittle; rejected.
- *Force-migrate all agents first* — scope creep beyond this feature; the spec explicitly defers the harness migration; rejected.

## R2 — Output schemas for not-yet-migrated agents

**Context**: schema_validator needs a Pydantic model per agent; only `MatchingOutput`/`WriterOutput` exist.

**Decision**: Define eval-side Pydantic models in `evals/evaluators/schemas.py` for the legacy agents (`ProfileOutput`, `ClientContextOutput`, `GapOutput`, `DebriefOutput`), derived from each agent's documented JSON output format in its system prompt. Reuse `MatchingOutput`/`WriterOutput` directly by import. Persona has no structured output (free text) → no schema; its schema gate is a no-op/skip and grounding is enforced by the judge instead.

**Rationale**: Unblocks the schema gate for all structured agents today; models are authored from the agents' own prompt contracts so they match real output; when an agent later gains a canonical schema in the harness, the eval imports that instead and the eval-side copy is deleted.

**Alternatives considered**:
- *Only validate the two migrated agents* — fails FR-016 (every agent covered); rejected.
- *Generic "is it valid JSON with these keys" checks* — weaker than typed/range validation Principle II wants; rejected.

## R3 — pytest-style runner vs the `python -m evals.run` contract

**Context**: User wants a pytest-style runner; constitution fixes the entry point as `python -m evals.run --agent <name>`; baseline regression and coverage checks are not native pytest concepts.

**Decision**: pytest is the **execution + reporting engine**; `run.py` is a thin CLI wrapper. `run.py` parses `--agent/--all/--update-baseline/--samples/--json`, sets the selected agent(s) via an environment variable consumed by `conftest.py`, calls `pytest.main()` over `evals/test_eval.py` (parametrized one test per (agent, case, evaluator)), then loads the JSON results a `conftest` hook wrote, performs baseline diff + coverage enforcement, prints the human report, and returns the final exit code.

**Rationale**: Keeps pytest's parametrization/fixtures/reporting while honoring the constitutional CLI and adding the non-pytest concerns (baseline, coverage, aggregate exit code) in one place.

**Alternatives considered**:
- *Pure pytest, no `run.py`* — violates the constitution's named entry point and can't express baseline/coverage gates cleanly; rejected.
- *Custom runner, no pytest* — re-implements parametrization/reporting; contradicts user's "pytest-style"; rejected.
- *Add `pytest-json-report` dependency* — avoided; a small `pytest_terminal_summary`/`pytest_runtest_logreport` hook in `conftest.py` writes the JSON with no new dependency.

## R4 — Evaluator determinism split (which checks are deterministic vs LLM-judge)

**Context**: Three evaluators named: schema_validator, factual_consistency, hallucination_detector. User pins Pydantic for schema and LLM-judge for hallucination. Non-determinism is the top risk.

**Decision**:
- **schema_validator** — fully deterministic (Pydantic `model_validate`); reports field/type/range violations.
- **factual_consistency** — deterministic-first: enum membership (e.g. `gap_type`, `severity`, match `type`), numeric ranges (`relevance_score 1–10`, `overall_fit_score 0–10`), and internal contradictions (e.g. an item in both `top_matches` and `secondary_matches`; a skill claimed in output but absent from the source profile). No LLM-judge in this gate.
- **hallucination_detector** — LLM-judge (a pydantic-ai `Agent` built from `create_model()`, temperature 0, structured boolean output) that, given the case's **source** data and the agent output, returns `{grounded: bool, fabricated_claims: [...]}`. Run at temperature 0; for stability, support `--samples K` majority vote.

**Rationale**: Maximize the deterministic surface (schema + factual) so most gates are flake-free and free; confine LLM cost/variance to the one judgment that genuinely needs semantic reasoning (is a claim grounded in the source?), matching the user's directive.

**Alternatives considered**:
- *LLM-judge for factual_consistency too* — more flakiness/cost for checks that are mechanically decidable; rejected.
- *Embedding-similarity grounding* — fuzzy thresholds, opaque failures; rejected in favor of a judge that names the fabricated claim.

## R5 — Determinism settings for agent + judge model calls

**Context**: Migrated agents use `create_model()`; legacy use `LLMClient`. Neither pins temperature today.

**Decision**: The eval invokes models at **temperature 0**. For pydantic-ai agents, pass `model_settings={"temperature": 0}` (via the adapter, not by editing the agents). For the judge, build a dedicated temperature-0 `Agent`. For legacy `LLMClient` agents, accept current settings for v1 and note that adding an optional temperature parameter to `LLMClient.call*` is a small, separate enhancement; record it as a known limitation rather than blocking. Document residual variance handling via `--samples` + tolerance bands.

**Rationale**: Determinism where the API allows it now, without forcing changes into production agent code paths in this feature.

**Alternatives considered**:
- *Record/replay ("cassette") for fully offline determinism* — explicitly out of scope per spec; deferred to a future enhancement.

## R6 — Baseline format, regression tolerance, and update policy

**Context**: `baselines/current/` stores reference results; need a regression rule that is neither flaky nor permissive, and a guard against rubber-stamping.

**Decision**: One JSON file per agent at `evals/baselines/current/<agent>.json` containing, per case: gate verdicts (pass/fail) and metrics (latency_ms, and tokens/cost when available). **Regression rules**: (a) any case that passed in baseline but fails now = hard regression; (b) aggregate pass-rate drop = regression; (c) metric drift beyond a default tolerance band (latency default informational-only; pass/fail is the binding signal for v1). Baselines are committed to git. Updating requires the explicit `--update-baseline` flag (never automatic); the diff is shown so a reviewer sees what changed.

**Rationale**: Pass/fail transitions are deterministic and unambiguous — the safest binding regression signal for v1; numeric tolerance bands are tracked but informational until quality scoring (future phase) needs them. Git-committed baselines + explicit flag satisfy FR-013.

**Alternatives considered**:
- *Score-based regression now* — depends on the deferred LLM-judge quality scoring; rejected for v1.
- *Auto-update baseline on green* — defeats regression detection; rejected.

## R7 — Infrastructure-error vs eval-failure distinction

**Context**: FR-018 + edge case — a missing key/unreachable provider must not look like a passing or a failing eval.

**Decision**: The adapter classifies exceptions: provider/auth/network errors raise a distinct `InfraError`; the runner reports these as `ERROR` (separate from gate `FAIL`), excludes them from baseline writes, and exits non-zero with a message that names the infrastructure cause. A case can never be silently marked pass when its model call failed.

**Rationale**: Prevents false greens/reds from environment problems; keeps baselines clean.

## R8 — Golden case sourcing

**Context**: FR-003/004 — ≥5 cases/agent from demo data + manual variation, including adversarial and edge inputs.

**Decision**: Seed each agent's cases from `data/sample_profile.json` (Alex Rivera) and `data/sample_brief.json` (NovaPay) as the canonical "happy path", then add manual variations: a second industry/profile, an edge input (empty transcript for debrief; sparse profile for profile/matching), and at least one **adversarial grounding** case per output-generating agent (writer/persona/matching/gap) where the source lacks a tempting skill and the expectation is that the output must not claim it. Persona includes the "ask about something not in the profile → honest declination" case (SC-010).

**Rationale**: Real demo data keeps cases realistic; deliberate variation gives the gates something to catch; matches FR-004 and the success criteria.

---

**Outcome**: All Technical Context unknowns resolved. No NEEDS CLARIFICATION remain. Ready for Phase 1.
