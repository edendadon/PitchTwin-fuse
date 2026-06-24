# Feature Specification: CI Security Scanning (Trivy + CodeQL + Dependabot)

**Feature Branch**: `005-ci-security-scanning`

**Created**: 2026-06-24

**Status**: Draft

**Input**: GitHub issue #22 — "ci: add Trivy, CodeQL, and Dependabot security scanning (all free for public repo)"

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the repository's maintainers and contributors. The value is automated, continuous security feedback that surfaces in one place without anyone having to remember to run scanners by hand. The repository is public, so every capability below is available at no cost.

### User Story 1 - Dependency & configuration vulnerability scanning (Priority: P1)

As a maintainer, when a pull request is opened or code is pushed to `main`, I want the project's dependencies and configuration files scanned for known vulnerabilities and misconfigurations, so that a contribution introducing a vulnerable package or insecure setting is flagged before it merges.

**Why this priority**: Dependency CVEs are the most common and highest-impact source of risk for a small Python project, and this catches them at the point of change. Delivers standalone value even if the other two stories are never built.

**Independent Test**: Open a PR that adds a dependency with a known CVE (or a config with a known misconfiguration); confirm the scan runs in CI and the finding appears in the repository's central security dashboard.

**Acceptance Scenarios**:

1. **Given** a pull request targeting `main`, **When** CI runs, **Then** a vulnerability/misconfiguration scan executes and its results are uploaded to the repository's central security findings view.
2. **Given** a push to `main`, **When** CI runs, **Then** the same scan executes and reports findings.
3. **Given** the scan finds a vulnerability, **When** the rollout is in advisory mode, **Then** the finding is recorded but the CI run is not failed/blocked.
4. **Given** no code change occurs for several days, **When** the recurring weekly scan fires, **Then** newly-disclosed vulnerabilities in unchanged dependencies are still detected.

---

### User Story 2 - Static code analysis of the Python codebase (Priority: P1)

As a maintainer, I want the Python source analyzed for code-level security weaknesses (e.g., injection, unsafe deserialization, hard-coded secrets patterns) whenever code changes, so that insecure code is caught at review time rather than in production.

**Why this priority**: Complements dependency scanning by covering first-party code rather than third-party packages. Together with Story 1 it gives full coverage of "vulnerable dependency" and "vulnerable code". Independently valuable.

**Independent Test**: Introduce a deliberately insecure code pattern on a branch, open a PR, and confirm the static analysis flags it in the central security dashboard.

**Acceptance Scenarios**:

1. **Given** a pull request that modifies Python source, **When** CI runs, **Then** static security analysis executes against the Python code and uploads results to the central security findings view.
2. **Given** a push to `main`, **When** CI runs, **Then** static analysis executes and reports findings.
3. **Given** no code change for several days, **When** the recurring weekly analysis fires, **Then** the codebase is re-analyzed against updated rule sets.

---

### User Story 3 - Automated dependency update proposals (Priority: P2)

As a maintainer, I want outdated dependencies — both the project's Python packages and the versions of the CI building blocks themselves — to generate automated update proposals on a regular cadence, and security-critical updates to be proposed promptly, so that the project stays current without manual tracking.

**Why this priority**: Reduces long-term maintenance burden and shrinks the window of exposure to disclosed vulnerabilities, but is lower urgency than detecting existing vulnerabilities. Builds naturally on Stories 1–2.

**Independent Test**: Confirm that, on the configured cadence, the system opens update proposals for known-outdated CI components and Python dependencies, and that a dependency with a published security advisory triggers a proposal.

**Acceptance Scenarios**:

1. **Given** an outdated CI building-block version, **When** the weekly cadence fires, **Then** an update proposal is opened automatically.
2. **Given** an outdated Python dependency, **When** the weekly cadence fires, **Then** an update proposal is opened automatically.
3. **Given** a dependency with a published security advisory, **When** the advisory is detected, **Then** a security update proposal is raised.

### Edge Cases

