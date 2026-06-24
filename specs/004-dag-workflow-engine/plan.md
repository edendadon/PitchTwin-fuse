# Implementation Plan: DAG Workflow Engine

**Branch**: `004-dag-workflow-engine` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-dag-workflow-engine/spec.md`

## Summary

Build a DAG-based WorkflowEngine that orchestrates proposal generation via a directed acyclic graph of nodes (AgentNode, ParallelNode, SequentialNode, HumanGateNode). Each node executes with bounded retries, per-node timeouts, max-iteration guards, and checkpoint persistence to SQLite. A global 240s timeout and 3-failure circuit breaker provide determinism. Execution traces are exposed via `GET /debug/trace/<trace_id>`.

## Technical Context

**Language/Version**: Python 3.11 (existing codebase)  
**Primary Dependencies**: Flask (existing), sqlite3 (stdlib), threading (stdlib); optional: asyncio if background execution is later needed  
**Storage**: SQLite — extends existing `data/pitchtwin.db` with `workflow_checkpoints` and `execution_traces` tables  
**Testing**: pytest (existing project convention from `tests/test_agents.py`)  
**Target Platform**: Linux server (Flask application, Docker)  
**Project Type**: Python library module (`orchestrator/workflow.py` + `orchestrator/memory.py`) consumed by Flask routes  
**Performance Goals**: Global workflow timeout 240s; per-node timeout default 60s; checkpoint after every node  
**Constraints**: Synchronous execution within Flask request lifecycle; must work with bare agent functions if Issue #1 harness not yet complete; timebox 3 hours  
**Scale/Scope**: Single in-process workflow at a time; no concurrent pipeline runs; proposal_id-scoped checkpoint lookup

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Determinism Over Speed** | PASS | Bounded retries (FR-003), per-node timeouts (FR-004), max-iteration guards (FR-005), circuit breaker (FR-008) fully specified |
| **II. Validation at Every Boundary** | CONDITIONAL | Schema validation is Issue #1's responsibility. Engine validates node inputs/outputs as JSON serialization only. Adapter pattern (FR-001 assumption) handles Pydantic schemas if Issue #1 is present |
| **III. Observability by Default** | PASS | Execution traces (FR-009), debug endpoint (FR-010), checkpoint persistence (FR-007) fully specified |
| **IV. No Hallucination** | N/A | Not applicable to orchestration engine; enforced by agents (Issue #1) |
| **V. Test-First for Agents** | N/A | Agent eval is out of scope for this feature; engine itself should have unit tests |
| **Orchestration as DAG** | PASS | DAG-based with AgentNode, ParallelNode, SequentialNode, HumanGateNode explicitly specified (FR-002) |
| **Checkpointing mandatory** | PASS | FR-007, FR-012 fully specify checkpointing behavior |

**Gate Result**: PASS — no violations. Condition on Issue #1 integration is acceptable per spec assumptions.

## Project Structure

### Documentation (this feature)

```text
specs/004-dag-workflow-engine/
├── plan.md              # This file (/spec.plan command output)
├── research.md          # Phase 0 output — architecture patterns, loop detection, adapter design
├── data-model.md        # Phase 1 output — WorkflowNode, Checkpoint, ExecutionTrace entities
├── quickstart.md        # Phase 1 output — validation scenarios for engine and Flask route
├── contracts/           # Phase 1 output — WorkflowEngine API contract, checkpoint schema
└── tasks.md             # Phase 2 output (/spec.tasks command — NOT created by /spec.plan)
```

### Source Code (repository root)

```text
orchestrator/
├── __init__.py
├── workflow.py          # WorkflowEngine, node classes (AgentNode, ParallelNode, SequentialNode, HumanGateNode)
├── memory.py            # MemoryStore (checkpoint + trace persistence via SQLite)
└── adapter.py           # Thin wrapper for bare agent functions (Issue #1 adapter if harness not ready)

# Existing files updated:
orchestrator.py          # Rewritten to use WorkflowEngine
app.py                   # New route: GET /debug/trace/<trace_id>
db.py                    # New tables: workflow_checkpoints, execution_traces

