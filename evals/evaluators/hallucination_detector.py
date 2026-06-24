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

You receive a SOURCE (the ONLY true facts — it may include the consultant's
profile, the client's context/requirements, and/or a conversation transcript)
and an OUTPUT produced by an agent. Decide ONE thing:

  Does the OUTPUT assert that the CONSULTANT personally possesses or has done a
  specific thing that the SOURCE does not support?

A fabrication is a NEW CONCRETE FACT *attributed to the consultant* — a skill,
technology, employer, client, project, certification, job title, duration, or a
numeric metric/achievement (e.g. "99.99% uptime", "50+ systems", "millions of
transactions") — that does not appear in the SOURCE. Invented numbers/metrics
about the consultant's own work are the clearest fabrications.

The following are ALWAYS GROUNDED — never flag them:
- Facts about the CLIENT or the engagement: the client's industry, needs,
  required skills, tech stack, or challenges (these come from the client context).
- Gap analysis: naming skills/technologies the consultant LACKS or that the
  client requires, and any description/mitigation/framing of those gaps. Saying
  the consultant is missing "SAP" is NOT claiming the consultant has SAP.
- Recommendations, advice, suggested talking points, questions to ask, and
  next steps (these are guidance, not claims about the consultant's background).
- Strategic positioning, headlines, persuasive framing, summaries, and
  reasonable synthesis/generalization of SOURCE facts.
- Honest declinations ("not in my background", "no direct experience with X").

Only set grounded=false when the OUTPUT credits the CONSULTANT with a concrete
skill/employer/cert/project/metric that simply is not in the SOURCE.

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
