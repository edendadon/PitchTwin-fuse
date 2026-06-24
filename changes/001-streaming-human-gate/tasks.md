# Tasks: Streaming Twin + Human Gate

## Tasks

- [ ] 1. Add `call_stream()` method to `LLMClient` in `llm_client.py` — implement streaming for LiteLLM/OpenAI (`stream=True`), Groq (same API), and Gemini (`stream=True`); include fallback that yields full response as single chunk if streaming fails
- [ ] 2. Add `run_stream()` method to `AgentHarness` in `agents/harness.py` — text-mode only generator that delegates to `llm.call_stream()` and emits trace on completion
- [ ] 3. Add `run_persona_agent_stream()` to `agents/persona_agent.py` — generator function mirroring `run_persona_agent` but using `harness.run_stream()`
- [ ] 4. Update `Proposal.status` docstring in `models.py` to document `generating | awaiting_approval | ready` lifecycle
- [ ] 5. Modify `run_proposal_pipeline()` in `orchestrator.py` — set proposal status to `awaiting_approval` instead of `ready`; remove auto `create_twin_session()` call
- [ ] 6. Add `handle_twin_message_stream()` to `orchestrator.py` — generator that yields tokens and appends full response to transcript after exhaustion
- [ ] 7. Add `GET /proposal/<id>/status` route in `app.py` — returns `{"status": "GENERATING|AWAITING_APPROVAL|READY"}`
- [ ] 8. Add `GET /proposal/<id>/approve` route in `app.py` — validates `awaiting_approval`, creates twin session, sets status `ready`, redirects to proposal view
- [ ] 9. Add `POST /twin/<id>/message/stream` SSE route in `app.py` — streams tokens via `text/event-stream` using `Response(stream_with_context(generator))`
- [ ] 10. Remove auto `create_twin_session` from `new_proposal` route in `app.py`; update redirect and error handling
- [ ] 11. Update `templates/proposal.html` — show "Approve & Create Twin" button when `status == 'awaiting_approval'`; show status indicator when `generating`
- [ ] 12. Update `templates/twin_chat.html` — replace `fetch`+JSON with streaming `fetch` + `ReadableStream` SSE reader; keep non-streaming fallback
- [ ] 13. Add tests for `call_stream()`, `run_persona_agent_stream()`, approval route, status route, and SSE endpoint in `tests/test_agents.py`
- [ ] 14. Run full test suite (`uv run python -m pytest tests/test_agents.py`) and verify all tests pass
