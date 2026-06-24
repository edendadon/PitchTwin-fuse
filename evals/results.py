"""
Process-local accumulator for per-case results.

`test_eval.py` appends a CaseResult here as each parametrized case runs; the
eval `conftest.py` writes the accumulated results to a JSON report at session
finish, and `run.py` reads that report to compute the aggregate exit code.
"""

from __future__ import annotations

from typing import Any

RESULTS: list[dict[str, Any]] = []


def reset() -> None:
    RESULTS.clear()


def record(agent: str, case_id: str, status: str, verdicts: list[dict[str, Any]]) -> None:
    RESULTS.append(
        {
            "agent": agent,
            "case_id": case_id,
            "status": status,  # PASS | FAIL | ERROR
            "verdicts": verdicts,
        }
    )
