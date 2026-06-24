"""
factual_consistency — deterministic checks that the output does not contradict
the source or itself. No model call.

Checks (best-effort across agents; PASS when none apply):
  1. Internal contradiction: the same item appears in both `top_matches` and
     `secondary_matches` (matching output).
  2. Source vocabulary overlap: a skill-typed match item must share at least one
     meaningful token with the FULL source (skills, technologies, companies,
     roles, descriptions — not just the `skills` list). This catches a wholly
     absent skill (e.g. "Kubernetes") while tolerating rephrasings and items
     labelled with a role/company.

A clean PASS here is not a grounding guarantee — the hallucination judge is the
stronger semantic gate. This evaluator only flags the mechanically-undeniable
cases and is deliberately lenient to avoid false positives.
"""

from __future__ import annotations

import re
from typing import Any

from evals.evaluators.base import GoldenCase, Status, Verdict

NAME = "factual_consistency"

_STOP = {"at", "of", "the", "and", "for", "with", "in", "on", "a", "an", "to"}


def _norm(s: str) -> str:
    return s.strip().lower()


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9+#.]+", _norm(s)) if len(t) >= 3 and t not in _STOP}


def _source_vocab(value: Any) -> set[str]:
    """Recursively collect normalized tokens from every string in the source."""
    vocab: set[str] = set()
    if isinstance(value, str):
        vocab |= _tokens(value)
    elif isinstance(value, dict):
        for v in value.values():
            vocab |= _source_vocab(v)
    elif isinstance(value, list):
        for v in value:
            vocab |= _source_vocab(v)
    return vocab


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

    vocab = _source_vocab(case.source)
    if vocab:
        for bucket in (top, secondary):
            if not isinstance(bucket, list):
                continue
            for m in bucket:
                if isinstance(m, dict) and m.get("type") == "skill":
                    item = str(m.get("item", ""))
                    item_tokens = _tokens(item)
                    # Flag only when NO meaningful token is anywhere in the source.
                    if item_tokens and not (item_tokens & vocab):
                        problems.append(
                            f"skill match '{item}' shares no term with the source profile"
                        )

    if problems:
        return Verdict(
            evaluator=NAME,
            status=Status.FAIL,
            reason="; ".join(problems[:5]),
            evidence={"problems": problems},
        )
    return Verdict(evaluator=NAME, status=Status.PASS, reason="no contradictions found")
