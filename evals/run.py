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

from evals import report as rpt
from evals.harness import AGENT_NAMES, count_cases, registered_agents

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


def _summarize(results: list[dict], *, update_baseline: bool) -> tuple[int, str]:
    n = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    any_infra = any(r["status"] == "ERROR" for r in results)
    any_fail = any(r["status"] == "FAIL" for r in results)

    grouped = rpt.group_by_agent(results)
    regressions: list[str] = []   # "agent:case"
    captured: list[str] = []      # agents whose baseline was (re)written

    skipped_capture: list[str] = []   # agents not captured because the run wasn't clean
    for agent, ares in grouped.items():
        if update_baseline:
            # Only baseline a CLEAN run — refuse to rubber-stamp failures/errors.
            if any(r["status"] != "PASS" for r in ares):
                skipped_capture.append(agent)
                continue
            rpt.write_baseline(agent, ares)
            captured.append(agent)
            continue
        baseline = rpt.load_baseline(agent)
        if baseline is None:
            if not rpt.has_infra_error(ares):
                rpt.write_baseline(agent, ares)  # first run: auto-capture, no false regression
                captured.append(agent)
        else:
            regressions += [f"{agent}:{c}" for c in rpt.compute_regressions(ares, baseline)]

    lines = [f"\nEval results: {passed}/{n} passed"]
    for r in results:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR "}[r["status"]]
        reg = "  <-- REGRESSION" if f"{r['agent']}:{r['case_id']}" in regressions else ""
        lines.append(f"  [{mark}] {r['agent']}:{r['case_id']}{reg}")
        if r["status"] != "PASS":
            for v in r["verdicts"]:
                if v["status"] in ("FAIL", "ERROR"):
                    lines.append(f"          {v['evaluator']}: {v['reason']}")

    if update_baseline:
        lines.append(f"\nBaseline updated for: {', '.join(captured) or '(none)'}")
        if skipped_capture:
            lines.append(
                f"NOT captured (run had failures — fix first): {', '.join(skipped_capture)}"
            )
        if any_infra:
            return EXIT_INFRA, "\n".join(lines)
        if any_fail:
            return EXIT_FAIL, "\n".join(lines)
        return EXIT_OK, "\n".join(lines)

    if captured:
        lines.append(f"\nCaptured initial baseline for: {', '.join(captured)}")
    if regressions:
        lines.append(f"REGRESSIONS ({len(regressions)}): {', '.join(regressions)}")

    if any_infra:
        lines.append("\nINFRASTRUCTURE ERROR — not a quality verdict.")
        return EXIT_INFRA, "\n".join(lines)
    if any_fail:
        note = " (includes regressions)" if regressions else ""
        lines.append(f"\nFAILED — hard gate failure{note}.")
        return EXIT_FAIL, "\n".join(lines)
    lines.append("\nPASSED — all hard gates green.")
    return EXIT_OK, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    agents = registered_agents() if args.all else [args.agent]

    if not agents:
        print("[evals] no registered agents to evaluate.", file=sys.stderr)
        return EXIT_USAGE

    # Coverage gate (FR-016): every selected agent must have >= MIN_CASES golden
    # cases. Checked before invoking the model so it is fast and free.
    counts = count_cases()
    short = rpt.coverage_failures(agents, counts)
    if short:
        print(f"\nCOVERAGE FAILURE: agent(s) with < {rpt.MIN_CASES} golden cases:")
        for a in short:
            print(f"  {a}: {counts.get(a, 0)} case(s)")
        return EXIT_COVERAGE

    _run_pytest(agents, args.samples)

    if not REPORT_PATH.exists():
        print("[evals] no report produced (collection error?).", file=sys.stderr)
        return EXIT_INFRA
    report = json.loads(REPORT_PATH.read_text())

    if args.json_out:
        shutil.copyfile(REPORT_PATH, args.json_out)

    code, summary = _summarize(report.get("results", []), update_baseline=args.update_baseline)
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
