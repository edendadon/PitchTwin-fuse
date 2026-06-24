# Contract: `.github/workflows/trivy.yml`

## Trigger contract
- `pull_request` → branches: `[main]`
- `push` → branches: `[main]`
- `schedule` → one weekly cron (fixed, e.g. `'31 4 * * 1'`, offset from CodeQL)

## Permissions contract
- Top-level: `contents: read`
- Scan job: `security-events: write` (for SARIF upload)

## Job contract
- Runs on `ubuntu-latest`, `timeout-minutes: 10`.
- Steps:
  1. `actions/checkout@v4`
  2. `aquasecurity/trivy-action@0.33.1` — `scan-type: fs`, `scanners: vuln,secret`, `format: sarif`, `output: trivy-fs.sarif`, `exit-code: 0` (advisory), `ignore-unfixed: true`.
  3. `github/codeql-action/upload-sarif@v3` — `sarif_file: trivy-fs.sarif`, `category: trivy-fs`, `if: always()`.
  4. `aquasecurity/trivy-action@0.33.1` — `scan-type: config`, `format: sarif`, `output: trivy-config.sarif`, `exit-code: 0`.
  5. `github/codeql-action/upload-sarif@v3` — `sarif_file: trivy-config.sarif`, `category: trivy-config`, `if: always()`.

## Behavioral contract
- Advisory: `exit-code: 0` so findings never fail the build (FR-007).
- Two SARIF categories (`trivy-fs`, `trivy-config`) keep results distinct in code scanning.
- `if: always()` guarantees upload even if the scan step reports findings.
- Tolerates restricted fork-PR permissions (upload may no-op; scan still runs).
- MUST NOT reference `ci.yml`.

## Acceptance (maps to spec)
- Satisfies FR-001, FR-003 (schedule), FR-004 (SARIF→code scanning), FR-007 (advisory), FR-008 (scoped permission), FR-010 (free).
