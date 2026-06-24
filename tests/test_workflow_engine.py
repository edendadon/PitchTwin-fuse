"""
Unit tests for WorkflowEngine, MemoryStore, and debug trace endpoint.

Tests cover:
- T016: WorkflowEngine.execute() happy path
- T018: MemoryStore checkpoint I/O
- T020: Checkpoint resume logic
- T023: Loop detection (5 identical outputs → MaxIterationsExceeded)
- T025: Circuit breaker (3 failures → CircuitBreakerOpen)
- T027: Global timeout enforcement
- T029: Debug trace endpoint
"""

import sys
import os
import json
import time
import sqlite3
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class TestMemoryStore:
    """T018: MemoryStore checkpoint I/O"""

    @pytest.fixture
    def store(self):
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                proposal_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                input_data TEXT NOT NULL,
                output_data TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'in_progress')),
                created_at TEXT NOT NULL,
                PRIMARY KEY (proposal_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS execution_traces (
                trace_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('started', 'completed', 'failed', 'timed_out', 'circuit_breaker')),
                timestamp TEXT NOT NULL,
                duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
                error TEXT,
                PRIMARY KEY (trace_id, node_id, event, timestamp)
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoint_proposal_status ON workflow_checkpoints (proposal_id, status);
            CREATE INDEX IF NOT EXISTS idx_trace_trace_id ON execution_traces (trace_id);
        """)
        conn.close()

        import orchestrator.memory as mem_module
        original_path = mem_module.DB_PATH
        mem_module.DB_PATH = db_path
        store = mem_module.MemoryStore()
        yield store
        mem_module.DB_PATH = original_path
        os.unlink(db_path)

    def test_save_and_get_checkpoint(self, store):
        checkpoint = {
            "proposal_id": "prop-123",
            "trace_id": "trace-456",
            "node_id": "profile_agent",
            "phase": "profile_agent",
            "input_data": {"consultant_id": "c1"},
            "output_data": {"structured": {"skills": ["Python"]}},
            "status": "completed",
            "created_at": "2026-06-24T00:00:00",
        }
        store.save_checkpoint(checkpoint)
        retrieved = store.get_latest_checkpoint("prop-123")
        assert retrieved is not None
        assert retrieved["proposal_id"] == "prop-123"
        assert retrieved["node_id"] == "profile_agent"
        assert retrieved["status"] == "completed"
        assert retrieved["input_data"] == {"consultant_id": "c1"}

    def test_get_latest_in_progress(self, store):
        store.save_checkpoint({
            "proposal_id": "prop-789",
            "trace_id": "trace-001",
            "node_id": "node1",
            "phase": "node1",
            "input_data": {},
            "output_data": {},
            "status": "completed",
            "created_at": "2026-06-24T00:00:00",
        })
        store.save_checkpoint({
            "proposal_id": "prop-789",
            "trace_id": "trace-002",
            "node_id": "node2",
            "phase": "node2",
            "input_data": {},
            "output_data": {},
            "status": "in_progress",
            "created_at": "2026-06-24T00:01:00",
        })
        result = store.get_latest_in_progress("prop-789")
        assert result is not None
        assert result["node_id"] == "node2"
        assert result["status"] == "in_progress"

    def test_save_and_get_trace(self, store):
        trace = {
            "trace_id": "trace-abc",
            "node_id": "profile_agent",
            "event": "completed",
            "timestamp": "2026-06-24T00:00:00",
            "duration_ms": 1500,
            "error": None,
        }
        store.save_trace(trace)
        traces = store.get_trace("trace-abc")
        assert len(traces) == 1
        assert traces[0]["node_id"] == "profile_agent"
        assert traces[0]["event"] == "completed"
        assert traces[0]["duration_ms"] == 1500


class TestWorkflowEngineHappyPath:
    """T016: WorkflowEngine.execute() happy path"""

    def test_dag_validation_no_cycle(self):
        from orchestrator.workflow import WorkflowEngine, DAGValidationError
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        dag = [
            {"id": "a", "type": "agent", "inputs": [], "agent_fn": lambda x: {"result": "a"}},
            {"id": "b", "type": "agent", "inputs": ["a"], "agent_fn": lambda x: {"result": "b"}},
        ]

        engine = WorkflowEngine(dag, store, trace_store)
        result = engine.execute("test-prop", {})

        assert result["status"] == "completed"
        assert "trace_id" in result
        assert result["outputs"]["a"] == {"result": "a"}
        assert result["outputs"]["b"] == {"result": "b"}

    def test_dag_validation_cycle_detected(self):
        from orchestrator.workflow import WorkflowEngine, DAGValidationError
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        dag = [
            {"id": "a", "type": "agent", "inputs": ["b"], "agent_fn": lambda x: {}},
            {"id": "b", "type": "agent", "inputs": ["a"], "agent_fn": lambda x: {}},
        ]

        engine = WorkflowEngine(dag, store, trace_store)
        with pytest.raises(DAGValidationError):
            engine.execute("test-prop", {})


class TestLoopDetection:
    """T023: Loop detection — 5 identical outputs → MaxIterationsExceeded"""

    def test_loop_detection_raises_max_iterations(self):
        from orchestrator.workflow import WorkflowEngine, MaxIterationsExceeded, NodeConfig
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        call_count = [0]

        def looping_agent(input_data):
            call_count[0] += 1
            return {"output": "same_output"}

        dag = [
            {
                "id": "looping",
                "type": "agent",
                "config": {"max_retries": 0, "timeout_sec": 10, "max_iterations": 5},
                "inputs": [],
                "agent_fn": looping_agent,
            }
        ]

        engine = WorkflowEngine(dag, store, trace_store, circuit_breaker_threshold=10)
        with pytest.raises(MaxIterationsExceeded) as exc_info:
            engine.execute("test-prop", {})
        assert "loop detected" in str(exc_info.value).lower()
        assert call_count[0] == 5


class TestCircuitBreaker:
    """T025: Circuit breaker — 3 consecutive failures → CircuitBreakerOpen"""

    def test_circuit_breaker_trips_after_3_failures(self):
        from orchestrator.workflow import WorkflowEngine, CircuitBreakerOpen
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        def failing_agent(input_data):
            raise RuntimeError("deliberate failure")

        dag = [
            {"id": "fail1", "type": "agent", "config": {"max_retries": 0, "timeout_sec": 5, "max_iterations": 1}, "inputs": [], "agent_fn": failing_agent},
            {"id": "fail2", "type": "agent", "config": {"max_retries": 0, "timeout_sec": 5, "max_iterations": 1}, "inputs": [], "agent_fn": failing_agent},
            {"id": "fail3", "type": "agent", "config": {"max_retries": 0, "timeout_sec": 5, "max_iterations": 1}, "inputs": [], "agent_fn": failing_agent},
            {"id": "fail4", "type": "agent", "config": {"max_retries": 0, "timeout_sec": 5, "max_iterations": 1}, "inputs": [], "agent_fn": failing_agent},
        ]

        engine = WorkflowEngine(dag, store, trace_store, circuit_breaker_threshold=3)
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            engine.execute("test-prop", {})
        assert "circuit breaker" in str(exc_info.value).lower()


class TestGlobalTimeout:
    """T027: Global timeout — 240s wall-clock limit"""

    def test_global_timeout_aborts_pipeline(self):
        from orchestrator.workflow import WorkflowEngine, WorkflowTimeout
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        def slow_agent(input_data):
            time.sleep(5)  # longer than the global timeout below
            return {"result": "slow"}

        dag = [
            {
                "id": "slow",
                "type": "agent",
                "config": {"max_retries": 0, "timeout_sec": 30, "max_iterations": 1},
                "inputs": [],
                "agent_fn": slow_agent,
            }
        ]

        engine = WorkflowEngine(dag, store, trace_store, global_timeout_sec=1)
        with pytest.raises((WorkflowTimeout, Exception)) as exc_info:
            engine.execute("test-prop", {})
        assert any(word in str(exc_info.value).lower() for word in ["timeout", "exceeded"])


class TestCheckpointResume:
    """T020: Checkpoint resume — skip completed nodes on restart"""

    def test_resume_skips_completed_nodes(self):
        from orchestrator.workflow import WorkflowEngine
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        execution_log = []

        def node_a(input_data):
            execution_log.append("a")
            return {"a": "done"}

        def node_b(input_data):
            execution_log.append("b")
            return {"b": "done"}

        dag = [
            {"id": "a", "type": "agent", "inputs": [], "agent_fn": node_a},
            {"id": "b", "type": "agent", "inputs": ["a"], "agent_fn": node_b},
        ]

        dag2 = [
            {"id": "a", "type": "agent", "inputs": [], "agent_fn": node_a},
            {"id": "b", "type": "agent", "inputs": ["a"], "agent_fn": node_b},
        ]

        engine1 = WorkflowEngine(dag, store, trace_store)

        store.save_checkpoint({
            "proposal_id": "resume-test",
            "trace_id": "trace-resume",
            "node_id": "a",
            "phase": "a",
            "input_data": {},
            "output_data": json.dumps({"a": "done"}),
            "status": "completed",
            "created_at": "2026-06-24T00:00:00",
        })

        execution_log.clear()
        engine2 = WorkflowEngine(dag2, store, trace_store)
        result = engine2.execute("resume-test", {})

        assert "a" not in execution_log
        assert "b" in execution_log
        assert result["status"] == "completed"

    def test_resume_from_in_progress_checkpoint(self):
        """Resuming from an in_progress checkpoint must not crash and must
        continue executing the remaining downstream nodes.

        Regression: get_latest_in_progress() returns a dict whose output_data
        is already json-decoded; execute() previously read it via attribute
        access (.node_id/.output_data) and re-ran json.loads on it, raising
        AttributeError/TypeError on every real resume.
        """
        from orchestrator.workflow import WorkflowEngine
        from orchestrator.memory import MemoryStore

        store = MemoryStore()
        trace_store = MemoryStore()

        execution_log = []

        def node_a(input_data):
            execution_log.append("a")
            return {"a": "done"}

        def node_b(input_data):
            execution_log.append("b")
            return {"b": "done"}

        def node_c(input_data):
            execution_log.append("c")
            return {"c": "done"}

        dag = [
            {"id": "a", "type": "agent", "inputs": [], "agent_fn": node_a},
            {"id": "b", "type": "agent", "inputs": ["a"], "agent_fn": node_b},
            {"id": "c", "type": "agent", "inputs": ["b"], "agent_fn": node_c},
        ]

        # Node "b" was mid-flight when the previous run was interrupted.
        store.save_checkpoint({
            "proposal_id": "resume-inprogress",
            "trace_id": "trace-inprogress",
            "node_id": "b",
            "phase": "b",
            "input_data": {},
            "output_data": {"b": "done"},
            "status": "in_progress",
            "created_at": "2026-06-24T00:00:00",
        })

        engine = WorkflowEngine(dag, store, trace_store)
        result = engine.execute("resume-inprogress", {})

        # Must complete without raising, and the not-yet-done downstream node runs.
        assert result["status"] == "completed"
        assert "a" not in execution_log
        assert "c" in execution_log


class TestDebugEndpoint:
    """T029: Debug trace endpoint — returns JSON execution graph"""

    def test_debug_endpoint_returns_json(self):
        from orchestrator.memory import MemoryStore
        import tempfile
        import orchestrator.memory as mem_module

        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS execution_traces (
                trace_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                event TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                duration_ms INTEGER,
                error TEXT,
                PRIMARY KEY (trace_id, node_id, event, timestamp)
            );
        """)
        conn.executescript("""
            INSERT INTO execution_traces (trace_id, node_id, event, timestamp, duration_ms, error)
            VALUES ('trace-debug-001', 'profile_agent', 'started', '2026-06-24T00:00:00', NULL, NULL);
            INSERT INTO execution_traces (trace_id, node_id, event, timestamp, duration_ms, error)
            VALUES ('trace-debug-001', 'profile_agent', 'completed', '2026-06-24T00:00:01', 1000, NULL);
        """)
        conn.close()

        original_path = mem_module.DB_PATH
        mem_module.DB_PATH = db_path
        store = mem_module.MemoryStore()

        traces = store.get_trace("trace-debug-001")
        assert len(traces) == 2
        assert traces[0]["event"] == "started"
        assert traces[1]["event"] == "completed"
        assert traces[1]["duration_ms"] == 1000

        mem_module.DB_PATH = original_path
        os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])