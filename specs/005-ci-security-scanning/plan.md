# Implementation Plan: CI Security Scanning (Trivy + CodeQL + Dependabot)

**Branch**: `005-ci-security-scanning` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/005-ci-security-scanning/spec.md`

## Summary

Add three free, public-repo security capabilities to CI without disturbing the existing `ci.yml` (ruff lint `continue-on-error` + pytest):

1. **Trivy** — filesystem/dependency + config/misconfiguration scanning (`aquasecurity/trivy-action`), SARIF uploaded to GitHub code scanning.
2. **CodeQL** — static analysis of the Python codebase (`github/codeql-action` init → autobuild → analyze), results to GitHub code scanning.
3. **Dependabot** — automated update proposals (`.github/dependabot.yml`) for the `github-actions` and `uv` ecosystems (Python; native uv support reads `pyproject.toml` + `uv.lock`), weekly, plus security updates. See research.md Decision 1.

Triggers for the scanners: `pull_request` + `push` to `main` + weekly `schedule`. Rollout is advisory/non-blocking. New scanning jobs request `security-events: write`; the existing lint/test job is untouched.

## Technical Context

**Language/Version**: Python 3.11 (CI pins 3.11; CodeQL language = `python`)
**Primary Dependencies**: GitHub Actions (`actions/checkout@v4`), `aquasecurity/trivy-action@v0.33.1`, `github/codeql-action` (v3 init/analyze + `upload-sarif`), Dependabot (GitHub-native, `uv` + `github-actions` ecosystems)
**Storage**: N/A (CI config only; findings persist in GitHub code scanning)
**Testing**: Existing `pytest` suite + `ruff`; validate new YAML with `actionlint`/`yamllint` if available, otherwise schema review
**Target Platform**: GitHub Actions `ubuntu-latest` runners
**Project Type**: Single Python project + CI/infrastructure config
**Performance Goals**: Each new scan job ≤ 10 min (matches existing `timeout-minutes: 10`)
**Constraints**: $0 incremental cost (public-repo free tier only); must not weaken or break existing `ci.yml`; minimum-necessary permissions
**Scale/Scope**: 3 new config files (`codeql.yml`, `trivy.yml`, `dependabot.yml`); existing `ci.yml` unchanged; 2 Dependabot ecosystems

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Impact | Status |
|-----------|--------|--------|
| I. Determinism Over Speed | Scanners pinned to major action versions; weekly schedule is deterministic; advisory mode avoids flaky build failures | ✅ Pass |
| II. Validation at Every Boundary | Adds an *additional* validation boundary (security findings) to CI; no change to agent I/O schemas | ✅ Pass (supportive) |
| III. Observability by Default | Findings surface in the central code-scanning dashboard rather than buried in logs — improves observability | ✅ Pass (supportive) |
| IV. No Hallucination | Not applicable — no LLM/agent output involved | ✅ N/A |
| V. Test-First for Agents | No agent code changed; existing eval/test gate (`ci.yml`) preserved intact | ✅ Pass |
| Governance — Compliance Review | Directly advances "all PRs must verify … zero schema violations"; CI security posture strengthened | ✅ Pass (supportive) |

**Result**: No violations. No entries required in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-ci-security-scanning/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (config artifacts + findings model)
├── quickstart.md        # Phase 1 output (how to verify)
├── contracts/           # Phase 1 output (workflow trigger/permission contracts)
│   ├── codeql.workflow.md
│   ├── trivy.workflow.md
│   └── dependabot.config.md
└── tasks.md             # Phase 2 output (/spec.tasks — NOT created here)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── ci.yml           # EXISTING — unchanged (ruff lint continue-on-error + pytest)
│   ├── codeql.yml        # NEW — CodeQL init/autobuild/analyze, python
│   └── trivy.yml         # NEW — Trivy fs + config scan → SARIF upload
└── dependabot.yml        # NEW — github-actions + pip ecosystems, weekly
```

**Structure Decision**: Keep each concern in its own file. CodeQL and Trivy live as **separate workflow files** (not jobs added to `ci.yml`) so their elevated `security-events: write` permission and `schedule` trigger stay isolated from the lint/test job, satisfying FR-008 (minimum-necessary permissions) and FR-011 (don't touch existing pipeline). Dependabot is a native config file, not a workflow.

## Triage Framework: [SYNC] vs [ASYNC] Classification

**Execution Strategy**: Small, security-sensitive infrastructure change. The workflow files modify CI permissions and security posture, so they warrant human review before merge; the Dependabot config is low-risk and mechanical.

### Preliminary Task Classification

| Task Category | Estimated [SYNC] Tasks | Estimated [ASYNC] Tasks | Rationale |
|---------------|----------------------|----------------------|-----------|
| Business Logic | 0 | 0 | No application logic changes |
| Data Operations | 0 | 0 | No data layer changes |
| UI Components | 0 | 0 | None |
| Integrations | 2 | 0 | CodeQL + Trivy workflows touch CI security permissions → human review |
| Infrastructure | 1 | 1 | Dependabot config [ASYNC]; verification/wiring [SYNC] |

### Triage Decision Criteria Applied

**High-Risk [SYNC] Classifications:**
- Authoring `codeql.yml` and `trivy.yml` — introduce `security-events: write` and new triggers; security-relevant, must be human-reviewed.
- Final verification that `ci.yml` is byte-for-byte unchanged and the pipeline still passes.

**Agent-Delegated [ASYNC] Classifications:**
- Authoring `.github/dependabot.yml` — declarative, low-risk, schema-validated.

### Triage Audit Trail

| Task | Classification | Primary Criteria | Risk Level | Rationale |
|------|----------------|------------------|------------|-----------|
| Add `codeql.yml` | [SYNC] | Security/permissions | Med | Grants `security-events: write`; affects security dashboard |
| Add `trivy.yml` | [SYNC] | Security/permissions | Med | New SARIF upload + permission scope |
| Add `dependabot.yml` | [ASYNC] | Declarative config | Low | No permission changes; native schema-validated |
| Verify existing pipeline intact | [SYNC] | Regression safety | Low | Confirms FR-011 (no breakage) |

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
