# Change Specification: Streaming Twin + Human Gate

**Status**: Active

## Mission Brief

**Goal**: Add streaming support to Persona Agent (`run_persona_agent_stream()` yielding tokens via AsyncGenerator), update `twin_chat.html` to consume SSE/streaming, add a HumanGateNode to the orchestrator workflow (after combined agent, before `create_twin_session`), and add Flask routes for proposal approval flow.

**Success Criteria**:
1. `run_persona_agent_stream()` exists in `agents/persona_agent.py` and yields tokens as a generator
2. `twin_chat.html` consumes the streaming endpoint via SSE (`EventSource`) and renders tokens incrementally
3. `HumanGateNode` is integrated into the orchestrator after Phase 2 (combined agent) and before `create_twin_session`
4. `GET /proposal/<id>/approve` route creates a twin session upon consultant approval
5. `GET /proposal/<id>/status` route returns one of `READY`, `AWAITING_APPROVAL`, `GENERATING`
6. Existing tests pass; new functionality has corresponding test coverage

**Constraints**:
- P1 priority (hackathon issue #5)
- Must use existing `llm_client.py` wrapper (Gemini/Groq/LiteLLM)
- Flask-based — SSE via Flask streaming responses (no FastAPI/async framework switch)
- Python 3.11+, maintain existing agent pure-function convention
- Constitutional alignment: grounding constraint (Principle IV), observability (Principle III), validation (Principle II)

## Functional Requirements

### FR-1: Streaming Persona Agent
- A new function `run_persona_agent_stream(user_message, conversation_history, system_prompt, llm_client)` yields string tokens as they arrive from the LLM provider
- Uses a Python generator (not async — Flask is synchronous WSGI)
- Falls back gracefully to non-streaming if the provider does not support streaming
- Harness tracing emits latency and token metadata on completion

### FR-2: SSE Streaming Chat Endpoint
- New Flask route `POST /twin/<session_id>/message/stream` returns `text/event-stream` response
- Each SSE event contains a token chunk: `data: {"token": "..."}\n\n`
- Final event signals completion: `data: {"done": true}\n\n`
- Transcript is appended to DB after full response is assembled

### FR-3: Frontend SSE Consumption
- `twin_chat.html` uses `EventSource` or `fetch` with streaming reader to consume SSE
- Tokens are appended to the assistant message bubble in real time
- Typing indicator is replaced by the streaming bubble
- Graceful fallback to existing non-streaming POST if SSE fails

### FR-4: Human Gate Node
- Proposal status lifecycle: `generating` → `awaiting_approval` → `ready`
- After Phase 2 (combined agent) completes, proposal is saved with status `awaiting_approval` (not `ready`)
- Twin session is NOT auto-created; consultant must explicitly approve
- `HumanGateNode` is a conceptual gate in the orchestrator flow (not necessarily a class — can be status-based)

### FR-5: Approval & Status Routes
- `GET /proposal/<id>/approve`: Validates proposal exists and is in `awaiting_approval` status; creates twin session; sets proposal status to `ready`; redirects to proposal view
- `GET /proposal/<id>/status`: Returns JSON `{"status": "GENERATING"|"AWAITING_APPROVAL"|"READY"}`
- Proposal view page shows approval button when status is `awaiting_approval`

### FR-6: LLM Client Streaming Support
- `LLMClient` gains a `call_stream(system_prompt, user_message)` method returning a generator of string chunks
- Implements streaming for all three providers (Gemini, Groq, LiteLLM/OpenAI)
- Retries are not applied to streaming calls (stream-level retry is impractical)

## Delta Description

### MODIFIED
| File | Change |
|------|--------|
| `llm_client.py` | Add `call_stream()` method with per-provider streaming |
| `agents/persona_agent.py` | Add `run_persona_agent_stream()` generator function |
| `agents/harness.py` | Add `run_stream()` method for text-mode streaming with tracing |
| `orchestrator.py` | Change `run_proposal_pipeline` to set status `awaiting_approval`; remove auto `create_twin_session` call |
| `app.py` | Add `/proposal/<id>/approve`, `/proposal/<id>/status`, `/twin/<id>/message/stream` routes; remove auto-create twin session from `new_proposal` |
| `models.py` | Extend `Proposal.status` docstring to include `generating`, `awaiting_approval` |
| `templates/twin_chat.html` | Replace fetch-based messaging with SSE streaming reader |
| `templates/proposal.html` | Add approval button when status is `awaiting_approval` |
| `tests/test_agents.py` | Add tests for streaming, approval flow, and status endpoint |

### ADDED
| File | Change |
|------|--------|
| (none) | All changes are modifications to existing files |

### REMOVED
| File | Change |
|------|--------|
| (none) | No files removed |

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Flask WSGI cannot do true async streaming | Medium | Use `Response(generator, mimetype='text/event-stream')` with `stream_with_context` — works in Flask WSGI |
| LLM provider may not support streaming | Low | `call_stream()` falls back to yielding the full response as a single chunk |
| Gunicorn buffering may break SSE | Medium | Document `--worker-class=gthread` or disable proxy buffering |
| Breaking existing proposal flow | Medium | Status field change is backward-compatible (existing `ready` status still valid) |
| Constitution: grounding constraint during streaming | Low | System prompt is identical; streaming only changes delivery, not content |
