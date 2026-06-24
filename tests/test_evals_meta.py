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


def test_schema_gate_fails_on_missing_required_field():
    # MatchingOutput requires `top_matches`; omit it to trigger a validation error.
    bad = {"secondary_matches": [], "client_tone_match": "x", "headline_positioning": "y"}
    v = schema_validator.evaluate(_matching_case(), bad)
    assert v.status == Status.FAIL
    assert "top_matches" in str(v.evidence)
    print("PASS: schema gate rejects output missing a required field")


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


# --- baseline regression detection (US2, offline) ---------------------------

from evals import report as rpt  # noqa: E402


def _r(agent, case_id, status):
    return {"agent": agent, "case_id": case_id, "status": status, "verdicts": []}


def test_baseline_roundtrip_no_regression_when_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(rpt, "BASELINE_DIR", tmp_path)
    results = [_r("matching", "c1", "PASS"), _r("matching", "c2", "PASS")]
    rpt.write_baseline("matching", results)
    baseline = rpt.load_baseline("matching")
    assert baseline is not None and baseline["cases"]["c1"]["passed"] is True
    assert rpt.compute_regressions(results, baseline) == []
    print("PASS: unchanged re-run reports zero regressions")


def test_regression_detected_when_passing_case_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(rpt, "BASELINE_DIR", tmp_path)
    rpt.write_baseline("matching", [_r("matching", "c1", "PASS"), _r("matching", "c2", "PASS")])
    baseline = rpt.load_baseline("matching")
    degraded = [_r("matching", "c1", "PASS"), _r("matching", "c2", "FAIL")]
    assert rpt.compute_regressions(degraded, baseline) == ["c2"]
    print("PASS: degraded previously-passing case flagged as regression")


def test_first_run_without_baseline_reports_no_regression():
    assert rpt.compute_regressions([_r("matching", "c1", "FAIL")], None) == []
    print("PASS: first run (no baseline) reports no phantom regressions")


def test_update_baseline_refuses_to_capture_a_failing_run(tmp_path, monkeypatch):
    from evals import run as evalrun

    monkeypatch.setattr(rpt, "BASELINE_DIR", tmp_path)
    results = [_r("matching", "c1", "PASS"), _r("matching", "c2", "FAIL")]
    code, _ = evalrun._summarize(results, update_baseline=True)
    assert code == evalrun.EXIT_FAIL
    assert not (tmp_path / "matching.json").exists()  # not rubber-stamped
    print("PASS: --update-baseline refuses a failing run")


def test_update_baseline_captures_a_clean_run(tmp_path, monkeypatch):
    from evals import run as evalrun

    monkeypatch.setattr(rpt, "BASELINE_DIR", tmp_path)
    results = [_r("matching", "c1", "PASS"), _r("matching", "c2", "PASS")]
    code, _ = evalrun._summarize(results, update_baseline=True)
    assert code == evalrun.EXIT_OK
    assert (tmp_path / "matching.json").exists()
    print("PASS: --update-baseline captures a clean run")
