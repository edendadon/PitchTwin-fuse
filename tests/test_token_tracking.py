"""
Tests for token_tracking.py — cost math, thread-local node attribution,
guardrail recording, and the persisted usage-dict shape.

Also covers LLMClient usage capture via an injected tracker plus a mock
provider response (the single capture point for the whole proposal pipeline).
"""

import os
import sys
import threading

# Make repo-root modules (token_tracking, llm_client, ...) importable,
# mirroring the sys.path shim in tests/conftest.py.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from token_tracking import CallUsage, UsageTracker, estimate_cost


# --- estimate_cost -------------------------------------------------------

def test_estimate_cost_uses_per_million_pricing():
    # gpt-4o is $2.50 / 1M input tokens, $10.00 / 1M output tokens.
    cost = estimate_cost("gpt-4o", 1_000_000, 1_000_000)
    assert cost == pytest.approx(12.50)


def test_estimate_cost_small_counts():
    cost = estimate_cost("gpt-4o", 2000, 400)
    assert cost == pytest.approx(2000 / 1e6 * 2.50 + 400 / 1e6 * 10.00)


def test_estimate_cost_unknown_model_falls_back_to_env_default(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_DEFAULT_IN", "1.00")
    monkeypatch.setenv("LLM_PRICE_DEFAULT_OUT", "2.00")
    cost = estimate_cost("totally-unknown-model", 1_000_000, 1_000_000)
    assert cost == pytest.approx(3.00)


# --- attribution ---------------------------------------------------------

def test_record_usage_attributes_to_current_node():
    tracker = UsageTracker()
    with tracker.node("profile_agent"):
        tracker.record_usage(CallUsage("m", 100, 50, 150, 0.001))
    bucket = tracker.nodes["profile_agent"]
    assert bucket["total_tokens"] == 150
    assert bucket["prompt_tokens"] == 100
    assert bucket["completion_tokens"] == 50
    assert bucket["calls"] == 1
    assert bucket["cost_usd"] == pytest.approx(0.001)


def test_record_usage_without_node_goes_to_unattributed():
    tracker = UsageTracker()
    tracker.record_usage(CallUsage("m", 10, 5, 15, 0.0))
    assert tracker.nodes["_unattributed"]["total_tokens"] == 15


def test_node_context_clears_on_exit():
    tracker = UsageTracker()
    with tracker.node("profile_agent"):
        pass
    # Recording after the context exits must not land in profile_agent.
    tracker.record_usage(CallUsage("m", 7, 3, 10, 0.0))
    assert tracker.nodes["profile_agent"]["total_tokens"] == 0
    assert tracker.nodes["_unattributed"]["total_tokens"] == 10


def test_thread_local_attribution_isolates_concurrent_nodes():
    """Two threads each holding a different node context must not cross-pollute."""
    tracker = UsageTracker()
    barrier = threading.Barrier(2)

    def worker(node_id, prompt, completion):
        with tracker.node(node_id):
            barrier.wait()  # both threads hold their node context simultaneously
            tracker.record_usage(
                CallUsage("m", prompt, completion, prompt + completion, 0.0)
            )

    t1 = threading.Thread(target=worker, args=("profile_agent", 100, 10))
    t2 = threading.Thread(target=worker, args=("client_research", 200, 20))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert tracker.nodes["profile_agent"]["prompt_tokens"] == 100
    assert tracker.nodes["profile_agent"]["completion_tokens"] == 10
    assert tracker.nodes["client_research"]["prompt_tokens"] == 200
    assert tracker.nodes["client_research"]["completion_tokens"] == 20


# --- guardrails ----------------------------------------------------------

def test_record_guardrail_appends_to_current_node():
    tracker = UsageTracker()
    with tracker.node("combined_agent"):
        tracker.record_guardrail("retry")
        tracker.record_guardrail("json_repair")
    assert tracker.nodes["combined_agent"]["guardrail_triggers"] == [
        "retry",
        "json_repair",
    ]


# --- aggregation / serialization -----------------------------------------

def test_totals_sums_across_nodes():
    tracker = UsageTracker()
    with tracker.node("a"):
        tracker.record_usage(CallUsage("m", 100, 50, 150, 0.002))
    with tracker.node("b"):
        tracker.record_usage(CallUsage("m", 200, 100, 300, 0.004))
    totals = tracker.totals()
    assert totals["prompt_tokens"] == 300
    assert totals["completion_tokens"] == 150
    assert totals["total_tokens"] == 450
    assert totals["cost_usd"] == pytest.approx(0.006)


def test_to_usage_dict_shape():
    tracker = UsageTracker()
    with tracker.node("profile_agent"):
        tracker.record_usage(CallUsage("m", 100, 50, 150, 0.002))
        tracker.record_guardrail("retry")
    usage = tracker.to_usage_dict(12.34, "trace-xyz")

    assert usage["trace_id"] == "trace-xyz"
    assert usage["duration_seconds"] == pytest.approx(12.34)
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert usage["total_tokens"] == 150
    assert usage["cost_usd"] == pytest.approx(0.002)
    assert set(usage["nodes"].keys()) == {"profile_agent"}

    node = usage["nodes"]["profile_agent"]
    assert node["total_tokens"] == 150
    assert node["calls"] == 1
    assert node["guardrail_triggers"] == ["retry"]


# --- LLMClient usage capture (Slice A) -----------------------------------
#
# The provider client is the external boundary, so we mock it; the behavior
# under test is real LLMClient code (call/_call_litellm/_emit_usage and the
# guardrail emission), driven by a canned provider response.

from unittest.mock import MagicMock  # noqa: E402


def _litellm_client_without_init(mocker):
    import llm_client as llm_mod

    # Skip _init_client so no real OpenAI client / logfire instrumentation runs.
    mocker.patch.object(llm_mod.LLMClient, "_init_client", lambda self: None)
    return llm_mod.LLMClient(provider="litellm")


def _canned_response(content, prompt, completion, total):
    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt
    response.usage.completion_tokens = completion
    response.usage.total_tokens = total
    return response


def test_llm_client_captures_usage_into_tracker(mocker):
    client = _litellm_client_without_init(mocker)
    response = _canned_response("hello", 1200, 300, 1500)
    client._litellm_client = MagicMock()
    client._litellm_client.chat.completions.create.return_value = response

    tracker = UsageTracker()
    client.set_tracker(tracker)
    with tracker.node("combined_agent"):
        out = client.call("system", "user")

    assert out == "hello"
    bucket = tracker.nodes["combined_agent"]
    assert bucket["prompt_tokens"] == 1200
    assert bucket["completion_tokens"] == 300
    assert bucket["total_tokens"] == 1500
    assert bucket["calls"] == 1
    assert bucket["cost_usd"] > 0


def test_llm_client_no_tracker_is_a_noop(mocker):
    client = _litellm_client_without_init(mocker)
    client._litellm_client = MagicMock()
    client._litellm_client.chat.completions.create.return_value = _canned_response(
        "hi", 1, 1, 2
    )
    # No set_tracker call -> must not raise.
    assert client.call("system", "user") == "hi"


def test_llm_client_emits_retry_guardrail_on_transient_failure(mocker):
    import llm_client as llm_mod

    client = _litellm_client_without_init(mocker)
    mocker.patch.object(llm_mod.time, "sleep", lambda *a, **k: None)

    response = _canned_response("ok", 5, 2, 7)
    client._litellm_client = MagicMock()
    client._litellm_client.chat.completions.create.side_effect = [
        RuntimeError("transient boom"),
        response,
    ]

    tracker = UsageTracker()
    client.set_tracker(tracker)
    with tracker.node("profile_agent"):
        out = client.call("system", "user")

    assert out == "ok"
    bucket = tracker.nodes["profile_agent"]
    assert "retry" in bucket["guardrail_triggers"]
    assert bucket["total_tokens"] == 7  # successful retry still captures usage


def test_call_json_emits_json_repair_on_fenced_response(mocker):
    client = _litellm_client_without_init(mocker)
    fenced = _canned_response('```json\n{"a": 1}\n```', 3, 1, 4)
    client._litellm_client = MagicMock()
    client._litellm_client.chat.completions.create.return_value = fenced

    tracker = UsageTracker()
    client.set_tracker(tracker)
    with tracker.node("combined_agent"):
        result = client.call_json("system", "user")

    assert result == {"a": 1}
    assert "json_repair" in tracker.nodes["combined_agent"]["guardrail_triggers"]
