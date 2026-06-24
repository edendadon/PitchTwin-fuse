# Phase 0 Research: CI Security Scanning

All "NEEDS CLARIFICATION" items from the Technical Context are resolved below. Findings are current as of June 2026.

## Decision 1: Python dependency ecosystem for Dependabot — `uv`, not `pip`

- **Decision**: Use `package-ecosystem: "uv"` in `.github/dependabot.yml` for the Python dependencies, plus a second entry for `github-actions`.
- **Rationale**: Dependabot has **native `uv` support** (GA since March 2025). This project is uv-managed (`pyproject.toml` PEP 621 + `uv.lock`, confirmed present). The `uv` ecosystem updates both `pyproject.toml` constraints and regenerates `uv.lock`, which the generic `pip` ecosystem does not do for uv lockfiles. All dependencies in `pyproject.toml` carry version constraints (`==` or `>=`), so the known limitation — "Dependabot won't bump `uv.lock` when `pyproject.toml` has no version constraints" (dependabot-core #12273) — does **not** apply here.
- **Alternatives considered**:
  - `pip` ecosystem — reads `pyproject.toml` but does not maintain `uv.lock`; would leave the lockfile out of sync. Rejected.
  - No Python ecosystem (actions-only) — fails FR-005/FR-009. Rejected.
- **Resolves**: FR-009 (target the manifest the project actually uses) and the spec's "confirm pip/uv coverage" open item.
- **Sources**: [Dependabot supported ecosystems](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories), [Dependabot Now Supports uv](https://pydevtools.com/blog/dependabot-uv-support/), [astral uv dependency-bots guide](https://docs.astral.sh/uv/guides/integration/dependency-bots/), [dependabot-core #12273](https://github.com/dependabot/dependabot-core/issues/12273).

## Decision 2: Trivy — scan modes and SARIF upload

- **Decision**: Use `aquasecurity/trivy-action` pinned to a stable release (`@v0.36.0`, bundling Trivy ≤ v0.65.x). Run two scans: `scan-type: fs` (dependency/vuln) and `scan-type: config` (misconfiguration). Output `format: sarif` to a file, then upload with `github/codeql-action/upload-sarif@v3` guarded by `if: always()`.
- **Rationale**: `fs` covers the lockfile/dependency CVEs; `config` covers IaC/Dockerfile/YAML misconfigurations. SARIF upload routes findings into the central code-scanning dashboard (FR-004). `if: always()` ensures findings upload even if a later step is configured to fail. Pinning below the v0.34.0 trivy-action (which bumped bundled Trivy to v0.69.1) avoids the documented SARIF-upload regression.
- **Known risks / mitigations**:
  - *SARIF upload failures on certain bundled Trivy versions* (trivy-action #408, trivy #10196) → pin to a known-good trivy-action release.
  - *Non-existent file paths in SARIF causing fingerprint failures* (trivy-action #471) → use `fs` scan from repo root so paths resolve; keep advisory so a transient upload hiccup never blocks merges.
  - *Fork PRs lack `security-events: write`* → upload step tolerates restricted permission; scan still runs (FR-008, edge case).
- **Alternatives considered**: Trivy `image` scan (no container image is built here — N/A); running Trivy as a job inside `ci.yml` (would couple elevated permissions to the lint/test job — rejected per FR-008).
- **Sources**: [aquasecurity/trivy-action](https://github.com/aquasecurity/trivy-action), [Code Scanning (SARIF) docs](https://deepwiki.com/aquasecurity/trivy-action/5.1.1-code-scanning-(sarif)), [trivy-action #471](https://github.com/aquasecurity/trivy-action/issues/471).

## Decision 3: CodeQL — language and build mode

- **Decision**: Use `github/codeql-action` v3 with `languages: python` and **no autobuild step** (Python is interpreted; `build-mode: none` / skip autobuild). Steps: `init` → `analyze`.
- **Rationale**: Python requires no compilation, so autobuild is a no-op and only adds time. CodeQL is free for public repositories via GitHub code scanning. Default query suite (`security-extended` optional) gives security coverage for FR-002.
- **Alternatives considered**: Including `autobuild` — unnecessary for Python; removed for speed. `security-and-quality` query suite — broader but noisier; start with default to keep the advisory backlog manageable.
- **Sources**: [github/codeql-action](https://github.com/github/codeql-action), [CodeQL code scanning docs](https://docs.github.com/en/code-security/code-scanning).

## Decision 4: Triggers, schedule, and rollout mode

- **Decision**: Both scanners trigger on `pull_request` (branches: `main`), `push` (branches: `main`), and a weekly `schedule` (cron, fixed day/time). Rollout is advisory: no `exit-code: 1` on Trivy; CodeQL findings are non-blocking by default (code scanning does not fail the job unless a check is configured to require it).
- **Rationale**: Matches FR-001/FR-002/FR-003 and SC-003 (≤ 7-day detection of new advisories). Advisory mode mirrors the existing `ruff` `continue-on-error` step (FR-007) and avoids blocking merges on a pre-existing finding backlog.
- **Cron note**: `Date.now()`-style nondeterminism is irrelevant; a fixed weekly cron (e.g. `'17 4 * * 1'`) is used. Avoid `0 0` to dodge peak scheduling contention.

## Decision 5: Permissions model

- **Decision**: Each new workflow declares top-level `permissions: contents: read` and grants `security-events: write` (plus `actions: read` where required by CodeQL) only on the scanning job. Existing `ci.yml` is untouched.
- **Rationale**: FR-008 (minimum-necessary, no broadening of existing job) and FR-011 (don't break existing pipeline). SARIF upload requires `security-events: write`; nothing else needs elevation.
- **Sources**: [Uploading SARIF — permissions](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github).
