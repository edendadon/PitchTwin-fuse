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
# All agents now share one calling convention: run_<agent>(...inputs..., llm_client).
# Each invoker maps a GoldenCase.input dict to the agent's positional args and
# wraps provider/model failures as InfraError.

def _client():
    from llm_client import LLMClient

    return LLMClient()


def _invoke_matching(case: GoldenCase) -> dict[str, Any]:
    from agents.matching_agent import run_matching_agent

    inp = case.input
    try:
        return run_matching_agent(inp["structured_profile"], inp["client_context"], _client())
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_profile(case: GoldenCase) -> dict[str, Any]:
    from agents.profile_agent import run_profile_agent

    try:
        return run_profile_agent(case.input["raw_profile"], _client())
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_client_research(case: GoldenCase) -> dict[str, Any]:
    from agents.client_research_agent import run_client_research_agent

    inp = case.input
    try:
        return run_client_research_agent(inp["client_brief"], inp["company_name"], _client())
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_writer(case: GoldenCase) -> dict[str, Any]:
    from agents.writer_agent import run_writer_agent

    inp = case.input
    try:
        return run_writer_agent(
            inp["relevance_map"], inp["structured_profile"], inp["client_context"], _client()
        )
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_gap(case: GoldenCase) -> dict[str, Any]:
    from agents.gap_agent import run_gap_agent

    inp = case.input
    try:
        return run_gap_agent(inp["client_context"], inp["structured_profile"], _client())
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_debrief(case: GoldenCase) -> dict[str, Any]:
    from agents.debrief_agent import run_debrief_agent

    try:
        return run_debrief_agent(case.input["transcript"], _client())
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


def _invoke_persona(case: GoldenCase) -> str:
    # Persona is free text: build the grounded system prompt, then answer one message.
    from agents.persona_agent import build_system_prompt, run_persona_agent

    inp = case.input
    try:
        system_prompt = build_system_prompt(
            inp.get("structured_profile", {}), inp.get("relevance_map", {})
        )
        return run_persona_agent(
            inp["user_message"], inp.get("conversation_history", []), system_prompt, _client()
        )
    except KeyError:
        raise
    except Exception as exc:
        raise _as_infra(exc) from exc


# Lazy schema resolvers (agents/schemas.py from the Issue #1 harness).
def _schema(name: str) -> Callable[[], type[BaseModel]]:
    def resolve() -> type[BaseModel]:
        import agents.schemas as s

        return getattr(s, name)

    return resolve


AGENT_REGISTRY: dict[str, AgentEntry] = {
    "profile": AgentEntry("profile", _invoke_profile, None, "structured"),
    "client_research": AgentEntry("client_research", _invoke_client_research, None, "structured"),
    "matching": AgentEntry("matching", _invoke_matching, None, "structured"),
    "writer": AgentEntry("writer", _invoke_writer, None, "structured"),
    "gap": AgentEntry("gap", _invoke_gap, None, "structured"),
    "persona": AgentEntry("persona", _invoke_persona, None, "text"),  # free text, schema SKIP
    "debrief": AgentEntry("debrief", _invoke_debrief, None, "structured"),
}

_SCHEMA_RESOLVERS: dict[str, Callable[[], type[BaseModel]]] = {
    "profile": _schema("ProfileOutput"),
    "client_research": _schema("ClientContextOutput"),
    "matching": _schema("MatchingOutput"),
    "writer": _schema("WriterOutput"),
    "gap": _schema("GapAnalysisOutput"),
    "debrief": _schema("DebriefOutput"),
    # persona: no schema (free text) -> get_output_schema returns None -> schema gate SKIP
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
