# Contract: `.github/workflows/codeql.yml`

## Trigger contract
- `pull_request` → branches: `[main]`
- `push` → branches: `[main]`
- `schedule` → one weekly cron (fixed, e.g. `'17 4 * * 1'`)

## Permissions contract
- Top-level: `contents: read`
- Analyze job: `security-events: write`, `packages: read`, `actions: read`

## Job contract
- Runs on `ubuntu-latest`, `timeout-minutes: 10`.
- Matrix language: `python` only.
- Steps: `actions/checkout@v4` → `github/codeql-action/init@v3` (with `languages: python`, no autobuild) → `github/codeql-action/analyze@v3` (category `/language:python`).
- **No** `autobuild` step (Python is interpreted).

## Behavioral contract
- Advisory: the analyze step does not fail the job on findings; results post to code scanning.
- MUST NOT reference `ci.yml` or alter the lint/test job.

## Acceptance (maps to spec)
- Satisfies FR-002, FR-003 (schedule), FR-004 (SARIF→code scanning), FR-007 (advisory), FR-008 (scoped permission), FR-010 (free).
