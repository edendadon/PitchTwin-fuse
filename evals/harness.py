"""
Agent adapter registry + golden-case loader.

This is the integration seam with the (in-progress) Issue #1 agent harness.
The 7 PitchTwin agents currently have two call shapes:
  - migrated (pydantic-ai): run_*(inputs...)            # no llm_client
  - legacy:                 run_*(inputs..., llm_client) # uses LLMClient
`AGENT_REGISTRY` hides both behind a uniform `invoke(case) -> output`. When the
Issue #1 `Agent` base class lands, each entry's `invoke` delegates to
`agent.execute(...)` and nothing else in the framework changes.

All agent / model imports are LAZY (inside invoke) so importing this module
stays offline and cheap — the meta-tests rely on that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from evals.evaluators.base import GoldenCase, InfraError

AGENT_NAMES = [
    "profile",
    "client_research",
    "matching",
    "writer",
    "gap",
    "persona",
    "debrief",
]

GOLDEN_DIR = Path(__file__).parent / "golden"


@dataclass
class AgentEntry:
    name: str
    invoke: Callable[[GoldenCase], Any]
    output_schema: type[BaseModel] | None  # None => free text (e.g. persona)
    output_kind: str  # "structured" | "text"


def _as_infra(exc: Exception) -> InfraError:
    """Wrap an agent/model exception as an InfraError.

    Agent run_* functions are thin wrappers around the model call, so a raised
    exception is overwhelmingly a provider/auth/network problem rather than a
    logic bug — classify it as infrastructure so the runner exits 3, not a
    false pass/fail.
    """
    return InfraError(f"{type(exc).__name__}: {exc}")


# --- per-agent invokers (lazy imports) -------------------------------------

def _invoke_matching(case: GoldenCase) -> dict[str, Any]:
    # The Issue #1 harness migration changed the signature back to taking an
    # llm_client (run_matching_agent now wraps AgentHarness over LLMClient).
    from agents.matching_agent import run_matching_agent
    from llm_client import LLMClient

    inp = case.input
    try:
        return run_matching_agent(inp["structured_profile"], inp["client_context"], LLMClient())
    except KeyError:
        raise
    except Exception as exc:  # provider/model failure
        raise _as_infra(exc) from exc


def _matching_schema() -> type[BaseModel]:
    # Schemas now live in agents/schemas.py (Issue #1 harness).
    from agents.schemas import MatchingOutput

    return MatchingOutput


# Registry. US1 ships the `matching` entry (migrated agent, has a schema).
# Remaining agents are registered in US3 (T019).
AGENT_REGISTRY: dict[str, AgentEntry] = {
    "matching": AgentEntry(
        name="matching",
        invoke=_invoke_matching,
        output_schema=None,  # resolved lazily via get_output_schema to stay offline at import
        output_kind="structured",
    ),
}

# Lazy schema resolvers, kept separate so importing harness never imports agents.
_SCHEMA_RESOLVERS: dict[str, Callable[[], type[BaseModel]]] = {
    "matching": _matching_schema,
}


def get_output_schema(agent: str) -> type[BaseModel] | None:
    resolver = _SCHEMA_RESOLVERS.get(agent)
    return resolver() if resolver else None


def registered_agents() -> list[str]:
    return list(AGENT_REGISTRY.keys())


# --- golden-case loader -----------------------------------------------------

def load_cases(agents: list[str] | None = None) -> list[GoldenCase]:
    """Load and validate golden cases for the given agents (default: all registered).

    Rejects cases whose `agent` field disagrees with their directory and
    enforces id uniqueness within an agent.
    """
    selected = agents or registered_agents()
    cases: list[GoldenCase] = []
    for agent in selected:
        agent_dir = GOLDEN_DIR / agent
        if not agent_dir.is_dir():
            continue
        seen: set[str] = set()
        for path in sorted(agent_dir.glob("*.json")):
            data = json.loads(path.read_text())
            case = GoldenCase.model_validate(data)
            if case.agent != agent:
                raise ValueError(
                    f"{path}: case.agent={case.agent!r} but lives under {agent!r}/"
                )
            if case.id in seen:
                raise ValueError(f"{path}: duplicate case id {case.id!r} in {agent}/")
            seen.add(case.id)
            cases.append(case)
    return cases


def count_cases() -> dict[str, int]:
    """Per-agent golden-case counts across ALL 7 agent dirs (for coverage checks)."""
    counts: dict[str, int] = {}
    for agent in AGENT_NAMES:
        agent_dir = GOLDEN_DIR / agent
        counts[agent] = len(list(agent_dir.glob("*.json"))) if agent_dir.is_dir() else 0
    return counts