# New test file:
tests/
└── test_workflow_engine.py  # Unit tests for WorkflowEngine, checkpoint, circuit breaker
```

**Structure Decision**: Single `orchestrator/` module containing the engine and its memory store. Adapter pattern keeps engine decoupled from Issue #1 harness. Flask routes remain in `app.py`. New SQLite tables extend existing `db.py` schema.

## Triage Framework: [SYNC] vs [ASYNC] Classification

**Execution Strategy**: This feature is primarily synchronous (pipeline executes within a single Flask request). Background/async execution is explicitly a Non-Goal.

### Preliminary Task Classification

| Task Category | Estimated [SYNC] Tasks | Estimated [ASYNC] Tasks | Rationale |
|---------------|----------------------|----------------------|-----------|
| Business Logic | 8 | 0 | Engine is synchronous by design; DAG execution is deterministic |
| Data Operations | 3 | 0 | Checkpoint read/write is synchronous SQLite |
| UI Components | 0 | 0 | No UI work in this feature |
| Integrations | 2 | 0 | Flask route, existing db.py — synchronous |
| Infrastructure | 2 | 0 | SQLite tables, circuit breaker, timeout mechanisms |

### Triage Decision Criteria Applied

**High-Risk [SYNC] Classifications:**

- WorkflowEngine.execute() — core loop with timeout/circuit-breaker logic; must be human-reviewed
- DAG validation (cycle detection) — incorrect DAG handling causes infinite loops
- Checkpoint resume logic — wrong checkpoint selection corrupts pipeline state

**Agent-Delegated [ASYNC] Classifications:**

- Node class implementations (AgentNode, ParallelNode, SequentialNode, HumanGateNode) — boilerplate with well-specified interfaces
- SQLite table schema in db.py — standard patterns
- Flask debug endpoint — simple read-only query
- Unit test scaffolding — follows existing pytest patterns

### Triage Audit Trail

| Task | Classification | Primary Criteria | Risk Level | Rationale |
|------|----------------|------------------|------------|-----------|
| WorkflowEngine core loop | SYNC | Complex timeout + circuit breaker logic | High | Core determinism depends on correct implementation |
| DAG cycle validation | SYNC | Prevents infinite loops | High | Must validate before execution starts |
| MemoryStore checkpoint I/O | SYNC | State corruption risk | High | Wrong checkpoint = wrong resume |
| AgentNode implementation | ASYNC | Well-specified interface, simple | Low | Standard wrapper around agent call |
| ParallelNode implementation | ASYNC | Thread.join(timeout) pattern | Medium | Timeout semantics must be correct |
| SequentialNode implementation | ASYNC | Simple sequential execution | Low | Straightforward loop |
| HumanGateNode implementation | ASYNC | Status polling pattern | Medium | Needs correct state machine |
| SQLite schema (workflow_checkpoints) | ASYNC | Standard CREATE TABLE | Low | Well-understood pattern |
| SQLite schema (execution_traces) | ASYNC | Standard CREATE TABLE | Low | Well-understood pattern |
| Flask /debug/trace endpoint | ASYNC | Simple SELECT + JSON | Low | Read-only query |
| Unit tests for WorkflowEngine | ASYNC | pytest pattern exists | Low | Follows existing test_agents.py |

## Complexity Tracking

No constitution violations requiring justification. All requirements align with existing patterns.

## Phase 0: Research

### Unknowns Identified

The following require research to resolve before Phase 1 design:

**R-1: DAG definition format**
How does the caller define the DAG? Options: dataclass-based nodes with explicit edges list, dict-based config, or YAML. This determines the API surface of `WorkflowEngine.execute(dag)`.

**R-2: Loop-detection algorithm**
How does the engine detect "same output repeated N times"? Compare hash of output? Compare full output equality? What counts as "progress"?

**R-3: Adapter pattern for bare functions**
If Issue #1 is not complete, the engine wraps bare agent functions. What's the minimal interface the adapter must expose?

**R-4: ParallelNode timeout semantics**
When a ParallelNode has multiple children, is the timeout per child (any child >60s fails) or total (all children must finish within 60s total)?

**R-5: DAG cycle validation algorithm**
What algorithm does the engine use to validate the DAG is acyclic before execution? Topological sort attempt? DFS-based cycle detection?

### Research Findings

**R-1: DAG definition format**
Decision: Dict-based nodes with an explicit `edges` list. Each node is a dict with `id`, `type`, `config` (retries, timeout, max_iterations), and `inputs` (list of upstream node IDs). The edges list defines parent→child relationships. Simple, serializable, no new class hierarchy needed for the DAG definition itself. Node execution classes (AgentNode, etc.) are separate from the definition format.

**R-2: Loop-detection algorithm**
Decision: Hash-based comparison. On each node execution, compute SHA-256 of the serialized output. Maintain a ring buffer of the last 5 output hashes. If all 5 hashes are identical (meaning 5 identical outputs), trigger max_iterations breach. Simple, deterministic, low overhead.

**R-3: Adapter pattern**
Decision: Minimal interface — callable `(input_data: dict) -> dict`. The adapter wraps any callable and exposes `.execute(input_data)` returning dict. This matches the existing agent function signature `run_agent(input, llm_client) -> dict`. If Issue #1 is present, the adapter uses `Agent.execute()`.

**R-4: ParallelNode timeout semantics**
Decision: Per-child timeout. Each child node runs in its own thread with `thread.join(timeout_sec)`. If a child exceeds its timeout, only that child is aborted. The ParallelNode waits for all children (or timeout). This is the more intuitive failure isolation model.

**R-5: DAG cycle validation**
Decision: Kahn's algorithm (topological sort). Attempt to produce a topological ordering of all nodes. If Kahn's algorithm fails (remaining nodes with no in-degree of zero), cycles exist. Report the cycle nodes in the error. O(V+E) complexity, same as DFS.

## Phase 1: Design & Contracts

### Data Model

**WorkflowNode (in-memory definition, not persisted)**
```python
@dataclass
class WorkflowNode:
    id: str                          # unique node identifier
    type: str                        # "agent" | "parallel" | "sequential" | "human_gate"
    config: NodeConfig               # max_retries, timeout_sec, max_iterations
    inputs: list[str]                # list of upstream node IDs (empty for roots)
