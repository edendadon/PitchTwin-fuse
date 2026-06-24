# Quickstart: Verifying CI Security Scanning

How to confirm the feature works after the workflows/config land on a branch.

## Prerequisites
- Branch pushed to a GitHub repo where Actions + code scanning are enabled (free for public repos).
- For Dependabot security updates: a maintainer enables **Settings → Code security → Dependabot** (one-time).

## 1. Validate YAML locally (before pushing)
```bash
# From repo root. actionlint catches workflow schema/syntax errors.
actionlint .github/workflows/codeql.yml .github/workflows/trivy.yml   # if installed
# Dependabot config is YAML; a basic parse check:
python -c "import yaml,sys; yaml.safe_load(open('.github/dependabot.yml')); print('dependabot.yml OK')"
```

## 2. Confirm the existing pipeline is untouched
```bash
git diff --stat origin/main -- .github/workflows/ci.yml   # MUST be empty (INV-1)
```

## 3. Trigger the scanners
- Open a PR to `main`. Expected: **CodeQL** and **Trivy** workflow runs appear in the Actions tab alongside the existing **CI** run.
- Both should complete in ≤ 10 min (SC-007) and **not** fail the PR on findings (advisory — FR-007).

## 4. Confirm findings reach the central dashboard
- Repo → **Security → Code scanning**. Expect results categorized as `python` (CodeQL), `trivy-fs`, and `trivy-config` after the first run completes (FR-004, SC-002).

## 5. Confirm the weekly schedule is registered
- Repo → **Actions → CodeQL / Trivy → ⋯** shows a scheduled trigger. (Scheduled runs only fire on the default branch once merged.)

## 6. Confirm Dependabot
- Repo → **Insights → Dependency graph → Dependabot**: two ecosystems listed (`uv`, `github-actions`).
- On the weekly cadence (or via "Check for updates"), Dependabot opens update PRs (FR-005). Security advisories raise PRs promptly (FR-006).

## Success checklist
- [ ] `ci.yml` unchanged vs `origin/main`
- [ ] CodeQL run green + results in code scanning
- [ ] Trivy run green + `trivy-fs` / `trivy-config` results in code scanning
- [ ] No PR blocked by a security finding (advisory)
- [ ] Dependabot lists `uv` + `github-actions`
- [ ] $0 cost (public-repo free features only)
