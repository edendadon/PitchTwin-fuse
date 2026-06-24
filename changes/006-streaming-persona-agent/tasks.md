# Tasks: Streaming Persona Agent + Human Approval Gate

## Tasks

- [x] 1. `LLMClient.call_stream()` — already done in `llm_client.py`
- [x] 2. `AgentHarness.run_stream()` — already done in `agents/harness.py`
- [x] 3. Add `run_persona_agent_stream()` to `agents/persona_agent.py` — generator that builds conversation context and yields from `harness.run_stream()`
- [x] 4. Update `Proposal.status` field comment in `models.py` — `generating | awaiting_approval | ready`
- [x] 5. Modify `run_proposal_pipeline()` in `orchestrator/__init__.py` — set `status="awaiting_approval"` on completion, remove `create_twin_session` call
- [x] 6. Add `handle_twin_message_stream()` to `orchestrator/__init__.py` — generator that yields tokens and appends full response to transcript after exhaustion
- [x] 7. Add `GET /proposal/<id>/status` route in `app.py` — returns `{"status": "GENERATING|AWAITING_APPROVAL|READY"}`
- [x] 8. Add `POST /proposal/<id>/approve` route in `app.py` — validates `awaiting_approval`, creates twin session, sets status `ready`, redirects; flash "Already approved" if already `ready`
- [x] 9. Add `POST /twin/<id>/message/stream` SSE route in `app.py` — streams tokens via `text/event-stream` using `Response(stream_with_context(...))`
- [x] 10. Modify `new_proposal` route in `app.py` — create proposal with `generating` status, launch pipeline in background thread, redirect immediately; remove auto `create_twin_session`
- [x] 11. Update `templates/proposal.html` — spinner + 15s status poll when `generating`; Approve button (POST form) when `awaiting_approval`; client link when `ready`
- [x] 12. Update `templates/twin_chat.html` — replace JSON fetch with SSE streaming `fetch` + `ReadableStream`; keep non-streaming fallback on error
- [x] 13. Add tests to `tests/test_agents.py` — cover `run_persona_agent_stream()`, `/proposal/<id>/status`, `/proposal/<id>/approve`
- [x] 14. Run full test suite (`uv run python -m pytest tests/`) — 52 passed
