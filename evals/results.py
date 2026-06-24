"""
Per-case result collection — written as one JSON file per (agent, case).

Writing a file per case (rather than accumulating in process memory) makes the
runner safe under pytest-xdist, where each case may run in a separate worker
process. `run.py` clears the directory before a run and reads every file after.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).parent / ".reports" / "cases"


def cases_dir() -> Path:
    return Path(os.environ.get("EVALS_CASES_DIR", str(DEFAULT_DIR)))


def reset() -> None:
    """Remove any prior per-case result files."""
    d = cases_dir()
    if d.exists():
        for f in d.glob("*.json"):
            f.unlink()


def write_case(agent: str, case_id: str, status: str, verdicts: list[dict[str, Any]]) -> None:
    d = cases_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{agent}__{case_id}.json").write_text(
        json.dumps(
            {"agent": agent, "case_id": case_id, "status": status, "verdicts": verdicts},
            indent=2,
        )
    )


def read_all() -> list[dict[str, Any]]:
    d = cases_dir()
    if not d.exists():
        return []
    return [json.loads(f.read_text()) for f in sorted(d.glob("*.json"))]
