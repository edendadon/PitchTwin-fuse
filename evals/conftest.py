"""
pytest plumbing for the eval suite.

- Parametrizes the `case` fixture with golden cases for the selected agent(s),
  read from the EVALS_AGENTS env var (set by run.py; empty => all registered).
- At session finish, writes the accumulated per-case results to the JSON path in
  EVALS_REPORT_PATH (set by run.py) so the runner can compute the exit code.

No third-party reporting plugin needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from evals import results
from evals.harness import load_cases


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        env = os.environ.get("EVALS_AGENTS", "").strip()
        agents = [a for a in env.split(",") if a] or None
        cases = load_cases(agents)
        metafunc.parametrize(
            "case", cases, ids=[f"{c.agent}:{c.id}" for c in cases]
        )


def pytest_sessionstart(session):
    results.reset()


def pytest_sessionfinish(session, exitstatus):
    report_path = os.environ.get("EVALS_REPORT_PATH")
    if not report_path:
        return
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"results": results.RESULTS}, indent=2))
