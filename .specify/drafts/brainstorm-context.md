# Brainstorm Context: DAG Orchestrator with Checkpointing, Loop Prevention, Timeouts

## Problem Statement

The current `orchestrator.py` is a fragile script with hardcoded phases, raw `threading.Thread`, no state machine, no checkpointing, no loop detection, and no timeout management. A process kill mid-pipeline loses all progress. An agent stuck in an infinite loop hangs the pipeline forever. There is no execution trace for debugging.

**Pain point**: Cannot recover from failures, cannot observe execution flow, cannot bound execution time — all unacceptable for a demo-ready system.

## Key Concepts

- **Workflow Node**: A single unit of execution (agent call, parallel fork, human gate, etc.) with defined inputs, outputs, and metadata (retries, timeout, max iterations)
- **DAG (Directed Acyclic Graph)**: Nodes connected by directed edges; execution follows topological order; cycles are forbidden by construction
- **Checkpoint**: Persisted execution state after each node completes (phase + outputs + trace) — enables resume after crash
- **Loop Prevention**: `max_iterations` counter per node — if the same node fires N times without progress, the circuit breaks
- **Circuit Breaker**: N consecutive failures across the workflow → halt execution
- **Human Gate**: A pause point where execution waits for external approval before proceeding
- **Execution Trace**: Log of every node execution (start, end, duration, output, errors) — visible via debug endpoint

## Approaches Considered

### Approach A: Embedded State Machine (Minimal Refactor)
- **How it works**: Replace raw threading with an enum-based state machine in `orchestrator.py`. Track phase in SQLite (`workflow_checkpoints` table). Use `Thread.join(timeout=)` for per-phase timeouts. Wrap each agent call in a retry loop with max iterations.
- **Tradeoffs**: Low code change surface (rewrite ~1 file). No new abstractions. But state machine logic gets tangled as complexity grows. Adding new node types (human gate, parallel fork) requires modifying the state machine enum and switch logic. No visual DAG structure.
- **Risks**: State machine becomes unmanageable as we add features (human gate, retry orchestration). Testing is harder because logic is embedded in a single file. Not extensible for future node types.
- **Best for**: Teams that need a quick fix and have low future complexity expectations.

### Approach B: DAG Workflow Engine (Dedicated Module)
- **How it works**: Create `orchestrator/workflow.py` with a `WorkflowEngine` class and node types (`AgentNode`, `ParallelNode`, `HumanGateNode`, `SequentialNode`). Define the pipeline as a DAG declaration. Engine compiles the DAG, topologically sorts it, and executes nodes with checkpointing after each. `orchestrator/memory.py` handles SQLite checkpointing. Global workflow timeout (240s). Per-node: `max_retries`, `timeout_sec`, `max_iterations`. Circuit breaker: 3 consecutive failures → halt.
- **Tradeoffs**: Higher up-front code (2 new files + rewrite of orchestrator.py). Clean separation of concerns — engine, nodes, memory store are independently testable. Adding new node types is a class addition. DAG structure is explicit and inspectable.
- **Risks**: Over-engineering if the pipeline stays at 5 nodes. Depends on Issue #1 (Agent base class) for `Agent.execute()` interface — needs coordination. Timebox pressure (3 hours) may force scope trimming.
- **Best for**: Teams expecting to grow the pipeline, need production reliability, and want testable components.

### Approach C: Event-Driven / Message Queue
- **How it works**: Each agent publishes results to an in-process or SQLite-backed queue. A supervisor process (or async loop) consumes from the queue and dispatches the next node. Checkpointing is implicit via queue state. Built-in retry via requeue.
- **Tradeoffs**: Decoupled and flexible — new nodes just publish/subscribe to queues. But introduces queue management complexity (ordering, message dedup, poison messages). Overkill for a 4-phase linear pipeline. Testing requires queue infrastructure.
- **Risks**: Significant complexity for marginal gain over Approach B. Eventual consistency makes deterministic execution traces harder. Not well-suited for the synchronous Flask request model.
- **Best for**: Highly asynchronous workflows with many concurrent agents and dynamic branching.

## Architecture Notes

- **Integration with existing system**: The orchestrator is called synchronously from `app.py`'s `/proposal/new` route. The DAG engine must support both synchronous execution (for the current request model) and background execution (future).
- **Data layer**: New tables `workflow_checkpoints` (phase, node_id, input_data, output_data, status, created_at) and `execution_traces` (trace_id, node_id, event, timestamp, duration_ms, error) in existing SQLite. Use existing `db.py` connection management.
- **Flask route**: `GET /debug/trace/<trace_id>` — reads from `execution_traces` table and returns JSON execution graph (node sequence, timing, errors).
- **Dependency on Issue #1**: The DAG orchestrator assumes agents expose `Agent.execute(context)` with standardized input/output schema, trace logging, and guardrails. If Issue #1 is not done, the engine must wrap existing bare functions.
- **Current pipeline structure** (4 phases):
  1. Parallel: Profile Agent + Client Research Agent
  2. Sequential: Combined Agent (Matching + Writer + Gap)
  3. On-demand: Persona Agent (per message, outside pipeline)
  4. Triggered: Debrief Agent (session end, outside pipeline)

  The DAG engine should initially cover Phases 1-2 (the proposal pipeline), with hooks for Phase 3-4 integration.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Timebox exceeded (3h) | H | H | Scope to core DAG engine + checkpointing; defer debug endpoint to follow-up |
| Issue #1 (Agent harness) not complete | M | H | Design engine to work with both `Agent.execute()` and bare functions via adapter |
| SQLite concurrency issues with checkpointing | M | M | Use WAL mode for concurrent reads; serialized writes via single-writer pattern |
| Circuit breaker false positives in parallel phase | L | M | Circuit breaker counts consecutive failures per node type, not globally |
| Human gate adds UI complexity to simple pipeline | M | L | Human gate is a "pause + poll" — no real-time push needed |

## Open Questions

- Should the DAG engine support async execution (asyncio) for the background pipeline case, or stay synchronous for now?
- Is the debug trace endpoint a P0 deliverable or can it be a follow-up?
- How does the engine handle the Persona Agent (Phase 3) and Debrief Agent (Phase 4) which are triggered outside the main pipeline?
- Should checkpointing serialize full input/output data, or just status + references? Tradeoff: storage vs resume fidelity.
- What is the exact interface contract with Issue #1's `Agent` base class? (Needs coordination with #1 implementation.)

## Recommended Direction

**Approach B: DAG Workflow Engine** — dedicated `orchestrator/workflow.py` + `orchestrator/memory.py`.

Rationale:
- The issue explicitly calls for "DAG-based orchestrator" — this matches the stated requirement
- Clean separation of concerns enables independent testing of engine, nodes, and persistence
- Adding node types (HumanGateNode, ParallelNode) is a class addition, not a refactor
- The debug trace endpoint naturally reads from the execution_traces table the engine populates
- The 3-hour timebox is tight but the engine can be scoped: core DAG execution + checkpointing + timeouts + loop prevention. The debug endpoint and human gate can be deferred or simplified.

Key design principle: The engine should know nothing about agent internals — it orchestrates nodes, each of which calls `Agent.execute()` (or wraps a bare function) and reports back. This clean interface is the key to managing complexity.
