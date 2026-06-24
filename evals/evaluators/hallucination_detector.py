"""
hallucination_detector — LLM-judge grounding gate (spec FR-006, Principle IV).

A judge model is asked whether every factual claim in the agent output is
supported by the case `source`. The judge is injectable (`judge=` kwarg) so the
meta-tests run fully offline with a deterministic stub; the default judge is a
pydantic-ai Agent at temperature 0.

PASS  : grounded and no fabricated claims (an honest "not in my background"
        declination counts as grounded — see `must_decline`).
FAIL  : ungrounded / fabricated claims listed in evidence.
ERROR : judge model unreachable (InfraError) — never a pass.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from pydantic import BaseModel

from evals.evaluators.base import GoldenCase, InfraError, Status, Verdict

NAME = "hallucination"

JUDGE_SYSTEM = """You are a grounding auditor for a consulting-proposal AI.

You receive a SOURCE (the only true facts about the consultant and the client)
and an OUTPUT produced by an agent. Decide whether the OUTPUT fabricates any
CONCRETE FACT not present in the SOURCE.

A CONCRETE FACT is a specific, checkable assertion: a named skill or technology,
a named employer/client/project, a certification, a numeric metric, a job title,
or a duration. Flag it as fabricated ONLY if no such fact (or an obvious synonym)
appears in the SOURCE.

The following are GROUNDED — never flag them:
- Strategic positioning, headlines, and "suggested framing" that synthesize,
  interpret, or generalize from SOURCE facts (this agent's JOB is to produce
  persuasive framing). E.g. if the SOURCE shows an AWS migration for a bank,
  then "specializing in regulated cloud transformations for financial services"
  is grounded synthesis, not fabrication.
- Reframing, summarizing, or combining SOURCE facts.
- Honest declinations ("not in my background", "no direct experience with X").
- Generic advice or reasoning that asserts no new concrete fact.

Only mark grounded=false when the OUTPUT states a NEW concrete fact about the
consultant that the SOURCE does not support (e.g. a skill, employer, cert, or
metric that simply isn't there).

Respond with valid JSON only — no markdown, no prose:
{"grounded": true, "fabricated_claims": []}
or, when ungrounded:
{"grounded": false, "fabricated_claims": ["short verbatim phrase from the OUTPUT", ...]}"""


class JudgeVerdict(BaseModel):
    grounded: bool
    fabricated_claims: list[str] = []


JudgeFn = Callable[[dict, Any, int], JudgeVerdict]


def _default_judge(source: dict, output: Any, samples: int = 1) -> JudgeVerdict:
    """Judge via the project's LLMClient (call_json) and majority-vote over `samples`.

    Uses the same client the agents use (post Issue #1 harness migration), so it
    inherits the configured provider and needs no separate model setup.
    """
    try:
        from llm_client import LLMClient

        llm = LLMClient()
        user_message = (
            "SOURCE:\n"
            + json.dumps(source, indent=2)
            + "\n\nOUTPUT:\n"
            + (output if isinstance(output, str) else json.dumps(output, indent=2))
        )
        votes: list[JudgeVerdict] = []
        for _ in range(max(1, samples)):
            raw = llm.call_json(JUDGE_SYSTEM, user_message)
            votes.append(JudgeVerdict.model_validate(raw))
    except Exception as exc:  # provider/model/parse failure
        raise InfraError(f"hallucination judge unavailable: {type(exc).__name__}: {exc}") from exc

    grounded_votes = sum(1 for v in votes if v.grounded)
    grounded = grounded_votes > len(votes) / 2
    fabricated: list[str] = []
    if not grounded:
        for v in votes:
            if not v.grounded:
                fabricated.extend(v.fabricated_claims)
    # de-dup preserving order
    fabricated = list(dict.fromkeys(fabricated))
    return JudgeVerdict(grounded=grounded, fabricated_claims=fabricated)


def evaluate(case: GoldenCase, output: Any, judge: JudgeFn | None = None) -> Verdict:
    judge = judge or _default_judge
    samples = int(os.environ.get("EVALS_SAMPLES", "1"))

    jv = judge(case.source, output, samples)  # may raise InfraError → runner exit 3

    if jv.grounded and not jv.fabricated_claims:
        return Verdict(evaluator=NAME, status=Status.PASS, reason="all claims grounded in source")
    return Verdict(
        evaluator=NAME,
        status=Status.FAIL,
        reason="output contains claims not supported by source",
        evidence={"fabricated_claims": jv.fabricated_claims},
    )
