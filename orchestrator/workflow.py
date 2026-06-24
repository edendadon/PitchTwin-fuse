"""
orchestrator/workflow.py — DAG WorkflowEngine

Core components:
- NodeConfig, WorkflowNode dataclasses
- Error types: WorkflowError, WorkflowTimeout, CircuitBreakerOpen, MaxIterationsExceeded, DAGValidationError
- WorkflowEngine: DAG execution with checkpointing, timeouts, circuit breaker, loop detection
- Node types: AgentNode, ParallelNode, SequentialNode, HumanGateNode
"""

from __future__ import annotations

import json
import threading
import time
import uuid
import hashlib
import queue as queue_module
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

# === Dataclasses ===

@dataclass
class NodeConfig:
    max_retries: int = 2
    timeout_sec: int = 60
    # Single-shot by default. Set max_iterations > 1 to opt a node into loop
    # detection: it is re-fired while it keeps producing identical output and
    # halts with MaxIterationsExceeded once it hits this many identical results.
    max_iterations: int = 1
    max_wait_sec: int | None = None  # for human_gate nodes


@dataclass
class WorkflowNode:
    id: str
    type: str  # "agent" | "parallel" | "sequential" | "human_gate"
    config: NodeConfig = field(default_factory=NodeConfig)
    inputs: list[str] = field(default_factory=list)  # upstream node IDs
    agent_fn: Callable[[dict], dict] | None = None  # only for type="agent"


# === Error Types ===

class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class WorkflowTimeout(WorkflowError):
    """Raised when the global workflow timeout is exceeded. Aborts the pipeline."""
    pass


class NodeTimeout(WorkflowError):
    """Raised when a single node exceeds its own timeout_sec. Retryable (counts as a node failure)."""
    pass


class CircuitBreakerOpen(WorkflowError):
    """Raised when circuit breaker trips after consecutive failures."""
    pass


class MaxIterationsExceeded(WorkflowError):
    """Raised when an agent fires max_iterations times without producing new output."""
    pass


class DAGValidationError(WorkflowError):
    """Raised when the DAG has cycles or invalid structure."""
    pass


# === WorkflowEngine ===

