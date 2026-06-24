"""
pytest plumbing for the eval suite.

Parametrizes the `case` fixture with golden cases for the selected agent(s), read
from the EVALS_AGENTS env var (set by run.py; empty => all registered). Each test
writes its own per-case result file (see evals/results.py), so the suite is safe
under pytest-xdist parallelism — run.py clears the dir before and reads it after.
"""

from __future__ import annotations

import os

from evals.harness import load_cases


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        env = os.environ.get("EVALS_AGENTS", "").strip()
        agents = [a for a in env.split(",") if a] or None
        cases = load_cases(agents)
        metafunc.parametrize("case", cases, ids=[f"{c.agent}:{c.id}" for c in cases])