```

**NodeConfig (in-memory)**
```python
@dataclass
class NodeConfig:
    max_retries: int = 2
    timeout_sec: int = 60
    max_iterations: int = 5
```

**WorkflowCheckpoint (SQLite — workflow_checkpoints table)**
```sql
CREATE TABLE workflow_checkpoints (
    proposal_id TEXT NOT NULL,        -- key for checkpoint lookup
    trace_id TEXT NOT NULL,           -- UUID for this invocation
    node_id TEXT NOT NULL,            -- last completed node
    phase TEXT NOT NULL,              -- human-readable phase name
    input_data TEXT NOT NULL,         -- JSON serialized node input
    output_data TEXT NOT NULL,        -- JSON serialized node output
    status TEXT NOT NULL,             -- 'completed' | 'failed' | 'in_progress'
    created_at TEXT NOT NULL,
    PRIMARY KEY (proposal_id, node_id)
);
```

**ExecutionTrace (SQLite — execution_traces table)**
```sql
CREATE TABLE execution_traces (
    trace_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    event TEXT NOT NULL,              -- 'started' | 'completed' | 'failed' | 'timed_out' | 'circuit_breaker'
    timestamp TEXT NOT NULL,
    duration_ms INTEGER,
    error TEXT,
    PRIMARY KEY (trace_id, node_id, event, timestamp)
);
```

### Contracts

**WorkflowEngine API**
```python
class WorkflowEngine:
    def __init__(self, dag: list[dict], checkpoint_store: MemoryStore, trace_store: MemoryStore):
        """
        dag: list of node dicts with keys: id, type, config, inputs
        checkpoint_store: MemoryStore instance for checkpoint persistence
        trace_store: MemoryStore instance for trace persistence
        """

    def execute(self, proposal_id: str, context: dict) -> ExecutionResult:
        """
        Runs the DAG for the given proposal_id.
        Creates new trace_id per invocation.
        Checks for in-progress checkpoint and resumes if found.
        Returns ExecutionResult with status, outputs, trace_id.
        Raises: WorkflowError, CircuitBreakerOpen, WorkflowTimeout
        """

    def resume(self, proposal_id: str) -> ExecutionResult:
        """
        Resume from the latest in_progress checkpoint for proposal_id.
        """
```

**MemoryStore API**
```python
class MemoryStore:
    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None: ...
    def get_latest_checkpoint(self, proposal_id: str) -> WorkflowCheckpoint | None: ...
    def get_latest_in_progress(self, proposal_id: str) -> WorkflowCheckpoint | None: ...
    def save_trace(self, trace: ExecutionTrace) -> None: ...
    def get_trace(self, trace_id: str) -> list[ExecutionTrace]: ...
```

### Quickstart

**Validation scenarios:**

1. **Happy path**: Run `run_proposal_pipeline()` → verify all nodes complete → verify trace at `/debug/trace/<id>` shows all nodes green
2. **Resume after crash**: Kill process mid-pipeline → re-run → verify Phase 1 skipped → verify full completion
3. **Loop prevention**: Mock agent returning same output 5 times → verify pipeline halts with "max_iterations exceeded"
4. **Circuit breaker**: Mock 3 failing agents → verify 4th is not called → verify "circuit breaker" error
5. **Global timeout**: Mock agent with 300s sleep → verify pipeline aborts at 240s with "timeout" status

**Setup**: `python tests/test_workflow_engine.py` (or `pytest` if conftest is set up)
**Run**: `python app.py` → `curl http://localhost:5000/api/health`
**Debug trace**: `curl http://localhost:5000/debug/trace/<trace_id>`

### Agent Context Update

Update `AGENTS.md` section `<!-- SPECKIT START -->` to `<!-- SPECKIT END -->` with:
```
specs/004-dag-workflow-engine/plan.md
```