# Tasks: CI Security Scanning (Trivy + CodeQL + Dependabot)

**Feature**: `005-ci-security-scanning` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Inputs**: plan.md, research.md, data-model.md, contracts/, quickstart.md

**Tech**: GitHub Actions (`actions/checkout@v4`), `aquasecurity/trivy-action@0.33.1`, `github/codeql-action@v3`, Dependabot v2 (`uv` + `github-actions`). Python 3.11. Advisory rollout. Worktree: `.worktrees/005-ci-security-scanning`.

**No TDD test tasks**: workflow/config YAML is validated via schema/lint + live CI run, not unit tests (none requested in spec). Validation tasks are included instead.

---

## Phase 1: Setup

- [X] T001 [SYNC] Confirm work is on branch `005-ci-security-scanning` in the isolated worktree and capture the baseline blob hash of `.github/workflows/ci.yml` (`git rev-parse HEAD:.github/workflows/ci.yml`) for the later unchanged-verification — file: `.github/workflows/ci.yml`

## Phase 2: Foundational (blocking prerequisites)

- [X] T002 [SYNC] Lock the shared workflow conventions both scanners follow: top-level `permissions: contents: read`; elevated `security-events: write` ONLY on the scanning job; pinned action versions; advisory mode (no build failure on findings); weekly `schedule` crons offset from each other. (Conventions captured in research.md Decisions 4–5; this task is the go/no-go gate before authoring workflows.) — ref: `specs/005-ci-security-scanning/research.md`

**Checkpoint**: Conventions agreed → user stories US1/US2/US3 can proceed independently.

---

## Phase 3: User Story 1 — Dependency & configuration vulnerability scanning (P1)

**Goal**: Trivy scans dependencies + config on PR/push/weekly; findings reach code scanning.
**Independent test**: Open a PR; `Trivy` run appears, completes ≤10 min, uploads `trivy-fs`/`trivy-config` SARIF, does not block the PR.

- [X] T003 [SYNC] [US1] Create `.github/workflows/trivy.yml`: triggers `pull_request`(main) + `push`(main) + weekly `schedule`; top-level `contents: read`; scan job `security-events: write`; `aquasecurity/trivy-action@0.33.1` `scan-type: fs` (`scanners: vuln,secret`, `ignore-unfixed: true`, `exit-code: 0`, `format: sarif`, `output: trivy-fs.sarif`) then `github/codeql-action/upload-sarif@v3` (`category: trivy-fs`, `if: always()`); plus a second `scan-type: config` pass → `trivy-config.sarif` uploaded with `category: trivy-config`; `timeout-minutes: 10` — file: `.github/workflows/trivy.yml`
- [X] T004 [P] [ASYNC] [US1] Validate `trivy.yml` parses and is schema-valid (`actionlint .github/workflows/trivy.yml` if available, else `python -c "import yaml; yaml.safe_load(open('.github/workflows/trivy.yml'))"`) — file: `.github/workflows/trivy.yml`

**Checkpoint**: Trivy workflow valid and self-contained (does not touch `ci.yml`).

---

## Phase 4: User Story 2 — Static code analysis of the Python codebase (P1)

**Goal**: CodeQL analyzes Python on PR/push/weekly; findings reach code scanning.
**Independent test**: Open a PR touching Python; `CodeQL` run appears, completes ≤10 min, posts results to code scanning, does not block the PR.

- [X] T005 [SYNC] [US2] Create `.github/workflows/codeql.yml`: triggers `pull_request`(main) + `push`(main) + weekly `schedule`; top-level `contents: read`; analyze job `security-events: write` (+ `actions: read`, `packages: read`); steps `actions/checkout@v4` → `github/codeql-action/init@v3` (`languages: python`, no autobuild / `build-mode: none`) → `github/codeql-action/analyze@v3` (`category: "/language:python"`); `timeout-minutes: 10` — file: `.github/workflows/codeql.yml`
- [X] T006 [P] [ASYNC] [US2] Validate `codeql.yml` parses and is schema-valid (`actionlint` or `yaml.safe_load`) — file: `.github/workflows/codeql.yml`

**Checkpoint**: CodeQL workflow valid and self-contained.

---

## Phase 5: User Story 3 — Automated dependency update proposals (P2)

**Goal**: Dependabot opens weekly update PRs for Python (uv) + GitHub Actions; security advisories raise prompt PRs.
**Independent test**: `Insights → Dependency graph → Dependabot` lists `uv` + `github-actions`; weekly cadence opens update PRs.

- [X] T007 [ASYNC] [US3] Create `.github/dependabot.yml` (`version: 2`) with two `updates` entries: (1) `package-ecosystem: "uv"`, `directory: "/"`, weekly schedule (monday), `open-pull-requests-limit: 5`; (2) `package-ecosystem: "github-actions"`, `directory: "/"`, weekly schedule (monday), `open-pull-requests-limit: 5` — file: `.github/dependabot.yml`
- [X] T008 [P] [ASYNC] [US3] Validate `dependabot.yml` parses and matches Dependabot v2 schema (`python -c "import yaml; d=yaml.safe_load(open('.github/dependabot.yml')); assert d['version']==2 and len(d['updates'])==2"`) — file: `.github/dependabot.yml`

**Checkpoint**: Dependabot config valid with both ecosystems.

---

## Phase 6: Polish & Cross-Cutting

- [X] T009 [SYNC] Verify `.github/workflows/ci.yml` is unchanged vs `origin/main` — `git diff origin/main -- .github/workflows/ci.yml` MUST be empty (INV-1 / FR-011) — file: `.github/workflows/ci.yml`
- [X] T010 [P] [ASYNC] Verify permission scoping + free-only: `security-events: write` appears only in the two new workflow files and NOT in `ci.yml` (INV-2); no paid-only actions referenced (INV-3) — files: `.github/workflows/*.yml`
- [X] T011 [SYNC] Confirm existing pipeline still passes in the worktree: `uv sync --frozen && uv run ruff check . && uv run python -m pytest tests/ -q` (FR-011 / SC-005) — files: `tests/`, `pyproject.toml`
- [X] T012 [ASYNC] Record rollout notes in the PR body / quickstart: maintainer must enable **Settings → Code security → Dependabot security updates** for FR-006; advisory rollout; fork-PR upload caveat; promotion-to-blocking is a future decision — ref: `specs/005-ci-security-scanning/quickstart.md`

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** → user stories.
- **US1 (T003–T004)**, **US2 (T005–T006)**, **US3 (T007–T008)** are mutually independent (different files) and may run in parallel after T002.
- **Polish (T009–T012)** runs after all three stories land.

```
T001 → T002 ┬─ US1: T003 → T004 ─┐
            ├─ US2: T005 → T006 ─┤→ T009 → T010 → T011 → T012
            └─ US3: T007 → T008 ─┘
```

## Parallel Opportunities

- After T002, the three story-authoring tasks touch different files → parallelizable: T003 ∥ T005 ∥ T007.
- Validation tasks T004 ∥ T006 ∥ T008 ∥ T010 (read-only, different files).

## Implementation Strategy

- **MVP = US1 + US2** (both P1): dependency/config scanning + static analysis surfacing in code scanning. Delivers the core "automated security feedback" value.
- **Increment = US3** (P2): automated update proposals.
- Advisory rollout throughout; promotion to blocking is deferred and out of scope.

## SYNC/ASYNC Summary

- **[SYNC]** (human review — security/permissions or regression-critical): T001, T002, T003, T005, T009, T011.
- **[ASYNC]** (declarative/validation, low risk): T004, T006, T007, T008, T010, T012.
