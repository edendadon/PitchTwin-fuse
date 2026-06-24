# Contract: Checkpoint & Trace Schemas

## Phase 1 Output

### SQLite Tables

#### workflow_checkpoints

```sql
CREATE TABLE workflow_checkpoints (
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

CREATE INDEX idx_checkpoint_proposal_status ON workflow_checkpoints (proposal_id, status);
```

#### execution_traces

```sql
CREATE TABLE execution_traces (
    trace_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    event TEXT NOT NULL CHECK (event IN ('started', 'completed', 'failed', 'timed_out', 'circuit_breaker')),
    timestamp TEXT NOT NULL,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error TEXT,
    PRIMARY KEY (trace_id, node_id, event, timestamp)
);

CREATE INDEX idx_trace_trace_id ON execution_traces (trace_id);
```

### JSON Serialization

**WorkflowCheckpoint → JSON (for input_data/output_data columns)**

```json
{
  "type": "object",
  "properties": {
    "input_data": { "type": "object" },
    "output_data": { "type": "object" }
  },
  "example": {
    "input_data": {
      "consultant_id": "uuid",
      "raw_profile": "string"
    },
    "output_data": {
      "structured_profile": { ... }
    }
  }
}
```

**ExecutionTrace → JSON (for Flask debug endpoint)**

```json
{
  "type": "object",
  "properties": {
    "trace_id": { "type": "string", "format": "uuid" },
    "node_id": { "type": "string" },
    "event": {
      "type": "string",
      "enum": ["started", "completed", "failed", "timed_out", "circuit_breaker"]
    },
    "timestamp": { "type": "string", "format": "date-time" },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "error": { "type": ["string", "null"] }
  }
}
```

### Debug Endpoint Response Schema

**GET /debug/trace/<trace_id>**

```json
{
  "trace_id": "string (UUID)",
  "proposal_id": "string (UUID)",
  "status": "completed | failed | timeout | circuit_broken",
  "duration_ms_total": "integer",
  "nodes": [
    {
      "node_id": "string",
      "event": "string",
      "timestamp": "string (ISO)",
      "duration_ms": "integer | null",
      "error": "string | null"
    }
  ]
}
```

**Error Responses**

| Status | Body | When |
|--------|------|------|
| 404 | `{"error": "trace_id not found"}` | No trace with this ID |
| 500 | `{"error": "database error"}` | SQLite failure |