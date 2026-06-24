"""
token_tracking.py — per-workflow token + cost aggregation.

Lives flat at the repo root (like db.py / observability.py) and imports nothing
local, so llm_client and the orchestrator can import its pure helpers
(``CallUsage`` / ``estimate_cost``) without creating an import cycle.

Why a separate surface? Issue #2's ``execution_traces`` table has a fixed schema
(trace_id, node_id, event, timestamp, duration_ms, error) with no room for tokens
or cost — and that schema is its contract, so we must not touch it. Instead #6
keeps tokens/cost on its own ``proposal.usage`` blob keyed per ``node_id``; the
debug-trace UI later joins the two by ``node_id`` (status + latency from the
traces, tokens + cost from here).

Attribution: each DAG wrapper runs inside its own thread (the WorkflowEngine
fires every agent_fn in a daemon thread), so a thread-local "current node" gives
clean per-node isolation even when phase-1 agents run concurrently.
"""

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

# USD per 1,000,000 tokens, as (input_price, output_price). Static price map —
# good enough for the proposal page's cost line. Unknown models fall back to the
# "default" entry, whose values can be overridden at runtime via the
# LLM_PRICE_DEFAULT_IN / LLM_PRICE_DEFAULT_OUT env vars.
_DEFAULT_IN = 0.50
_DEFAULT_OUT = 1.50

MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "kimi-k2.5": (0.60, 2.50),
    "default": (_DEFAULT_IN, _DEFAULT_OUT),
}


def _price_for(model: str) -> tuple[float, float]:
    """Per-1M (in, out) price for ``model``, or the env-overridable default."""
    price = MODEL_PRICES.get(model)
    if price is not None:
        return price
    return (
        float(os.getenv("LLM_PRICE_DEFAULT_IN", _DEFAULT_IN)),
        float(os.getenv("LLM_PRICE_DEFAULT_OUT", _DEFAULT_OUT)),
    )


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost of a single call from its token counts."""
    in_price, out_price = _price_for(model)
    return (prompt_tokens / 1_000_000) * in_price + (completion_tokens / 1_000_000) * out_price


@dataclass
class CallUsage:
    """Token + cost record for one LLM call."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class UsageTracker:
    """
    Per-workflow aggregator of token usage, cost, and guardrail triggers,
    bucketed by DAG node id.

    A ``threading.local`` holds the current node for the running thread; a lock
    guards ``self.nodes`` because phase-1 agents record concurrently. The engine
    already records per-node ``duration_ms`` in execution_traces, so we do no
    timing here.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self.nodes: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _new_bucket() -> dict[str, Any]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "calls": 0,
            "guardrail_triggers": [],
        }

    @contextmanager
    def node(self, node_id: str):
        """Set the current thread's node for the duration of the block."""
        with self._lock:
            self.nodes.setdefault(node_id, self._new_bucket())
        previous = getattr(self._local, "node_id", None)
        self._local.node_id = node_id
        try:
            yield
        finally:
            self._local.node_id = previous

    def _current_bucket(self) -> dict[str, Any]:
        """Bucket for the current thread's node (caller must hold the lock)."""
        node_id = getattr(self._local, "node_id", None) or "_unattributed"
        bucket = self.nodes.get(node_id)
        if bucket is None:
            bucket = self._new_bucket()
            self.nodes[node_id] = bucket
        return bucket

    def record_usage(self, usage: CallUsage) -> None:
        with self._lock:
            bucket = self._current_bucket()
            bucket["prompt_tokens"] += usage.prompt_tokens
            bucket["completion_tokens"] += usage.completion_tokens
            bucket["total_tokens"] += usage.total_tokens
            bucket["cost_usd"] += usage.cost_usd
            bucket["calls"] += 1

    def record_guardrail(self, trigger: str) -> None:
        with self._lock:
            self._current_bucket()["guardrail_triggers"].append(trigger)

    def totals(self) -> dict[str, Any]:
        with self._lock:
            totals = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "calls": 0,
            }
            for bucket in self.nodes.values():
                totals["prompt_tokens"] += bucket["prompt_tokens"]
                totals["completion_tokens"] += bucket["completion_tokens"]
                totals["total_tokens"] += bucket["total_tokens"]
                totals["cost_usd"] += bucket["cost_usd"]
                totals["calls"] += bucket["calls"]
            return totals

    def to_usage_dict(self, duration_seconds: float, trace_id: str = "") -> dict[str, Any]:
        """Flatten to a JSON-serializable blob for persistence/render."""
        totals = self.totals()
        with self._lock:
            nodes = {
                node_id: {
                    "prompt_tokens": b["prompt_tokens"],
                    "completion_tokens": b["completion_tokens"],
                    "total_tokens": b["total_tokens"],
                    "cost_usd": round(b["cost_usd"], 6),
                    "calls": b["calls"],
                    "guardrail_triggers": list(b["guardrail_triggers"]),
                }
                for node_id, b in self.nodes.items()
            }
        return {
            "trace_id": trace_id,
            "duration_seconds": round(duration_seconds, 2),
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "cost_usd": round(totals["cost_usd"], 6),
            "calls": totals["calls"],
            "nodes": nodes,
        }
