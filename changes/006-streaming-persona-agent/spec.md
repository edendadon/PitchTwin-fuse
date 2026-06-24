# Change Specification: Streaming Persona Agent + Human Approval Gate

**Status**: Active

## Mission Brief

**Goal**: Add streaming token delivery to twin chat and enforce explicit consultant approval before the client receives a session link. Builds on the existing `001-streaming-human-gate` spec; tasks 1 and 2 (LLMClient.call_stream + AgentHarness.run_stream) are already implemented.

**Success Criteria**:
1. `run_persona_agent_stream()` exists in `agents/persona_agent.py` and yields string tokens
2. `POST /twin/<id>/message/stream` returns `text/event-stream` SSE; tokens render incrementally in `twin_chat.html`
3. `new_proposal` creates proposal with status `generating`, launches pipeline in background thread, redirects immediately
4. Pipeline completion sets proposal status to `awaiting_approval`; no auto-create twin session
5. `GET /proposal/<id>/status` returns `{"status": "GENERATING"|"AWAITING_APPROVAL"|"READY"}`
6. `POST /proposal/<id>/approve` creates twin session and sets status `ready`; flash "Already approved" on duplicate
7. `templates/proposal.html` shows spinner + 15s status poll when `generating`; shows Approve button when `awaiting_approval`
8. All existing tests pass; new streaming/approval tests added

**Constraints**:
- Flask WSGI only — use `Response(stream_with_context(...), mimetype='text/event-stream')`
- No FastAPI/async switch
- Must preserve existing `handle_twin_message` for the non-streaming fallback
- Constitutional alignment: Principle IV (grounding unchanged), Principle III (trace on stream completion)

## Delta Description

### MODIFIED
| File | Change |
|------|--------|
| `agents/persona_agent.py` | Add `run_persona_agent_stream()` generator |
| `models.py` | Extend `Proposal.status` to `generating \| awaiting_approval \| ready` |
| `orchestrator/__init__.py` | Set status `awaiting_approval` on completion; add `handle_twin_message_stream()`; remove auto create_twin_session |
| `app.py` | Background thread for new_proposal; add status, approve, stream-message routes |
| `templates/proposal.html` | Spinner + status polling; Approve button |
| `templates/twin_chat.html` | Replace fetch with SSE streaming reader; keep fallback |
| `tests/test_agents.py` | Tests for streaming, approval, status endpoint |

### ALREADY DONE
| File | What's done |
|------|------------|
| `llm_client.py` | `call_stream()` with Gemini/Groq/LiteLLM + fallback |
| `agents/harness.py` | `run_stream()` generator with trace on completion |

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Flask WSGI buffering breaks SSE | Medium | `stream_with_context`; document gthread worker for gunicorn |
| Background thread exceptions go unnoticed | Low | Catch and set proposal status to `error` |
| Duplicate approval creates duplicate session | Low | Check status == `awaiting_approval` before creating session |
| Partial stream saved to transcript on disconnect | Low | Assemble full response in generator; append only after exhaustion |