- **Existing pipeline unaffected**: Adding scans MUST NOT break the current lint + test pipeline; in advisory mode a finding does not fail the build.
- **uv-based dependency manifest**: The project manages Python dependencies with uv (`pyproject.toml` + `uv.lock`) rather than `requirements.txt`. The update-proposal ecosystem must be configured to read the manifest the project actually uses; if native support is partial, the chosen configuration must be documented.
- **Permissions**: Jobs that publish findings to the central security view require elevated write permission for security events; the current pipeline only grants read access, so the new jobs must request the additional scope without broadening the existing job's permissions.
- **Fork / external PRs**: Findings-upload from PRs originating in forks may have restricted permissions; behavior in that case should degrade gracefully (scan still runs; upload may be skipped) rather than error the build.
- **Duplicate / noisy findings**: First rollout is advisory to avoid blocking merges on pre-existing findings before the backlog is triaged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CI MUST scan project dependencies and configuration files for known vulnerabilities and misconfigurations on every pull request targeting `main` and every push to `main`.
- **FR-002**: The CI MUST perform static security analysis of the Python codebase on every pull request targeting `main` and every push to `main`.
- **FR-003**: The system MUST run both the dependency scan and the static analysis on a recurring weekly schedule, independent of code changes, so vulnerabilities disclosed against unchanged code are detected within 7 days.
- **FR-004**: Findings from both the dependency scan and the static analysis MUST be published to the repository's central, deduplicated security findings view (rather than only living in raw build logs).
- **FR-005**: The system MUST automatically propose dependency updates for the CI building blocks and for the project's Python dependencies on a weekly cadence.
- **FR-006**: The system MUST raise prompt update proposals for dependencies covered by a published security advisory.
- **FR-007**: On initial rollout, scan findings MUST be advisory (non-blocking) — a finding records to the security view but does not fail the CI run — mirroring the existing advisory lint step.
- **FR-008**: Jobs that publish findings MUST request only the minimum additional permission required (write access for security events) and MUST NOT broaden permissions of the existing lint/test job.
- **FR-009**: The dependency-update configuration MUST target the dependency manifest the project actually uses (uv-managed `pyproject.toml` / `uv.lock`); any limitation in native support MUST be documented in the feature.
- **FR-010**: All capabilities MUST be implemented using only no-cost features available to a public repository; nothing requiring a paid plan may be introduced.
- **FR-011**: Adding these capabilities MUST NOT remove, weaken, or break the repository's existing lint and test pipeline.

### Key Entities *(include if feature involves data)*

- **Security finding**: A single detected issue (vulnerability, misconfiguration, or code weakness) with a severity, a location, and a source scanner; aggregated and deduplicated in the central security view.
- **Dependency update proposal**: An automated change proposal to move a CI component or Python dependency from a current version to a newer (or security-fixed) version.
- **Scan run**: One execution of a scanner, triggered by a pull request, a push to `main`, or the weekly schedule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pull requests targeting `main` and pushes to `main` trigger both the dependency scan and the static code analysis.
- **SC-002**: Findings from both scanners are visible in a single central security view within one CI run, with no manual log-reading required.
- **SC-003**: Both scanners also run on a weekly schedule, so a newly-disclosed vulnerability in unchanged code is detected within 7 days.
- **SC-004**: Outdated CI components and Python dependencies produce automated update proposals on a weekly cadence with zero manual intervention.
- **SC-005**: Introducing the scans causes 0 regressions in the existing lint + test pipeline, and in advisory mode 0 builds are failed solely due to a security finding.
- **SC-006**: Total incremental CI cost is $0 (all capabilities use free public-repository features).
- **SC-007**: Each scan job completes within the project's existing CI time budget (≤ 10 minutes per job).

## Assumptions

- **Tooling choice**: The dependency/config scan is implemented with **Trivy** (`aquasecurity/trivy-action`), the static analysis with **GitHub CodeQL**, and update proposals with **Dependabot** — the three tools named in issue #22. All are free for public repositories.
- **Central security view**: The "central security findings view" is GitHub code scanning (the repository **Security → Code scanning** tab); scanners upload results in SARIF.
- **Language scope**: Static analysis targets Python only (the project's primary language). No compiled-language build step is required.
- **Dependabot ecosystems**: Configuration covers the `github-actions` ecosystem and the Python dependency ecosystem. The project uses uv; Dependabot's `pip` ecosystem reads PEP 621 `pyproject.toml`. If `uv.lock` is not natively honored, version resolution falls back to manifest constraints and this limitation is documented.
- **Schedule cadence**: "Weekly" is the cadence for both the scheduled scans and Dependabot, unless maintainers later tune it.
- **Rollout mode**: Findings are advisory (non-blocking) for the initial rollout, consistent with the existing `ruff` lint step being `continue-on-error`. Promotion to blocking is a separate future decision after the finding backlog is triaged.
- **Worktree discipline**: Implementation happens in the isolated worktree on `005-ci-security-scanning`, branched from `origin/main`, per the project working agreement.
- **Publishing constraint**: The authenticated local account lacks push access to `edendadon/PitchTwin-fuse`; the resulting PR will be opened from a fork. This affects delivery, not the feature design.
