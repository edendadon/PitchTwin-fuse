"""
Unit tests for app._aggregate_trace_nodes — folding raw execution_traces
events into one status row per node (success / retry / failure / timeout).
"""

from app import _aggregate_trace_nodes


def _ev(node_id, event, duration_ms=None, error=None):
    return {
        "trace_id": "t",
        "node_id": node_id,
        "event": event,
        "timestamp": "2026-01-01T00:00:00",
        "duration_ms": duration_ms,
        "error": error,
    }


def test_clean_completion_is_success():
    rows = _aggregate_trace_nodes([
        _ev("profile_agent", "started"),
        _ev("profile_agent", "completed", duration_ms=1200),
    ])
    assert rows == [
        {"node_id": "profile_agent", "status": "success", "duration_ms": 1200, "error": None}
    ]


def test_completion_after_failure_is_retry():
    rows = _aggregate_trace_nodes([
        _ev("client_research", "started"),
        _ev("client_research", "failed", error="attempt 1: boom"),
        _ev("client_research", "started"),
        _ev("client_research", "completed", duration_ms=900),
    ])
    assert rows[0]["status"] == "retry"
    assert rows[0]["duration_ms"] == 900


def test_failed_without_completion_is_failure():
    rows = _aggregate_trace_nodes([
        _ev("combined_agent", "started"),
        _ev("combined_agent", "failed", error="bad json"),
    ])
    assert rows[0]["status"] == "failure"
    assert rows[0]["error"] == "bad json"


def test_timed_out_is_timeout():
    rows = _aggregate_trace_nodes([
        _ev("combined_agent", "started"),
        _ev("combined_agent", "timed_out", error="global timeout exceeded"),
    ])
    assert rows[0]["status"] == "timeout"
    assert rows[0]["error"] == "global timeout exceeded"


def test_preserves_first_seen_order():
    rows = _aggregate_trace_nodes([
        _ev("profile_agent", "completed", duration_ms=1),
        _ev("client_research", "completed", duration_ms=2),
        _ev("combined_agent", "completed", duration_ms=3),
    ])
    assert [r["node_id"] for r in rows] == [
        "profile_agent", "client_research", "combined_agent"
    ]


def test_empty_events_yields_no_rows():
    assert _aggregate_trace_nodes([]) == []
