# Research: DAG Workflow Engine

## Phase 0 Output

### Research Questions & Findings

**R-1: DAG definition format**
- Decision: Dict-based nodes with an explicit `edges` list
- Each node: `{"id": str, "type": "agent"|"parallel"|"sequential"|"human_gate", "config": {...}, "inputs": [upstream_ids]}`
- Edges: `[(parent_id, child_id), ...]` or embedded in node `inputs`
- Rationale: Serializable, no new class hierarchy for definition, caller can construct programmatically
- Alternative rejected: YAML config file — too rigid for dynamic DAG construction

**R-2: Loop-detection algorithm**
- Decision: Hash-based comparison with ring buffer
- Maintain last 5 output hashes per node execution attempt
- If all 5 hashes identical → 5 identical outputs in a row → max_iterations breach
- Rationale: O(1) hash computation, deterministic, low memory (5 hashes × 32 bytes)
- Alternative rejected: Semantic comparison (parse JSON and compare keys) — too expensive; Full equality — fragile with dict ordering

**R-3: Adapter pattern for bare functions**
- Decision: Minimal callable wrapper
- Interface: `(input_data: dict) -> dict`
- Adapter wraps any callable and exposes `.execute(input_data)`
- If Issue #1 `Agent` class present: use `Agent.execute()` as the adapter target
- Rationale: Decouples engine from Issue #1; allows bare functions to work without full harness

**R-4: ParallelNode timeout semantics**
- Decision: Per-child timeout
- Each child runs in its own thread with `thread.join(timeout_sec)`
- If child exceeds its timeout → that child is aborted (cancelled via Thread.join timeout)
- ParallelNode waits for all children or total timeout
- Rationale: Failure isolation — one slow child doesn't fail the whole group
- Alternative rejected: Total timeout (all children must finish within 60s) — too strict for variable LLM response times

**R-5: DAG cycle validation algorithm**
- Decision: Kahn's algorithm (topological sort)
- Attempt to produce topological ordering of all nodes
- If Kahn's fails (remaining nodes with no in-degree = 0) → cycle detected
- Report first node found in cycle
- Rationale: O(V+E), same complexity as DFS, also produces execution order
- Alternative rejected: DFS recursion — Python recursion limit risk on large DAGs

## Additional Findings

### SQLite Concurrency
- Use `WAL` mode for workflow_checkpoints to allow concurrent reads during execution
- Writes are serialized via single-writer pattern (synchronous Flask request = single writer)
- Checkpoint lookup: `SELECT ... WHERE proposal_id=? AND status='in_progress' ORDER BY created_at DESC LIMIT 1`

### Threading Model
- Use `threading.Thread` with `join(timeout)` for per-node timeout (existing pattern)
- Circuit breaker: Simple counter, incremented on each node failure, reset on success
- No asyncio needed for initial implementation (synchronous Flask request model)

### Integration with existing db.py
- Add new table schemas to `db.py` init script
- Use existing `get_connection()` pattern for new tables
- Checkpoint and trace writes use same transaction pattern as proposals/sessions

### Flask Debug Endpoint
- `GET /debug/trace/<trace_id>` → query `execution_traces` table
- Return JSON: `{"trace_id": ..., "events": [...], "duration_ms_total": ...}`
- No authentication (explicitly out of scope per spec)