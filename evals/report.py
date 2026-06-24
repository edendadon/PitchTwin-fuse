"""
Baselines and regression detection (User Story 2).

A baseline is a committed snapshot of an agent's per-case pass/fail at a known-
good point (evals/baselines/current/<agent>.json). On later runs the framework
compares against it and labels REGRESSIONS — cases that passed in the baseline
but fail now.

Exit policy (per spec FR-009/FR-012): hard gates always bind — any FAIL fails the
run. The baseline adds regression *labelling* (which failures are new) and the
explicit `--update-baseline` capture; it does not relax the gate.

All functions operate on plain result dicts (the shape recorded in
evals/results.py), so the regression logic is unit-testable offline with no LLM.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASELINE_DIR = Path(__file__).parent / "baselines" / "current"

MIN_CASES = 5  # every agent must have at least this many golden cases (FR-016)


def coverage_failures(agents: list[str], counts: dict[str, int], min_cases: int = MIN_CASES) -> list[str]:
    """Agents (among `agents`) that have fewer than `min_cases` golden cases."""
    return [a for a in agents if counts.get(a, 0) < min_cases]


def _baseline_path(agent: str) -> Path:
    return BASELINE_DIR / f"{agent}.json"


def group_by_agent(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["agent"], []).append(r)
    return grouped


def load_baseline(agent: str) -> dict[str, Any] | None:
    path = _baseline_path(agent)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_baseline(agent: str, agent_results: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Capture (or refresh) the baseline for one agent from its current results."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    data = {
        "agent": agent,
        "captured_at": stamp,
        "cases": {r["case_id"]: {"passed": r["status"] == "PASS"} for r in agent_results},
    }
    _baseline_path(agent).write_text(json.dumps(data, indent=2) + "\n")
    return data


def compute_regressions(agent_results: list[dict[str, Any]], baseline: dict[str, Any] | None) -> list[str]:
    """Case ids that passed in the baseline but do not pass now.

    No baseline (first run) → no regressions.
    """
    if not baseline:
        return []
    base_cases = baseline.get("cases", {})
    regressions: list[str] = []
    for r in agent_results:
        was_passing = base_cases.get(r["case_id"], {}).get("passed") is True
        passing_now = r["status"] == "PASS"
        if was_passing and not passing_now:
            regressions.append(r["case_id"])
    return regressions


def has_infra_error(agent_results: list[dict[str, Any]]) -> bool:
    return any(r["status"] == "ERROR" for r in agent_results)
