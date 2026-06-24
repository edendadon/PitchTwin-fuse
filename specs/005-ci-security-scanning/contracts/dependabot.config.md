# Contract: `.github/dependabot.yml`

## Schema contract
- `version: 2`
- `updates:` array with two entries.

### Entry 1 — Python dependencies (uv)
- `package-ecosystem: "uv"`
- `directory: "/"` (where `pyproject.toml` + `uv.lock` live)
- `schedule: { interval: "weekly", day: "monday" }`
- `open-pull-requests-limit: 5`
- Optional: `groups` to batch minor/patch updates and reduce PR noise.

### Entry 2 — GitHub Actions
- `package-ecosystem: "github-actions"`
- `directory: "/"` (scans `.github/workflows/*`)
- `schedule: { interval: "weekly", day: "monday" }`
- `open-pull-requests-limit: 5`

## Behavioral contract
- Weekly scheduled version-update PRs for both ecosystems (FR-005).
- Security updates: Dependabot security updates are raised promptly for advisories independent of the weekly schedule (FR-006) — enabled at repo level (Settings → Code security), no config key required.
- `uv` ecosystem updates both `pyproject.toml` constraints and `uv.lock` (FR-009). Project deps carry version constraints, so lockfile bumps work.

## Acceptance (maps to spec)
- Satisfies FR-005, FR-006, FR-009, FR-010 (free).

## Note for maintainers
- FR-006 "security updates" relies on repository setting **Settings → Code security → Dependabot security updates = enabled**. This is a one-click repo setting outside the config file; document it in the PR body so a maintainer with admin access can toggle it.
