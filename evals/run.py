"""
Eval runner CLI — the constitutional entry point (Principle V).

    python -m evals.run --agent <name>
    python -m evals.run --all
    python -m evals.run --agent matching --samples 3 --json out.json

Wraps pytest as the execution engine, then computes the aggregate exit code from
the JSON report the eval conftest writes.

Exit codes (see contracts/cli.md):
  0  all gates pass, no regressions, coverage satisfied
  1  a hard-gate FAIL (or regression — wired in US2)
  2  coverage failure (wired in US3)
  3  infrastructure ERROR (provider unreachable / no credentials)
  4  usage error
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from evals.harness import AGENT_NAMES, registered_agents

EVALS_DIR = Path(__file__).parent
REPORT_PATH = EVALS_DIR / ".reports" / "last_run.json"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_COVERAGE = 2
EXIT_INFRA = 3
EXIT_USAGE = 4


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m evals.run", description="PitchTwin agent evals")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--agent", help="agent to evaluate", choices=AGENT_NAMES)
    sel.add_argument("--all", action="store_true", help="evaluate all registered agents")
    p.add_argument("--update-baseline", action="store_true", help="(US2) capture/refresh baseline")
    p.add_argument("--samples", type=int, default=1, help="LLM-judge samples (majority vote)")
    p.add_argument("--json", dest="json_out", help="also write the JSON report to this path")
    return p.parse_args(argv)


def _run_pytest(agents: list[str], samples: int) -> None:
    os.environ["EVALS_AGENTS"] = ",".join(agents)
    os.environ["EVALS_REPORT_PATH"] = str(REPORT_PATH)
    os.environ["EVALS_SAMPLES"] = str(samples)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    pytest.main(["-q", "-p", "no:cacheprovider", str(EVALS_DIR / "test_eval.py")])


def _summarize(report: dict) -> tuple[int, str]:
    res = report.get("results", [])
    n = len(res)
    passed = [r for r in res if r["status"] == "PASS"]
    failed = [r for r in res if r["status"] == "FAIL"]
    errored = [r for r in res if r["status"] == "ERROR"]

    lines = [f"\nEval results: {len(passed)}/{n} passed"]
    for r in res:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR "}[r["status"]]
        lines.append(f"  [{mark}] {r['agent']}:{r['case_id']}")
        if r["status"] != "PASS":
            for v in r["verdicts"]:
                if v["status"] in ("FAIL", "ERROR"):
                    lines.append(f"          {v['evaluator']}: {v['reason']}")

    if errored:
        lines.append(f"\nINFRASTRUCTURE ERROR ({len(errored)} case(s)) — not a quality verdict.")
        return EXIT_INFRA, "\n".join(lines)
    if failed:
        lines.append(f"\nFAILED — {len(failed)} case(s) failed a hard gate.")
        return EXIT_FAIL, "\n".join(lines)
    lines.append("\nPASSED — all hard gates green.")
    return EXIT_OK, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    agents = registered_agents() if args.all else [args.agent]

    if args.update_baseline:
        print("[evals] --update-baseline is not implemented in this MVP (US2).", file=sys.stderr)

    if not agents:
        print("[evals] no registered agents to evaluate.", file=sys.stderr)
        return EXIT_USAGE

    _run_pytest(agents, args.samples)

    if not REPORT_PATH.exists():
        print("[evals] no report produced (collection error?).", file=sys.stderr)
        return EXIT_INFRA
    report = json.loads(REPORT_PATH.read_text())

    if args.json_out:
        shutil.copyfile(REPORT_PATH, args.json_out)

    code, summary = _summarize(report)
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
