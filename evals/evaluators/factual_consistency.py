"""
factual_consistency — deterministic checks that the output does not contradict
the source or itself. No model call.

Checks (best-effort across agents; PASS when none apply):
  1. Internal contradiction: the same item appears in both `top_matches` and
     `secondary_matches` (matching output).
  2. Closed-set source membership: any output item of type "skill" must refer
     to a skill present in the source profile's skill list (case-insensitive
     substring match in either direction).

A clean PASS here is not a grounding guarantee — the hallucination judge is the
stronger semantic gate. This evaluator catches the mechanically-decidable cases.
"""

from __future__ import annotations

from typing import Any

from evals.evaluators.base import GoldenCase, Status, Verdict

NAME = "factual_consistency"


def _source_skills(case: GoldenCase) -> list[str]:
    src = case.source or {}
    prof = src.get("structured_profile") or src.get("profile") or src
    skills = prof.get("skills") if isinstance(prof, dict) else None
    return [str(s) for s in skills] if isinstance(skills, list) else []


def _norm(s: str) -> str:
    return s.strip().lower()


def _skill_supported(item: str, source_skills: list[str]) -> bool:
    n = _norm(item)
    return any(n in _norm(s) or _norm(s) in n for s in source_skills)


def evaluate(case: GoldenCase, output: Any) -> Verdict:
    if not isinstance(output, dict):
        # Free-text output (persona) — nothing mechanical to check here.
        return Verdict(evaluator=NAME, status=Status.SKIP, reason="non-structured output")

    problems: list[str] = []

    top = output.get("top_matches") or []
    secondary = output.get("secondary_matches") or []
    if isinstance(top, list) and isinstance(secondary, list):
        top_items = {_norm(m.get("item", "")) for m in top if isinstance(m, dict)}
        dupes = [
            m.get("item")
            for m in secondary
            if isinstance(m, dict) and _norm(m.get("item", "")) in top_items
        ]
        if dupes:
            problems.append(f"item(s) in both top and secondary matches: {dupes}")

    source_skills = _source_skills(case)
    if source_skills:
        for bucket in (top, secondary):
            if not isinstance(bucket, list):
                continue
            for m in bucket:
                if isinstance(m, dict) and m.get("type") == "skill":
                    item = str(m.get("item", ""))
                    if item and not _skill_supported(item, source_skills):
                        problems.append(
                            f"skill match '{item}' not present in source skills"
                        )

    if problems:
        return Verdict(
            evaluator=NAME,
            status=Status.FAIL,
            reason="; ".join(problems[:5]),
            evidence={"problems": problems},
        )
    return Verdict(evaluator=NAME, status=Status.PASS, reason="no contradictions found")
