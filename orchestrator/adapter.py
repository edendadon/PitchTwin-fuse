"""
orchestrator/adapter.py — AgentAdapter for wrapping bare agent functions.

Probes for Issue #1 Agent base class availability.
If Agent.execute() is available, uses it.
Otherwise, wraps bare callable with execute() interface.
"""

from typing import Any, Callable


class AgentAdapter:
    """
    Wraps an agent function (or Agent instance from Issue #1) behind a
    consistent .execute(input_data: dict) -> dict interface.

    If an Agent base class exists with execute(), use it.
    Otherwise fall back to wrapping the bare callable.
    """

    def __init__(self, agent_fn: Callable[[dict], dict] | Any):
        self._agent_fn = agent_fn
        self._use_harness = False

        if hasattr(agent_fn, "execute") and callable(getattr(agent_fn, "execute")):
            self._use_harness = True

    def execute(self, input_data: dict) -> dict:
        if self._use_harness:
            return self._agent_fn.execute(input_data)
        else:
            return self._agent_fn(input_data)