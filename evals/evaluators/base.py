"""
Core eval models shared across the framework.

Kept dependency-free (only pydantic) so every other eval module can import it
without import cycles: harness -> base, evaluators -> base, runner -> *.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InfraError(RuntimeError):
    """Raised when a model/provider call fails (auth, network, unreachable).

    Distinct from an evaluation FAIL — the runner maps this to exit code 3 and
    never reports it as a pass (spec FR-018).
    """


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"  # infrastructure problem, not a quality failure
    SKIP = "SKIP"  # evaluator not applicable to this agent


class Verdict(BaseModel):
    """One evaluator's result for one case."""

    evaluator: str
    status: Status
    reason: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """A passing or not-applicable verdict — does not fail the case."""
        return self.status in (Status.PASS, Status.SKIP)


class GoldenCase(BaseModel):
    """One evaluation scenario for one agent (loaded from golden/<agent>/<id>.json)."""

    id: str
    agent: str
    description: str
    tags: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    expectations: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Evaluator(Protocol):
    """An evaluator module/object exposes NAME and evaluate(case, output)."""

    NAME: str

    def evaluate(self, case: GoldenCase, output: Any) -> Verdict: ...
