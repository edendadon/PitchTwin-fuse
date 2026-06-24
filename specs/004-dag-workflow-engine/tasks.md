# Tasks: DAG Workflow Engine

**Input**: Design documents from `/specs/004-dag-workflow-engine/`
**Prerequisites**: plan.md, spec.md (required for user stories), research.md, data-model.md, contracts/
**Tests**: Test tasks are INCLUDED (per Constitution Principle V: test-first for agents/engine)

**Note**: Tests should be written FIRST and fail before implementation (TDD approach for critical engine logic).

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create orchestrator module structure and extend SQLite schema

- [x] T001 [ASYNC] Create orchestrator/ directory structure with __init__.py
- [x] T002 [ASYNC] Extend db.py with workflow_checkpoints and execution_traces table schemas
- [x] T003 [P] [ASYNC] Add indexes for efficient checkpoint lookup (proposal_id, status) and trace lookup (trace_id)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and error types that all user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [SYNC] Define NodeConfig and WorkflowNode dataclasses in orchestrator/workflow.py
- [x] T005 [ASYNC] Define error types: WorkflowError, WorkflowTimeout, CircuitBreakerOpen, MaxIterationsExceeded, DAGValidationError in orchestrator/workflow.py
- [x] T006 [SYNC] Implement MemoryStore class in orchestrator/memory.py with save_checkpoint, get_latest_in_progress, save_trace, get_trace methods
- [x] T007 [ASYNC] Implement AgentAdapter class in orchestrator/adapter.py that wraps bare functions (probes for Issue #1 Agent.execute() availability)

**Checkpoint**: Foundational ready — user story implementation can now begin

---

## Phase 3: Core Engine (SYNC — Human Review Required)

**Purpose**: The WorkflowEngine core loop with all determinism guarantees

- [x] T008 [SYNC] Implement WorkflowEngine.__init__ with DAG storage, global timeout, circuit breaker threshold
- [x] T009 [SYNC] Implement DAG validation: Kahn's algorithm topological sort; raise DAGValidationError on cycle detection in orchestrator/workflow.py
- [x] T010 [SYNC] Implement WorkflowEngine.execute() core loop: topological sort, checkpoint resume scan, node execution with global timeout enforcement in orchestrator/workflow.py
- [x] T011 [SYNC] Implement circuit breaker: increment on failure, reset on success, raise CircuitBreakerOpen after threshold in orchestrator/workflow.py

---

## Phase 4: Node Types (ASYNC — Well-Specified Interfaces)

**Purpose**: Implement each node type with bounded retries, per-node timeout, loop detection

- [x] T012 [ASYNC] Implement AgentNode: call agent_fn with retries, timeout via Thread.join, hash-based loop detection (5-hash ring buffer) in orchestrator/workflow.py
- [x] T013 [ASYNC] Implement ParallelNode: thread-per-child with per-child timeout, wait-all, failure aggregation in orchestrator/workflow.py
- [x] T014 [ASYNC] Implement SequentialNode: ordered child execution, fail-fast on child failure in orchestrator/workflow.py
- [x] T015 [ASYNC] Implement HumanGateNode: set proposal status to "awaiting_approval", poll db for approval signal, resume on approval in orchestrator/workflow.py

---

## Phase 5: User Story 1 - Happy Path Pipeline (P0) 🎯 MVP

**Goal**: End-to-end pipeline completes with all phases, proposal status=ready, full trace visible

**Independent Test**: POST /proposal/new with valid profile/brief → status=ready, GET /debug/trace/<id> shows all nodes completed

- [x] T016 [P] [ASYNC] [US1] Write unit tests for WorkflowEngine.execute() happy path in tests/test_workflow_engine.py (tests should FAIL before T017-T018)
- [x] T017 [ASYNC] [US1] Implement run_proposal_pipeline() in orchestrator.py using WorkflowEngine with full DAG for Phases 1-2
- [x] T018 [P] [ASYNC] [US1] Write unit tests for MemoryStore checkpoint I/O in tests/test_workflow_engine.py (tests should FAIL before T006)
- [x] T019 [ASYNC] [US1] Wire run_proposal_pipeline() into Flask /proposal/new route in app.py (existing route, just call new function)

**Checkpoint**: User Story 1 complete — full pipeline works end-to-end

---

## Phase 6: User Story 2 - Resume After Crash (P0)

**Goal**: Pipeline resumes from last checkpoint after process kill mid-execution

**Independent Test**: Kill process during Phase 1 → re-trigger → Phase 1 skipped, Phase 2 runs, proposal complete

- [x] T020 [P] [ASYNC] [US2] Write unit tests for checkpoint resume logic in tests/test_workflow_engine.py (tests should FAIL before T021)
- [x] T021 [ASYNC] [US2] Implement checkpoint resume: get_latest_in_progress(), skip completed nodes, execute from first pending node in orchestrator/workflow.py
- [x] T022 [ASYNC] [US2] Verify checkpoint write after each node completes in orchestrator/memory.py

**Checkpoint**: User Story 2 complete — crash recovery works

---

## Phase 7: User Story 3 - Loop Prevention (P0)

**Goal**: Infinite loop in agent detected and pipeline halts cleanly

**Independent Test**: Mock agent returning same output 5 times → pipeline halts with "max_iterations exceeded" error

- [x] T023 [P] [ASYNC] [US3] Write unit tests for loop detection (5 identical outputs → breach) in tests/test_workflow_engine.py (tests should FAIL before T024)
- [x] T024 [ASYNC] [US3] Implement hash-based loop detection in AgentNode: SHA-256 output, ring buffer, trigger MaxIterationsExceeded in orchestrator/workflow.py

**Checkpoint**: User Story 3 complete — loop prevention active

---

## Phase 8: User Story 4 - Circuit Breaker (P0)

**Goal**: 3 consecutive failures trip circuit breaker and halt pipeline

**Independent Test**: Mock 3 failing agents → 4th not called, error "circuit breaker: 3 consecutive failures"

- [x] T025 [P] [ASYNC] [US4] Write unit tests for circuit breaker (3 failures → halt) in tests/test_workflow_engine.py (tests should FAIL before T026)
- [x] T026 [ASYNC] [US4] Implement circuit breaker counter: increment on node failure, halt if threshold reached in orchestrator/workflow.py

**Checkpoint**: User Story 4 complete — circuit breaker active

---

## Phase 9: User Story 5 - Global Timeout (P0)

**Goal**: Pipeline aborts after 240s global timeout

**Independent Test**: Mock 300s agent → pipeline status=timeout after 240s

- [x] T027 [P] [ASYNC] [US5] Write unit tests for global timeout (240s wall-clock limit) in tests/test_workflow_engine.py (tests should FAIL before T028)
- [x] T028 [ASYNC] [US5] Implement global workflow timeout: wall-clock start time, abort all nodes when exceeded, set status=timeout in orchestrator/workflow.py

**Checkpoint**: User Story 5 complete — timeout enforcement active

---

## Phase 10: User Story 6 - Debug Trace Endpoint (P0)

**Goal**: GET /debug/trace/<trace_id> returns JSON execution graph

**Independent Test**: curl /debug/trace/<trace_id> → JSON with nodes, events, duration_ms, errors

- [x] T029 [P] [ASYNC] [US6] Write integration tests for debug trace endpoint in tests/test_workflow_engine.py (tests should FAIL before T030)
- [x] T030 [ASYNC] [US6] Implement Flask route GET /debug/trace/<trace_id> in app.py querying execution_traces table
- [x] T031 [ASYNC] [US6] Ensure trace events emitted after every node start/complete/fail in orchestrator/memory.py and workflow.py

**Checkpoint**: User Story 6 complete — observability endpoint functional

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Integration verification, validation against quickstart scenarios

- [x] T032 [ASYNC] Run Scenario 1 (Happy Path): POST /proposal/new → verify trace at /debug/trace/<id>
- [x] T033 [ASYNC] Run Scenario 2 (Resume): Kill mid-pipeline → re-trigger → verify Phase 1 skipped
- [x] T034 [ASYNC] Run Scenario 3 (Loop): Mock repeated output → verify "max_iterations exceeded" error
- [x] T035 [ASYNC] Run Scenario 4 (Circuit Breaker): Mock 3 failures → verify "circuit breaker" error
- [x] T036 [ASYNC] Run Scenario 5 (Timeout): Mock 300s sleep → verify status=timeout at 240s
- [x] T037 [ASYNC] Update AGENTS.md to document new orchestrator/workflow.py and orchestrator/memory.py modules (SPECKIT section already updated)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **Core Engine (Phase 3)**: Depends on Foundational — BLOCKS node types and all user stories
- **Node Types (Phase 4)**: Depends on Core Engine — needed for user stories
- **User Stories (Phase 5-10)**: All depend on Node Types
  - US1 (Happy Path) — run first, validates full integration
  - US2 (Resume) — depends on US1 complete (same engine)
  - US3 (Loop) — depends on US1 complete
  - US4 (Circuit Breaker) — depends on US1 complete
  - US5 (Timeout) — depends on US1 complete
  - US6 (Debug Endpoint) — depends on US1 complete
- **Polish (Phase 11)**: Depends on all user stories complete

### Within Each User Story

1. Write failing unit tests FIRST (TDD)
2. Implement feature
3. Verify tests pass
4. Verify independent test criteria

### Parallel Execution Opportunities

- Phase 1 tasks (T001-T003) can all run in parallel
- Foundational tasks T005, T007 can run parallel to T004 (different files)
- Node Type tasks (T012-T015) can run in parallel (different classes)
- Test tasks within a user story (T016, T018) can run in parallel (different test files)

### Recommended Implementation Order

```
Sequential: T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008-T011 → T012-T015
            (setup)   (foundational)                (core engine)  (node types)

Then parallel for US1-US6:
  T016, T018 (write failing tests)
  ↓
  T017 (implement happy path — core integration)
  ↓
  T019 (Flask wire)

  T020-T021 (resume)
  T023-T024 (loop)
  T025-T026 (circuit breaker)
  T027-T028 (timeout)
  T029-T031 (debug endpoint)

All can run in parallel after T019 complete.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: Core Engine (SYNC — human review required)
4. Complete Phase 4: Node Types
5. Complete Phase 5: User Story 1
6. **STOP and VALIDATE**: Full pipeline runs end-to-end
7. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational + Core + Node Types → Complete engine foundation
2. Add US1 (Happy Path) → Full pipeline functional → MVP!
3. Add US2 (Resume) → Crash recovery → Production resilience
4. Add US3-US5 → All failure modes handled
5. Add US6 (Debug Endpoint) → Full observability

---

## Format Reminder

- `[P]` = Can run in parallel (different files, no dependencies)
- `[SYNC]` = Requires human review (complex logic, security-critical, ambiguous requirements)
- `[ASYNC]` = Can be delegated to async agents (well-defined, clear specs)
- `[US1]-[US6]` = Maps task to user story for traceability
- All tasks include exact file paths
- Tests written FIRST and fail before implementation (TDD for engine)