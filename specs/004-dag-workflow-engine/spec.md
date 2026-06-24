# Feature: DAG Workflow Engine

## Clarifications

### Session 2026-06-24

- Q: How does the engine uniquely identify a workflow run for checkpointing and trace purposes? Is it a new UUID per invocation, or derived from the proposal_id so resume automatically picks up the right checkpoint? → A: Each pipeline invocation gets a new unique trace UUID, but the checkpoint is keyed by `proposal_id`. The engine resumes by scanning for the latest in-progress checkpoint for that proposal. This keeps traces cleanly separated per invocation while enabling deterministic resume.

## Feature Overview

**Short Name**: dag-workflow-engine

**Description**: Replace the current raw-threading orchestrator (`orchestrator.py`) with a deterministic DAG-based WorkflowEngine. The engine orchestrates nodes (AgentNode, ParallelNode, HumanGateNode) with per-node retries, timeouts, max-iteration guards, circuit breaking, and SQLite checkpointing for resume-after-failure. Exposes execution traces via a debug endpoint.

## Mission Brief

**Goal**: Build a DAG-based WorkflowEngine that replaces the current raw-threading orchestrator with deterministic node execution, checkpointing, loop prevention, timeout management, and circuit breaking.

**Success Criteria**:
- Pipeline completes end-to-end with full execution trace visible at `/debug/trace/<id>`
- Killing the process mid-pipeline and restarting resumes from the last checkpoint
- An infinite loop in an agent is caught by `max_iterations=5` and the pipeline halts cleanly
- Human gate pauses proposal at "awaiting approval" state
- Global workflow timeout (240s) aborts stuck pipelines

**Constraints**:
- Depends on Issue #1 (Agent harness base class) — must work with both `Agent.execute()` and bare function wrappers
- Must integrate with existing SQLite (new tables: `workflow_checkpoints`, `execution_traces`)
- Must integrate with existing Flask route `/proposal/new` (synchronous call)
- Timebox: 3 hours

## Key Concepts

- **WorkflowNode**: Base unit of execution. Each node has a unique ID, type (agent, parallel, sequential, human gate), input data, output data, and execution metadata (retries, timeout, max iterations).
- **Checkpoint**: After each node completes, the engine persists the full execution state (phase, node results, trace events) to SQLite. On restart, the engine reads the latest checkpoint and resumes from the next unexecuted node.
- **Circuit Breaker**: Tracks consecutive failures across the workflow. If three nodes fail in a row, the engine halts and reports the failure. Prevents cascading failures from wasting LLM budget.
- **Execution Trace**: Every node execution logs start time, end time, duration, status (success/failure/skipped), output summary, and error details to an `execution_traces` table.

## User Scenarios & Testing

### Scenario A: Happy Path (P0)
Given a valid consultant profile and client brief  
When the user triggers `/proposal/new`  
Then the pipeline completes all phases  
And a Proposal is stored with `status=ready`  
And visiting `/debug/trace/<trace_id>` shows the execution DAG with all nodes green.

### Scenario B: Resume After Crash (P0)
Given a running pipeline that has completed Phase 1  
When the process is killed and restarted  
And the user triggers `/proposal/new` again for the same profile  
Then the engine detects the existing checkpoint  
And resumes from Phase 2 without re-running Phase 1  
And the final proposal is complete.

### Scenario C: Loop Prevention (P0)
Given an agent that enters an infinite loop (repeating the same output)  
When the agent has fired 5 times without progress  
Then the engine detects the max-iteration breach  
And halts the pipeline with a "max_iterations exceeded" error.

### Scenario D: Circuit Breaker Trip
Given three consecutive agent failures  
When the fourth agent is about to execute  
Then the circuit breaker trips  
And the pipeline halts with "circuit breaker: 3 consecutive failures" error.

### Scenario E: Human Gate Pause
Given a pipeline that has reached a HumanGateNode  
When the node executes  
Then the proposal status is set to "awaiting approval"  
And the pipeline pauses until external approval is received.

### Scenario F: Global Timeout
Given a pipeline running for over 240 seconds  
When the timeout threshold is exceeded  
Then the engine aborts all running nodes  
And the pipeline status is set to "timeout".

## Functional Requirements

### FR-001: WorkflowEngine
The engine accepts a DAG definition (list of nodes with edges) and executes it in topological order. It supports synchronous execution for the current Flask request model.

