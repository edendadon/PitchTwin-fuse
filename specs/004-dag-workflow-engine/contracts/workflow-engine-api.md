# Contract: WorkflowEngine API

## Phase 1 Output

### Overview

The `WorkflowEngine` is the core orchestration component. It accepts a DAG definition, executes nodes in topological order, persists checkpoints after each node, emits execution traces, and supports resume-from-checkpoint.

---

### Class: WorkflowEngine

#### Constructor

```python
def __init__(
    self,
    dag: list[dict],
    checkpoint_store: MemoryStore,
    trace_store: MemoryStore,
    global_timeout_sec: int = 240,
    circuit_breaker_threshold: int = 3,
):
    """
    dag: List of node definition dicts. Each dict:
        {
            "id": str,                    # unique node ID
            "type": str,                   # "agent" | "parallel" | "sequential" | "human_gate"
            "config": {                    # optional; defaults applied if missing
                "max_retries": int,       # default 2
                "timeout_sec": int,        # default 60
                "max_iterations": int,     # default 5
            },
            "inputs": list[str],          # upstream node IDs (empty for roots)
            "agent_fn": callable,         # only for type="agent"; the function to call
        }
    checkpoint_store: MemoryStore instance for checkpoint persistence
    trace_store: MemoryStore instance for trace event persistence
    global_timeout_sec: Maximum wall-clock time for entire workflow (default 240)
    circuit_breaker_threshold: Consecutive failures before halting (default 3)
    """
```

#### Methods

**execute(proposal_id: str, context: dict) -> ExecutionResult**
```python
def execute(self, proposal_id: str, context: dict) -> ExecutionResult:
    """
    Run the DAG for the given proposal_id.

    1. Generate new trace_id (UUID)
    2. Check for in-progress checkpoint for proposal_id
       - If found, resume from next unexecuted node
       - If not found, start fresh
    3. Execute nodes in topological order
    4. After each node: save checkpoint, emit trace event
    5. Enforce global timeout, circuit breaker
    6. Return ExecutionResult

    Raises:
        WorkflowTimeout: Global timeout exceeded
        CircuitBreakerOpen: 3 consecutive failures
        WorkflowError: DAG validation failed or unexpected error

    Returns ExecutionResult:
        {
            "trace_id": str,
            "proposal_id": str,
            "status": "completed" | "failed" | "timeout" | "circuit_broken",
            "outputs": dict[str, any],   # node_id -> output value
            "duration_ms": int,
            "error": str | None,
        }
    """
```

**get_trace(trace_id: str) -> list[ExecutionTrace]**
```python
def get_trace(self, trace_id: str) -> list[ExecutionTrace]:
    """
    Retrieve all trace events for a given trace_id, ordered by timestamp.
    Used by the Flask debug endpoint.

    Returns list of ExecutionTrace namedtuples.
    """
```

---

### Class: MemoryStore

```python
@dataclass
class WorkflowCheckpoint:
    proposal_id: str
    trace_id: str
    node_id: str
    phase: str
    input_data: dict
    output_data: dict
    status: str   # "completed" | "failed" | "in_progress"
    created_at: str

@dataclass
class ExecutionTrace:
    trace_id: str
    node_id: str
    event: str      # "started" | "completed" | "failed" | "timed_out" | "circuit_breaker"
    timestamp: str  # ISO timestamp
    duration_ms: int | None
    error: str | None
```

**Methods:**
```python
def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None: ...
def get_latest_in_progress(self, proposal_id: str) -> WorkflowCheckpoint | None: ...
def get_latest_completed_node(self, proposal_id: str, trace_id: str) -> WorkflowCheckpoint | None: ...
def save_trace(self, trace: ExecutionTrace) -> None: ...
def get_trace(self, trace_id: str) -> list[ExecutionTrace]: ...
```

---

### Node Types

**AgentNode**
- Calls `agent_fn(input_data)` with retries and timeout
- Compares output hash to ring buffer for loop detection
- Saves checkpoint on completion or final failure

**ParallelNode**
- Executes child nodes concurrently in threads
- Each child has its own timeout (per-child timeout model)
- Waits for all children before returning
- Fails if any child fails after retries

**SequentialNode**
- Executes child nodes one at a time in order
- Stops and fails on first child failure

**HumanGateNode**
- Sets proposal status to "awaiting_approval"
- Blocks execution until external approval
- Polls `db.get_proposal(proposal_id).status != "awaiting_approval"` to resume

---

### DAG Definition Example

```python
dag = [
    {
        "id": "profile_agent",
        "type": "agent",
        "config": {"max_retries": 2, "timeout_sec": 60, "max_iterations": 5},
        "inputs": [],
        "agent_fn": run_profile_agent,
    },
    {
        "id": "client_research",
        "type": "agent",
        "config": {"max_retries": 2, "timeout_sec": 60, "max_iterations": 5},
        "inputs": [],
        "agent_fn": run_client_research_agent,
    },
    {
        "id": "phase1_parallel",
        "type": "parallel",
        "config": {"timeout_sec": 120},
        "inputs": ["profile_agent", "client_research"],
        "agent_fn": None,  # not used for parallel/sequential/human_gate types
    },
    {
        "id": "combined_agent",
        "type": "agent",
        "config": {"max_retries": 2, "timeout_sec": 90, "max_iterations": 3},
        "inputs": ["phase1_parallel"],
        "agent_fn": run_combined_agent,
    },
]
```

---

### Error Types

```python
class WorkflowError(Exception): pass
class WorkflowTimeout(WorkflowError): pass
class CircuitBreakerOpen(WorkflowError): pass
class MaxIterationsExceeded(WorkflowError): pass
class DAGValidationError(WorkflowError): pass
```

---

### Integration Points

| Component | Integration |
|-----------|-------------|
| `orchestrator.py` | Creates `WorkflowEngine` instance, passes DAG, calls `execute()` |
| `app.py` | Calls `run_proposal_pipeline()` which uses WorkflowEngine under the hood |
| `db.py` | Provides connection; `MemoryStore` uses same connection pattern |
| `/debug/trace/<trace_id>` | Calls `WorkflowEngine.get_trace()` or directly queries `MemoryStore` |