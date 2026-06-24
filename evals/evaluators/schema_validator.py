"""
schema_validator — deterministic Pydantic validation of agent output.

PASS  : output validates against the agent's Pydantic OutputSchema.
FAIL  : validation error (field path + message in evidence).
SKIP  : agent has no structured schema (e.g. persona / free text).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from evals.evaluators.base import GoldenCase, Status, Verdict

NAME = "schema"


def evaluate(case: GoldenCase, output: Any) -> Verdict:
    # Lazy import to avoid importing agent modules at framework import time.
    from evals.harness import get_output_schema

    schema = get_output_schema(case.agent)
    if schema is None:
        return Verdict(
            evaluator=NAME,
            status=Status.SKIP,
            reason=f"agent '{case.agent}' has no structured output schema",
        )

    try:
        schema.model_validate(output)
    except ValidationError as exc:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        return Verdict(
            evaluator=NAME,
            status=Status.FAIL,
            reason=f"output failed {schema.__name__} validation at '{loc}': {first.get('msg', '')}",
            evidence={"errors": errors[:10]},
        )
    return Verdict(evaluator=NAME, status=Status.PASS, reason=f"valid {schema.__name__}")
