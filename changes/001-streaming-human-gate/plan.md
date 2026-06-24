# Implementation Plan: Streaming Twin + Human Gate

## Context

The current flow is fully synchronous: `new_proposal` runs the pipeline, auto-creates a twin session, and redirects to the proposal view. The twin chat uses `fetch` POST calls that wait for the full LLM response before rendering. This change introduces:

1. **Token-level streaming** from LLM → persona agent → Flask SSE → browser
2. **Human gate** requiring consultant approval before the twin session is created

Both changes touch the same pipeline but are independent concerns that can be developed and tested separately.

## Approach

### Layer 1: LLM Client Streaming (`llm_client.py`)

Add `call_stream(system_prompt, user_message) -> Generator[str, None, None]`:

- **LiteLLM/OpenAI**: Use `stream=True` on `chat.completions.create()`, iterate `response` chunks, yield `chunk.choices[0].delta.content`
- **Groq**: Same OpenAI-compatible streaming API
- **Gemini**: Use `generate_content(..., stream=True)`, iterate response chunks, yield `chunk.text`
- **Fallback**: If streaming raises, call `self.call()` and yield the full string as one chunk

No retries on streaming — retry logic remains on `call()` only.

### Layer 2: Agent Harness Streaming (`agents/harness.py`)

Add `run_stream(user_message) -> Generator[str, None, None]` to `AgentHarness`:

- Only supported for `mode="text"` (persona agent)
- Delegates to `self.llm.call_stream(self.system_prompt, user_message)`
- Emits trace on completion (wraps generator to capture timing)

### Layer 3: Persona Agent Streaming (`agents/persona_agent.py`)

Add `run_persona_agent_stream(user_message, conversation_history, system_prompt, llm_client) -> Generator[str, None, None]`:

- Same message construction as `run_persona_agent`
- Uses `AgentHarness(..., mode="text").run_stream(...)` instead of `.run()`
- Caller is responsible for assembling the full response from yielded chunks

### Layer 4: Orchestrator Human Gate (`orchestrator.py`)

Modify `run_proposal_pipeline`:

- Pipeline is launched in a background thread from the Flask route
- Proposal is created with `status="generating"` before the thread starts
- On pipeline completion, status transitions to `status="awaiting_approval"`
- Remove the `create_twin_session` call from the pipeline
- `create_twin_session` is now only called from the approval route

Add `handle_twin_message_stream(session_id, user_message) -> Generator[str, None, None]`:

- Same setup as `handle_twin_message` but calls `run_persona_agent_stream`
- Yields tokens to caller
- After generator is exhausted, appends full response to transcript
- On mid-stream client disconnect, partial response is discarded (not saved to transcript)

### Layer 5: Flask Routes (`app.py`)

**New routes:**

| Route | Method | Behavior |
|-------|--------|----------|
| `/proposal/<id>/status` | GET | Returns `{"status": "GENERATING\|AWAITING_APPROVAL\|READY"}` |
| `/proposal/<id>/approve` | POST | Validates `awaiting_approval`, creates session, sets `ready`, redirects. If already `ready`, flash "Already approved" and redirect. |
| `/twin/<id>/message/stream` | POST | SSE endpoint wrapping `handle_twin_message_stream` |

**Modified routes:**

- `new_proposal`: Remove auto `create_twin_session`; create proposal with `generating` status, launch pipeline in background thread, redirect to proposal view immediately
- `view_proposal`: Show approval button (form POST) when status is `awaiting_approval`; show spinner with 15s polling when `generating`

**SSE response pattern:**
```python
from flask import Response, stream_with_context

def generate():
    for token in handle_twin_message_stream(session_id, message):
        yield f"data: {json.dumps({'token': token})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"

return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

### Layer 6: Frontend SSE (`templates/twin_chat.html`)

Replace the `fetch` + JSON approach with streaming fetch:

```javascript
const response = await fetch(url, { method: 'POST', ... });
const reader = response.body.getReader();
const decoder = new TextDecoder();
// Parse SSE lines, extract tokens, append to message bubble
```

Using `fetch` with `ReadableStream` instead of `EventSource` because `EventSource` only supports GET requests.

Fallback: If `ReadableStream` is unavailable (old browsers), fall back to the existing non-streaming POST endpoint.

### Layer 7: Proposal Template (`templates/proposal.html`)

- When `proposal.status == 'awaiting_approval'`: show "Approve & Create Twin" as a form POST button to `/proposal/<id>/approve`
- When `proposal.status == 'ready'` and twin session exists: show existing twin link
- When `proposal.status == 'generating'`: show spinner/status indicator

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Python generator (not `async`) for streaming | Flask is WSGI; `async def` generators require an ASGI server. Generators with `stream_with_context` work natively. |
| `fetch` + `ReadableStream` over `EventSource` | `EventSource` only supports GET; our streaming endpoint needs POST with a JSON body. |
| Status-based human gate (not a class) | The existing codebase uses status strings. Adding a `HumanGateNode` class would be over-engineering for a status check. The gate is the `awaiting_approval` → `ready` transition triggered by the approval route. |
| No new DB columns | `proposals.status` already exists and supports arbitrary string values. Just expanding the status vocabulary. |
| Streaming fallback to non-streaming | Ensures the app works even if the LLM provider doesn't support streaming or the browser lacks `ReadableStream`. |

## Files Modified

| File | Lines Changed (est.) | Complexity |
|------|---------------------|------------|
| `llm_client.py` | +40 | Medium — three provider implementations |
| `agents/harness.py` | +25 | Low — wrapper generator |
| `agents/persona_agent.py` | +20 | Low — mirrors existing function |
| `orchestrator.py` | +35, ~5 modified | Medium — new streaming handler, status change |
| `app.py` | +50, ~10 modified | Medium — three new routes, one modified |
| `models.py` | +2 | Trivial — docstring update |
| `templates/twin_chat.html` | +40, ~20 modified | Medium — SSE reader logic |
| `templates/proposal.html` | +15 | Low — conditional button |
| `tests/test_agents.py` | +60 | Medium — mock streaming, approval tests |

## Rollback

All changes are backward-compatible. If streaming causes issues:
- The non-streaming `run_persona_agent` and `/twin/<id>/message` route remain functional
- Setting proposal status back to `ready` in `run_proposal_pipeline` restores the old auto-create flow
