# Quickstart: DAG Workflow Engine

## Phase 1 Output

### Validation Scenarios

These scenarios prove the feature works end-to-end. Run after implementation.

---

**Scenario 1: Happy Path**

Prerequisites: Demo profile seeded (`POST /demo/seed`), valid client brief

```bash
# Trigger pipeline
curl -X POST http://localhost:5000/proposal/new \
  -d "consultant_id=<profile_id>&company_name=Acme&client_brief=..."

# Wait ~60-90s for completion
# Check proposal status
curl http://localhost:5000/proposal/<proposal_id>

# Verify trace exists and shows all nodes green
curl http://localhost:5000/debug/trace/<trace_id>
```

Expected: `status=ready` in proposal, trace shows all nodes with `completed` event.

---

**Scenario 2: Resume After Crash (Checkpoint)**

Prerequisites: Pipeline started and completed Phase 1

```bash
# Kill and restart app mid-pipeline
# Re-trigger same proposal
curl -X POST http://localhost:5000/proposal/new \
  -d "consultant_id=<profile_id>&company_name=Acme&client_brief=..."

# Verify Phase 1 nodes not re-executed (check trace for duplicate node_ids)
curl http://localhost:5000/debug/trace/<trace_id>
```

Expected: Only Phase 2 nodes in trace; Phase 1 skipped via checkpoint resume.

---

**Scenario 3: Loop Prevention (max_iterations)**

Prerequisites: Mock agent returns identical output 5 times

```bash
# Configure mock agent with repeated output
# Run pipeline
curl -X POST http://localhost:5000/proposal/new \
  -d "consultant_id=<profile_id>&company_name=Acme&client_brief=..."
```

Expected: Pipeline halts with error containing "max_iterations exceeded".

---

**Scenario 4: Circuit Breaker**

Prerequisites: Mock 3 consecutive failing agents

```bash
# Run pipeline with failing mock agents
curl -X POST http://localhost:5000/proposal/new \
  -d "consultant_id=<profile_id>&company_name=Acme&client_brief=..."
```

Expected: After 3rd failure, pipeline halts with error containing "circuit breaker".

---

**Scenario 5: Global Timeout (240s)**

Prerequisites: Mock agent with 300s sleep

```bash
# Run pipeline
curl -X POST http://localhost:5000/proposal/new \
  -d "consultant_id=<profile_id>&company_name=Acme&client_brief=..."
```

Expected: Pipeline aborts with `status=timeout` after 240s.

---

### Debug Endpoint

```bash
curl http://localhost:5000/debug/trace/<trace_id>
```

Response:
```json
{
  "trace_id": "uuid",
  "proposal_id": "uuid",
  "status": "completed",
  "duration_ms_total": 45230,
  "nodes": [
    {"node_id": "profile_agent", "event": "completed", "duration_ms": 3200, "error": null},
    {"node_id": "client_research", "event": "completed", "duration_ms": 4100, "error": null}
  ]
}
```

---

### Running Tests

```bash
# Unit tests for WorkflowEngine
pytest tests/test_workflow_engine.py -v

# Integration test (full pipeline if API keys set)
python -m pytest tests/test_agents.py -v -k "not mock"  # skip mock-only tests
```

---

### Prerequisites

1. `.env` with `GEMINI_API_KEY` or `LITELLM_API_KEY` set
2. SQLite database initialized: `python app.py` (runs `db.init_db()`)
3. Demo data seeded: `curl -X POST http://localhost:5000/demo/seed`