"""
Meta-tests for the eval framework (US1 hard gates).

These run fully offline — no LLM provider needed. The hallucination judge is
injected as a deterministic stub; schema/factual gates are deterministic.

They assert the framework CATCHES failures: a malformed output fails the schema
gate, a fabricated output fails the hallucination gate, and an unsupported skill
fails the factual-consistency gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.evaluators import factual_consistency, hallucination_detector, schema_validator
from evals.evaluators.base import GoldenCase, Status
from evals.evaluators.hallucination_detector import JudgeVerdict


def _matching_case(skill_item="AWS"):
    profile = {"name": "Sam", "skills": ["AWS", "Python"], "experience": [], "projects": []}
    return GoldenCase(
        id="t", agent="matching", description="meta",
        tags=["happy"],
        source={"structured_profile": profile},
        input={"structured_profile": profile, "client_context": {}},
    )


def _valid_matching_output(skill_item="AWS", score=9):
    return {
        "top_matches": [
            {"type": "skill", "item": skill_item, "relevance_score": score,
             "reason": "relevant", "suggested_framing": "lead with it"}
        ],
        "secondary_matches": [],
        "client_tone_match": "be direct",
        "headline_positioning": "strong fit",
    }


# --- schema gate ------------------------------------------------------------

def test_schema_gate_passes_on_valid_output():
    v = schema_validator.evaluate(_matching_case(), _valid_matching_output())
    assert v.status == Status.PASS
    print("PASS: schema gate accepts valid output")


def test_schema_gate_fails_on_out_of_range_score():
    bad = _valid_matching_output(score=99)  # relevance_score must be <= 10
    v = schema_validator.evaluate(_matching_case(), bad)
    assert v.status == Status.FAIL
    assert "relevance_score" in str(v.evidence)
    print("PASS: schema gate rejects out-of-range score")


def test_schema_gate_skips_when_agent_has_no_schema():
    case = GoldenCase(id="t", agent="persona", description="meta", tags=["happy"], source={}, input={})
    v = schema_validator.evaluate(case, "free text response")
    assert v.status == Status.SKIP
    print("PASS: schema gate skips free-text agents")


# --- factual consistency gate ----------------------------------------------

def test_factual_gate_flags_unsupported_skill():
    out = _valid_matching_output(skill_item="Kubernetes")  # not in source skills
    v = factual_consistency.evaluate(_matching_case(), out)
    assert v.status == Status.FAIL
    print("PASS: factual gate flags skill absent from source")


def test_factual_gate_passes_supported_skill():
    v = factual_consistency.evaluate(_matching_case(), _valid_matching_output(skill_item="AWS"))
    assert v.status == Status.PASS
    print("PASS: factual gate accepts source-backed skill")


# --- hallucination gate (injected stub judge) -------------------------------

def _judge_grounded(source, output, samples=1):
    return JudgeVerdict(grounded=True, fabricated_claims=[])


def _judge_fabricated(source, output, samples=1):
    return JudgeVerdict(grounded=False, fabricated_claims=["Certified Kubernetes Administrator"])


def test_hallucination_gate_fails_on_fabrication():
    v = hallucination_detector.evaluate(
        _matching_case(), _valid_matching_output(), judge=_judge_fabricated
    )
    assert v.status == Status.FAIL
    assert "Certified Kubernetes Administrator" in v.evidence["fabricated_claims"]
    print("PASS: hallucination gate fails fabricated output")


def test_hallucination_gate_passes_grounded():
    v = hallucination_detector.evaluate(
        _matching_case(), _valid_matching_output(), judge=_judge_grounded
    )
    assert v.status == Status.PASS
    print("PASS: hallucination gate passes grounded output")