### FR-002: Node Types
The engine supports at minimum: AgentNode (single agent call), ParallelNode (fan-out to multiple child nodes), SequentialNode (ordered child nodes), HumanGateNode (pauses for external approval).

### FR-003: Per-Node Retries
Each agent node has a configurable max_retries (default: 2). On failure, the node retries with the same input. After exhausting retries, the node is marked as failed and the circuit breaker counter increments.

### FR-004: Per-Node Timeout
Each node has a configurable timeout_sec (default: 60s for agents). If the node exceeds its timeout, it is aborted and marked as failed.

### FR-005: Max Iterations / Loop Prevention
Each agent node has a configurable max_iterations (default: 5). If the node fires this many times without producing new or different output, the pipeline halts with a loop-detection error.

### FR-006: Global Workflow Timeout
The engine has a configurable global timeout (default: 240s). If the total workflow execution exceeds this, all running nodes are aborted and the pipeline status is set to "timeout".

### FR-007: Checkpoint Persistence
After each node completes (success or failure), the engine persists the node's input, output, and execution metadata to SQLite under a checkpoint keyed by `proposal_id`. Each invocation also generates a new unique `trace_id` to keep traces cleanly separated. On engine initialization, it scans for the latest in-progress checkpoint for the given `proposal_id` and resumes from the next unexecuted node.

### FR-008: Circuit Breaker
The engine tracks consecutive failures across all nodes. After 3 consecutive failures, the engine halts the pipeline and refuses to execute further nodes. A manual reset clears the breaker.

### FR-009: Execution Trace
Every node execution emits trace events (node_id, event type, timestamp, duration_ms, error). These are persisted to an execution_traces table and exposed via a Flask debug endpoint.

### FR-010: Debug Trace Endpoint
A Flask route `GET /debug/trace/<trace_id>` returns a JSON representation of the execution trace, including all nodes, their status, timing, and error details.

### FR-011: Human Gate State Management
A HumanGateNode sets the proposal status to "awaiting approval" and waits. A separate mechanism (polling or manual trigger) marks the gate as approved, after which the pipeline resumes.

### FR-012: Resume-from-Checkpoint
On startup, the engine scans for the latest checkpoint with status "in_progress" for the given `proposal_id`. If found, it skips all completed nodes and resumes execution from the first unexecuted node. Each invocation generates a new `trace_id`; the checkpoint lookup uses `proposal_id` to find the right context.

## Success Criteria

- Pipeline completes end-to-end in under 240 seconds with full execution trace available
- A crashed pipeline resumes from its last checkpoint without re-executing completed phases
- An agent stuck in a loop is detected and halted within 5 iterations
- Three consecutive failures trip the circuit breaker and halt execution
- Global workflow timeout aborts execution cleanly after 240 seconds
- The debug endpoint returns structured trace data for any completed or in-progress pipeline

## Key Entities

### WorkflowCheckpoint
- proposal_id (string) — key used for checkpoint lookup and resume
- trace_id (string) — unique UUID for this specific pipeline invocation
- phase (string) — which phase/node was last completed
- input_data (JSON) — serialized input to the node
- output_data (JSON) — serialized output from the node
- status (string) — completed | failed | in_progress
- created_at (timestamp)

### ExecutionTrace
- trace_id (string) — UUID for the entire workflow run
- node_id (string)
- event (string) — started | completed | failed | timed_out | circuit_breaker
- timestamp (ISO timestamp)
- duration_ms (integer)
- error (string, nullable)

## Assumptions

- The existing `db.py` connection management and SQLite infrastructure is reused for new tables
- The DAG engine initially covers Phases 1-2 of the pipeline (proposal generation) only; Phases 3-4 (Persona Agent, Debrief Agent) are out of scope for this feature
- The human gate is implemented as a polling model (status check + manual resume trigger), not real-time push
- The engine runs synchronously within the Flask request lifecycle (background workers are a future consideration)
- If Issue #1 (Agent harness) is not complete, the engine wraps bare agent functions with a thin adapter

## Non-Goals

- Async/background pipeline execution (Phase 3-4 agents remain outside the DAG engine)
- Real-time streaming or WebSocket support
- Authentication/authorization for the debug endpoint
- Persistent queue or message broker (in-process execution only)