class WorkflowEngine:
    def __init__(
        self,
        dag: list[dict],
        checkpoint_store,
        trace_store,
        global_timeout_sec: int = 240,
        circuit_breaker_threshold: int = 3,
    ):
        self.dag = dag
        self.checkpoint_store = checkpoint_store
        self.trace_store = trace_store
        self.global_timeout_sec = global_timeout_sec
        self.circuit_breaker_threshold = circuit_breaker_threshold

        self._nodes: dict[str, WorkflowNode] = {}
        self._outputs: dict[str, Any] = {}
        self._circuit_failures: int = 0

        self._parse_dag(dag)

    def _parse_dag(self, dag: list[dict]) -> None:
        for node_dict in dag:
            config_dict = node_dict.get("config", {})
            config = NodeConfig(
                max_retries=config_dict.get("max_retries", 2),
                timeout_sec=config_dict.get("timeout_sec", 60),
                max_iterations=config_dict.get("max_iterations", 1),
                max_wait_sec=config_dict.get("max_wait_sec"),
            )
            node = WorkflowNode(
                id=node_dict["id"],
                type=node_dict["type"],
                config=config,
                inputs=node_dict.get("inputs", []),
                agent_fn=node_dict.get("agent_fn"),
            )
            self._nodes[node.id] = node

    def _validate_dag(self) -> list[str]:
        """Kahn's algorithm: detect cycles and return execution order. Raises DAGValidationError on cycle."""
        in_degree = {node_id: 0 for node_id in self._nodes}
        adjacency = {node_id: [] for node_id in self._nodes}

        for node_id, node in self._nodes.items():
            for inp in node.inputs:
                if inp not in self._nodes:
                    raise DAGValidationError(f"Node {node_id} references unknown input node: {inp}")
                adjacency[inp].append(node_id)
                in_degree[node_id] += 1

        from collections import deque
        queue_deque = deque([n for n, d in in_degree.items() if d == 0])
        topo_order = []

        while queue_deque:
            node_id = queue_deque.popleft()
            topo_order.append(node_id)
            for child_id in adjacency[node_id]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue_deque.append(child_id)

        if len(topo_order) != len(self._nodes):
            remaining = [n for n, d in in_degree.items() if d > 0]
            raise DAGValidationError(f"DAG cycle detected. Nodes in cycle: {remaining}")

        return topo_order

    def _topological_sort_nodes(self) -> list[WorkflowNode]:
        order = self._validate_dag()
        return [self._nodes[node_id] for node_id in order]

    def _get_ready_nodes(self, completed: set[str]) -> list[WorkflowNode]:
        ready = []
        for node in self._nodes.values():
            if node.id in completed:
                continue
            if all(inp in completed for inp in node.inputs):
                ready.append(node)
        return ready

    def _execute_node(self, node: WorkflowNode, input_data: dict, trace_id: str) -> tuple[Any, str | None]:
        if node.type == "agent":
            return self._execute_agent_node(node, input_data, trace_id)
        elif node.type == "parallel":
            return self._execute_parallel_node(node, input_data, trace_id)
        elif node.type == "sequential":
            return self._execute_sequential_node(node, input_data, trace_id)
        elif node.type == "human_gate":
            return self._execute_human_gate_node(node, input_data, trace_id)
        else:
            raise WorkflowError(f"Unknown node type: {node.type}")

    def _execute_agent_node(self, node: WorkflowNode, input_data: dict, trace_id: str) -> tuple[Any, str | None]:
        agent_fn = node.agent_fn
        if agent_fn is None:
            raise WorkflowError(f"AgentNode {node.id} has no agent_fn")

        cfg = node.config
        # max_iterations <= 1 => single-shot node (the common case for the
        # proposal pipeline). max_iterations > 1 engages loop detection: the
        # agent is fired repeatedly and, if it yields the same output every
        # time without making progress, the pipeline halts.
        max_iterations = max(1, cfg.max_iterations)
        hash_buffer: list[str] = []
        last_error: str | None = None

        for _iteration in range(max_iterations):
            succeeded = False
            result: Any = None

            # Per-invocation retry loop for transient failures.
            for attempt in range(cfg.max_retries + 1):
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "event": "started",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": None,
                })
                start = time.time()
                try:
                    result = self._call_with_timeout(agent_fn, input_data, cfg.timeout_sec)
                    duration_ms = int((time.time() - start) * 1000)
                    self.trace_store.save_trace({
                        "trace_id": trace_id,
                        "node_id": node.id,
                        "event": "completed",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": duration_ms,
                        "error": None,
                    })
                    succeeded = True
                    break
                except WorkflowTimeout:
                    # Global deadline blown — abort the entire workflow.
                    self.trace_store.save_trace({
                        "trace_id": trace_id,
                        "node_id": node.id,
                        "event": "timed_out",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": int((time.time() - start) * 1000),
                        "error": f"global timeout of {self.global_timeout_sec}s exceeded",
                    })
                    raise
                except Exception as e:
                    last_error = str(e)
                    self.trace_store.save_trace({
                        "trace_id": trace_id,
                        "node_id": node.id,
                        "event": "failed",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": int((time.time() - start) * 1000),
                        "error": f"attempt {attempt + 1}: {last_error}",
                    })

            if not succeeded:
                # Retries exhausted for this invocation -> node failure.
                self._circuit_failures += 1
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "event": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": last_error,
                })
                return None, last_error

            result_hash = hashlib.sha256(
                json.dumps(result, sort_keys=True, default=str).encode()
            ).hexdigest()

            if max_iterations == 1:
                # Single-shot: accept the first successful output.
                self._circuit_failures = 0
                return result, None

            if hash_buffer and result_hash != hash_buffer[-1]:
                # Output changed -> the agent made progress, accept it.
                self._circuit_failures = 0
                return result, None

            hash_buffer.append(result_hash)

        # Fired max_iterations times with identical output -> loop detected.
        self.trace_store.save_trace({
            "trace_id": trace_id,
            "node_id": node.id,
            "event": "failed",
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": None,
            "error": f"max_iterations exceeded ({max_iterations} identical outputs)",
        })
        raise MaxIterationsExceeded(
            f"AgentNode {node.id}: {max_iterations} identical outputs, loop detected"
        )

    def _execute_parallel_node(self, node: WorkflowNode, input_data: dict, trace_id: str) -> tuple[dict, str | None]:
        child_outputs: dict[str, Any] = {}
        errors: list[str] = []
        child_threads: list[tuple[str, threading.Thread]] = []

        for child_id in node.inputs:
            child_node = self._nodes.get(child_id)
            if child_node is None or child_node.agent_fn is None:
                continue

            child_fn = child_node.agent_fn
            result_holder = queue_module.Queue()
            error_holder = queue_module.Queue()

            def make_wrapper(fn, inp, rh, eh):
                def wrapper():
                    try:
                        rh.put(fn(inp))
                    except Exception as e:
                        eh.put(e)
                return wrapper

            wrapped = make_wrapper(child_fn, input_data, result_holder, error_holder)
            t = threading.Thread(target=wrapped)
            child_threads.append((child_id, t, result_holder, error_holder))
            t.start()

        for child_id, t, result_holder, error_holder in child_threads:
            t.join(timeout=node.config.timeout_sec)
            if t.is_alive():
                errors.append(f"{child_id}: timeout after {node.config.timeout_sec}s")
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": child_id,
                    "event": "timed_out",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": f"timeout after {node.config.timeout_sec}s",
                })
                child_outputs[child_id] = None
            elif not error_holder.empty():
                exc = error_holder.get()
                errors.append(f"{child_id}: {exc}")
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": child_id,
                    "event": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": str(exc),
                })
                child_outputs[child_id] = None
            else:
                result = result_holder.get()
                child_outputs[child_id] = result
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": child_id,
                    "event": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": None,
                })

        if errors:
            self._circuit_failures += 1
            return None, f"ParallelNode {node.id} errors: {'; '.join(errors)}"
        self._circuit_failures = 0
        return child_outputs, None

    def _execute_sequential_node(self, node: WorkflowNode, input_data: dict, trace_id: str) -> tuple[dict, str | None]:
        result = input_data
        for child_id in node.inputs:
            child_node = self._nodes.get(child_id)
            if child_node is None or child_node.agent_fn is None:
                continue
            child_fn = child_node.agent_fn
            try:
                result = self._call_with_timeout(child_fn, result, node.config.timeout_sec)
            except Exception as e:
                self._circuit_failures += 1
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": child_id,
                    "event": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": str(e),
                })
                return None, str(e)
        self._circuit_failures = 0
        return result, None

    def _execute_human_gate_node(self, node: WorkflowNode, input_data: dict, trace_id: str) -> tuple[Any, str | None]:
        import db as db_module
        proposal_id = input_data.get("proposal_id")
        max_wait = node.config.max_wait_sec
        if proposal_id:
            proposal = db_module.get_proposal(proposal_id)
            if proposal:
                proposal.status = "awaiting_approval"
                db_module.save_proposal(proposal)

        gate_start = time.time()
        while True:
            import db as db_module
            if proposal_id:
                proposal = db_module.get_proposal(proposal_id)
                if proposal and proposal.status != "awaiting_approval":
                    break
                if max_wait and (time.time() - gate_start) > max_wait:
                    self.trace_store.save_trace({
                        "trace_id": trace_id,
                        "node_id": node.id,
                        "event": "failed",
                        "timestamp": datetime.utcnow().isoformat(),
                        "duration_ms": None,
                        "error": f"human gate timeout after {max_wait}s",
                    })
                    return None, f"HumanGate timeout after {max_wait}s"
            time.sleep(2)

        return input_data, None

    def _call_with_timeout(self, fn: Callable, input_data: dict, timeout_sec: int) -> Any:
        result_holder = queue_module.Queue()
        error_holder = queue_module.Queue()

        def wrapper():
            try:
                result_holder.put(fn(input_data))
            except Exception as e:
                error_holder.put(e)

        # Cap the wait at whatever is left of the global workflow budget so a
        # single long-running node cannot blow past the global timeout.
        effective_timeout = timeout_sec
        deadline = getattr(self, "_deadline", None)
        if deadline is not None:
            remaining = deadline - time.time()
            effective_timeout = max(0.0, min(timeout_sec, remaining))

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()
        t.join(timeout=effective_timeout)

        if t.is_alive():
            if deadline is not None and time.time() >= deadline:
                raise WorkflowTimeout(
                    f"Global timeout of {self.global_timeout_sec}s exceeded"
                )
            raise NodeTimeout(
                f"Node function {getattr(fn, '__name__', 'agent')} timed out after {timeout_sec}s"
            )
        if not error_holder.empty():
            raise error_holder.get()
        if not result_holder.empty():
            return result_holder.get()
        raise WorkflowError("Function returned no result and no error")

    def execute(self, proposal_id: str, context: dict) -> dict:
        trace_id = str(uuid.uuid4())
        global_start = time.time()
        self._deadline = global_start + self.global_timeout_sec
        completed: set[str] = set()
        outputs: dict[str, Any] = {}

        self._circuit_failures = 0

        topo_order = self._topological_sort_nodes()

        existing_in_progress = self.checkpoint_store.get_latest_in_progress(proposal_id)
        if existing_in_progress:
            # get_latest_in_progress() returns a dict whose output_data has already
            # been json-decoded by _row_to_checkpoint, so read it by key and do not
            # decode it again (mirrors the completed-checkpoint branch below).
            checkpoint_node_id = existing_in_progress["node_id"]
            for n in topo_order:
                if n.id == checkpoint_node_id:
                    break
                completed.add(n.id)
                outputs[n.id] = existing_in_progress["output_data"]
            outputs[checkpoint_node_id] = existing_in_progress["output_data"]
            completed.add(checkpoint_node_id)
        else:
            latest_checkpoint = self.checkpoint_store.get_latest_checkpoint(proposal_id)
            if latest_checkpoint:
                checkpoint_trace_id = latest_checkpoint["trace_id"]
                completed_rows = self.checkpoint_store.get_completed_checkpoints(proposal_id, checkpoint_trace_id)
                for row in completed_rows:
                    node_id = row["node_id"]
                    for n in topo_order:
                        if n.id == node_id:
                            completed.add(node_id)
                            outputs[node_id] = row["output_data"]
                            break

        if self._circuit_failures >= self.circuit_breaker_threshold:
            raise CircuitBreakerOpen(
                f"Circuit breaker open: {self._circuit_failures} consecutive failures"
            )

        try:
            topo_order = self._topological_sort_nodes()
        except DAGValidationError:
            raise

        for node in topo_order:
            if node.id in completed:
                continue

            if self._circuit_failures >= self.circuit_breaker_threshold:
                raise CircuitBreakerOpen(
                    f"Circuit breaker open: {self._circuit_failures} consecutive failures"
                )

            elapsed = time.time() - global_start
            if elapsed > self.global_timeout_sec:
                self.trace_store.save_trace({
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "event": "timed_out",
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": None,
                    "error": "global timeout exceeded",
                })
                self.checkpoint_store.save_checkpoint({
                    "proposal_id": proposal_id,
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "phase": f"timeout at {node.id}",
                    "input_data": json.dumps(context),
                    "output_data": json.dumps(outputs),
                    "status": "failed",
                    "created_at": datetime.utcnow().isoformat(),
                })
                raise WorkflowTimeout(
                    f"Global timeout of {self.global_timeout_sec}s exceeded at node {node.id}"
                )

            # Root nodes receive the workflow context; downstream nodes receive a
            # dict mapping each upstream node id to its output, so multi-input
            # nodes (e.g. the combined agent) can read each dependency by name.
            if node.inputs:
                input_data = {inp_id: outputs.get(inp_id) for inp_id in node.inputs}
            else:
                input_data = context

            result, error = self._execute_node(node, input_data, trace_id)

            if error:
                outputs[node.id] = None
                self.checkpoint_store.save_checkpoint({
                    "proposal_id": proposal_id,
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "phase": node.id,
                    "input_data": json.dumps(input_data),
                    "output_data": json.dumps(result) if result else json.dumps({}),
                    "status": "failed",
                    "created_at": datetime.utcnow().isoformat(),
                })
            else:
                outputs[node.id] = result
                completed.add(node.id)
                self.checkpoint_store.save_checkpoint({
                    "proposal_id": proposal_id,
                    "trace_id": trace_id,
                    "node_id": node.id,
                    "phase": node.id,
                    "input_data": json.dumps(input_data),
                    "output_data": json.dumps(result) if result else json.dumps({}),
                    "status": "completed",
                    "created_at": datetime.utcnow().isoformat(),
                })

        return {
            "trace_id": trace_id,
            "proposal_id": proposal_id,
            "status": "completed",
            "outputs": outputs,
            "duration_ms": int((time.time() - global_start) * 1000),
            "error": None,
        }

    def get_trace(self, trace_id: str) -> list[dict]:
        return self.trace_store.get_trace(trace_id)