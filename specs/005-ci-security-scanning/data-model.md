# Phase 1 Data Model: CI Security Scanning

This feature has no application data model. The "entities" are configuration artifacts and the conceptual records they produce. Documented here for completeness.

## Configuration Artifacts (files created)

| Artifact | Path | Type | Purpose |
|----------|------|------|---------|
| CodeQL workflow | `.github/workflows/codeql.yml` | GitHub Actions workflow | Static analysis of Python → code scanning |
| Trivy workflow | `.github/workflows/trivy.yml` | GitHub Actions workflow | Dependency + config scan → code scanning |
| Dependabot config | `.github/dependabot.yml` | Dependabot v2 config | Weekly update proposals (uv + github-actions) |
| Existing CI (unchanged) | `.github/workflows/ci.yml` | GitHub Actions workflow | ruff lint (continue-on-error) + pytest — **must remain byte-for-byte unchanged** |

## Conceptual Records

### Security finding
- **source**: `trivy` | `codeql`
- **severity**: critical | high | medium | low | informational
- **location**: file path + line range (or dependency coordinate)
- **rule_id**: scanner rule identifier
- **state**: open | dismissed | fixed (managed by GitHub code scanning)
- **Lifecycle**: produced by a scan run → uploaded as SARIF → deduplicated/aggregated in the repository **Security → Code scanning** view.

### Dependency update proposal
- **ecosystem**: `uv` | `github-actions`
- **dependency**: package/action name
- **from_version** → **to_version**
- **reason**: scheduled (weekly) | security-advisory
- **Lifecycle**: opened automatically by Dependabot as a pull request on the weekly cadence (or promptly for security advisories).

### Scan run
- **trigger**: pull_request | push(main) | schedule(weekly)
- **scanner**: trivy(fs) | trivy(config) | codeql(python)
- **result**: SARIF file uploaded to code scanning
- **blocking**: false (advisory rollout — FR-007)

## Validation / Invariants

- INV-1: New workflows MUST NOT modify `ci.yml` (FR-011). Verified by diffing the file against `origin/main`.
- INV-2: `security-events: write` appears ONLY in the new scanning workflows, never added to the existing lint/test job (FR-008).
- INV-3: No paid feature is referenced; all actions are free for public repos (FR-010).
- INV-4: Dependabot Python ecosystem MUST be `uv` (matches `pyproject.toml` + `uv.lock`) (FR-009).
- INV-5: Both scanners MUST register `pull_request`, `push:main`, and `schedule` triggers (FR-001/002/003).
