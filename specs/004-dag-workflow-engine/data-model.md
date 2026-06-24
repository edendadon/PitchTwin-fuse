# Data Model: DAG Workflow Engine

## Phase 1 Output

### Entities

#### WorkflowNode (in-memory definition, not persisted)

```python
@dataclass
class WorkflowNode:
    id: str                           # unique node identifier (e.g., "profile_agent", "phase1_parallel")
    type: str                         # "agent" | "parallel" | "sequential" | "human_gate"
    config: NodeConfig               # per-node execution settings
    inputs: list[str]                # list of upstream node IDs (empty list for root nodes)

@dataclass
class NodeConfig:
    max_retries: int = 2             # number of retries on failure
    timeout_sec: int = 60             # per-node timeout
    max_iterations: int = 5           # loop prevention threshold
```

#### WorkflowCheckpoint (SQLite — workflow_checkpoints table)

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| proposal_id | TEXT | PK (part) | Key for checkpoint lookup and resume |
| trace_id | TEXT | NOT NULL | UUID for this pipeline invocation |
| node_id | TEXT | PK (part) | ID of the last completed/failed node |
| phase | TEXT | NOT NULL | Human-readable phase name (e.g., "Phase 1: Profile Agent") |
| input_data | TEXT | NOT NULL | JSON serialized node input |
| output_data | TEXT | NOT NULL | JSON serialized node output |
| status | TEXT | NOT NULL | `completed` \| `failed` \| `in_progress` |
| created_at | TEXT | NOT NULL | ISO timestamp |

**Primary Key**: `(proposal_id, node_id)`

**Index**: `CREATE INDEX idx_checkpoint_proposal_status ON workflow_checkpoints(proposal_id, status)` — for efficient resume lookup

#### ExecutionTrace (SQLite — execution_traces table)

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| trace_id | TEXT | PK (part) | UUID for the entire workflow run |
| node_id | TEXT | PK (part) | Node that generated this event |
| event | TEXT | PK (part) | `started` \| `completed` \| `failed` \| `timed_out` \| `circuit_breaker` |
| timestamp | TEXT | PK (part) | ISO timestamp of event |
| duration_ms | INTEGER | NULL | Duration in milliseconds (for completed/failed) |
| error | TEXT | NULL | Error message if event is `failed`/`timed_out`/`circuit_breaker` |

**Primary Key**: `(trace_id, node_id, event, timestamp)`

**Index**: `CREATE INDEX idx_trace_trace_id ON execution_traces(trace_id)` — for efficient trace lookup by debug endpoint

### Validation Rules

- `node_id` must be non-empty string
- `type` must be one of: `agent`, `parallel`, `sequential`, `human_gate`
- `max_retries` >= 0
- `timeout_sec` > 0
- `max_iterations` > 0
- `status` must be one of: `completed`, `failed`, `in_progress`
- `event` must be one of: `started`, `completed`, `failed`, `timed_out`, `circuit_breaker`
- `duration_ms` must be >= 0 when present

### State Transitions

**Workflow Execution States** (proposal.status field):
- `pending` — pipeline not started
- `in_progress` — pipeline running
- `awaiting_approval` — paused at HumanGateNode
- `ready` — pipeline completed successfully
- `failed` — pipeline failed (circuit breaker, max_iterations, etc.)
- `timeout` — pipeline exceeded global timeout

**Node Execution States** (internal to engine):
- `pending` — node not yet executed
- `running` — node currently executing
- `completed` — node finished successfully
- `failed` — node failed after all retries
- `skipped` — node skipped due to upstream failure or circuit breaker

### Relationships

- `workflow_checkpoints.proposal_id` → `proposals.id` (foreign key, not enforced for SQLite)
- `workflow_checkpoints.trace_id` → `execution_traces.trace_id` (logical link)
- `execution_traces.trace_id` → `workflow_checkpoints.trace_id` (logical link)

### Persistence Strategy

- **Checkpoint write**: After each node completes (success or failure), write to `workflow_checkpoints`
- **Checkpoint lookup**: `SELECT * FROM workflow_checkpoints WHERE proposal_id=? AND status='in_progress' ORDER BY created_at DESC LIMIT 1`
- **Trace write**: Append-only events as nodes execute (no update, no delete)
- **Trace read**: `SELECT * FROM execution_traces WHERE trace_id=? ORDER BY timestamp`