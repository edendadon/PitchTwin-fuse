"""
Parametrized hard-gate test: for each (agent, golden case), invoke the agent via
the registry and apply the three evaluators as hard gates.

Run via the CLI: `python -m evals.run --agent <name>` (which sets EVALS_AGENTS and
EVALS_REPORT_PATH and calls pytest on this file).
"""

from __future__ import annotations

import pytest

from evals import results
from evals.evaluators import (
    factual_consistency,
    hallucination_detector,
    schema_validator,
)
from evals.evaluators.base import InfraError, Status, Verdict
from evals.harness import AGENT_REGISTRY

EVALUATORS = (schema_validator, factual_consistency, hallucination_detector)


def test_eval_case(case):
    entry = AGENT_REGISTRY.get(case.agent)
    if entry is None:
        pytest.skip(f"agent '{case.agent}' not registered yet")

    # --- invoke the agent (infra failures are distinct from gate failures) ---
    try:
        output = entry.invoke(case)
    except InfraError as exc:
        results.write_case(
            case.agent, case.id, Status.ERROR.value,
            [{"evaluator": "invoke", "status": "ERROR", "reason": str(exc)}],
        )
        pytest.fail(f"INFRA ERROR invoking {case.agent}:{case.id}: {exc}", pytrace=False)

    # --- apply the three hard gates ---
    verdicts: list[Verdict] = []
    for ev in EVALUATORS:
        try:
            verdicts.append(ev.evaluate(case, output))
        except InfraError as exc:
            verdicts.append(Verdict(evaluator=ev.NAME, status=Status.ERROR, reason=str(exc)))

    has_error = any(v.status == Status.ERROR for v in verdicts)
    failed = [v for v in verdicts if v.status == Status.FAIL]
    status = Status.ERROR if has_error else (Status.FAIL if failed else Status.PASS)

    results.write_case(
        case.agent, case.id, status.value,
        [v.model_dump(mode="json") for v in verdicts],
    )

    if has_error:
        errs = [v for v in verdicts if v.status == Status.ERROR]
        pytest.fail(
            f"INFRA ERROR in gates for {case.agent}:{case.id}: "
            + "; ".join(f"{v.evaluator}: {v.reason}" for v in errs),
            pytrace=False,
        )

    assert not failed, "Hard gate(s) failed for {}:{}:\n{}".format(
        case.agent,
        case.id,
        "\n".join(f"  [{v.evaluator}] {v.reason}" for v in failed),
    )
