# spec.harness-brainstorm — Agent Harness: Guardrails, Validation & Tracing

## Current State (from code review)

| Aspect | `matching_agent.py` | `writer_agent.py` | Every other agent |
|--------|---------------------|-------------------|-------------------|
| LLM call pattern | `pydantic_ai.Agent` + `run_sync()` | same | `llm_client.call_json()` |
| Output validation | Pydantic `MatchingOutput` model | Pydantic `WriterOutput` model | `json.loads()` raw dict — no schema |
| Input validation | None (raw dicts in, trust the caller) | same | same |
| Tracing | None | None | None |
| Error handling | None (raises on LLM failure) | same | `call_json` has HTTP retries only |
| Hallucination guard | System prompt only | System prompt only | System prompt only |
| **Used by orchestrator?** | ❌ (orchestrator uses `combined_agent`) | ❌ | varies |

The root inconsistency: matching + writer use pydantic_ai (a second LLM calling path) while every other agent uses `llm_client.call_json()`.
The orchestrator bypasses them entirely via `combined_agent.py`.

---

## Brainstorm: Design Options

### Option A — Thin Harness Base Class

A shared `AgentHarness` that wraps `llm_client.call_json()` with validation, tracing, and retry.

```python
class AgentHarness:
    def __init__(self, llm_client, system_prompt: str, output_schema: type[BaseModel] | None = None):
        ...

    def run(self, **inputs) -> dict:
        # 1. Validate inputs against schema (if provided)
        # 2. Start OTel span with agent name, input summary
        # 3. Call LLM with retries + exponential backoff
        # 4. Parse JSON
        # 5. Validate output against schema
        # 6. On validation failure -> retry LLM with error feedback
        # 7. Log metrics (latency, tokens if available, retry count)
        # 8. Return validated dict
```

**Pros:** Unifies all 7 agents under one calling convention. Drops the dead pydantic_ai dependency. Easy to add cross-cutting features.

**Cons:** Migrates matching/writer away from pydantic_ai (breaking change to tests).

---

### Option B — Pydantic AI for Everything

Standardize all agents on pydantic_ai's `Agent` class with structured output models.

**Pros:** Built-in schema validation. Native structured output. The matching/writer agents are already canonical.

**Cons:** pydantic_ai's `create_model()` is hardcoded to LiteLLM — can't use the `llm_client.LLMClient()` abstraction (which supports Gemini/Groq/LiteLLM). Two LLM client paths in the codebase. pydantic_ai doesn't natively support Logfire/OTel instrumentation of agent calls (the spans come from the underlying OpenAI SDK, not from pydantic_ai).

---

### Option C — Decorator-Based Harness

```python
@agent(
    name="matching",
    system_prompt=SYSTEM_PROMPT,
    output_schema=MatchingOutput,
    retries=3,
    temperature=0.2,
)
def run_matching_agent(structured_profile, client_context):
    return {"consultant_profile": structured_profile, "client_context": client_context}
```

**Pros:** Declarative, minimal boilerplate. Easy to test (decorator is mockable).

**Cons:** Harder to compose. Decorator args can't be dynamic. Less Pythonic for this use case.

---

## Guardrails (cross-cutting, regardless of Option)

### 1. Input Guardrails (pre-call)

- **Schema validation**: Each agent declares a Pydantic model for expected inputs. Harness validates before calling LLM.
- **Size limits**: Reject inputs exceeding token limits (e.g., profile > 100k chars -> truncation warning).
- **PII scan** (future): Strip emails, phone numbers from logged payloads.

### 2. Output Guardrails (post-call)

- **Schema validation**: Output must match declared schema. Retry LLM with "Your response was invalid: {error}" up to N times.
- **Grounding constraint** (Persona Agent only): After LLM response, extract named entities and cross-reference against profile. If entities are not in profile, emit warning / filter / regenerate.
- **Tone check**: Verify output tone matches requested tone_markers (simple keyword-based or LLM-as-judge).
- **No-empty check**: Reject empty strings or lists where schema requires content.

### 3. Safety Guardrails

- **Timeout per agent**: Configurable per agent (profile_agent might need 60s, persona_agent 30s).
- **Circuit breaker**: If an agent fails 5 times in a row (across pipeline runs), skip it or fall back to a cached result.
- **Content filter**: Block toxic / adversarial inputs before they reach the LLM (basic regex for prompt injection patterns).

---

## Validation Layer

### Input Validation

```python
class MatchingInputs(BaseModel):
    structured_profile: ProfileData  # nested model
    client_context: ClientContext    # nested model

class WriterInputs(BaseModel):
    relevance_map: RelevanceMap
    structured_profile: ProfileData
    client_context: ClientContext
```

Harness runs `MatchingInputs(**kwargs)` before the LLM call — catches type errors early with clear error messages.

### Output Validation

Already half-done for matching/writer (pydantic_ai). For the other agents:

```python
class ProfileOutput(BaseModel):
    name: str
    title: str
    skills: list[str]
    experience: list[ExperienceItem]
    ...
```

### Retry on Validation Failure

```python
for attempt in range(max_retries):
    raw = llm_client.call(system_prompt, user_message)
    try:
        parsed = output_schema.model_validate_json(raw)
        return parsed.model_dump()
    except ValidationError as e:
        user_message += f"\n\nPrevious response was invalid: {e}\nPlease respond with valid JSON matching this schema: {output_schema.model_json_schema()}"
```

---

## Tracing & Observability

### Current (orchestrator level only):
```python
with logfire.span("agent: profile"):
    result = run_profile_agent(...)
```

### Proposed (agent harness level):
```python
with logfire.span(
    "agent.run",
    agent_name=self.name,
    input_tokens=estimate_tokens(inputs),
    agent_version=1,
) as span:
    span.set_attribute("input", summarize(inputs, max_len=500))  # logfire captures this
    result = self._call_llm(inputs)
    span.set_attribute("output_valid", True)
    span.set_attribute("retry_count", retries)
    span.set_attribute("latency_ms", elapsed_ms)
    # logfire automatically captures exceptions as span errors
```

### Metrics to capture per agent call:
- Agent name
- Success/failure
- Latency (ms)
- Retry count
- Input token estimate (character count / 4)
- Output token estimate
- Validation errors (if any)
- Pipeline run ID (propagated from orchestrator)

### Logfire Integration

logfire is already a dependency (`pyproject.toml` line 17) and used in `orchestrator.py`. The harness should:
1. Create child spans nested under the orchestrator's pipeline span
2. Use `logfire.instrument_openai()` / `logfire.instrument_google_genai()` (already done in `llm_client._init_client`)
3. Add structured attributes (agent name, inputs summary, validation status)

The OTel context propagation workaround in `orchestrator.py:58-68` (capturing `parent_ctx` and re-attaching in threads) should be moved into the harness so every agent call automatically inherits the parent span.

---

## Specific Recommendations for matching_agent.py + writer_agent.py

### Problem: These agents are dead code

The orchestrator calls `combined_agent.py` which does matching + writer + gap in one call. The standalone matching/writer agents are only exercised by unit tests.

**Decision needed**: Either:
- (a) Delete standalone matching/writer agents, keep only `combined_agent.py`
- (b) Rewire orchestrator to call them individually (reverting the combined agent optimization)
- (c) Keep both, but refactor them to use the shared harness

### If we keep them (for modularity / testability):

1. **Convert matching/writer from `pydantic_ai.Agent` to shared harness.** Drop the `_get_agent()` singleton, `create_model()`, and `pydantic_ai.Agent.run_sync()` pattern. Unify on `llm_client.call_json()`.

2. **Add input validation models** (`MatchingInputs`, `WriterInputs`).

3. **Wrap in harness**: Call harness.run() which handles tracing, validation, retries.

4. **Remove `_agent` module-level singleton** — it's a testing headache (needs `patch.object` in every test).

### Proposed file structure:

```
agents/
  harness.py          # AgentHarness class, shared decorators/utilities
  schemas.py          # All input/output Pydantic models (or keep inline)
  matching_agent.py   # Now uses harness: run_matching_agent = Harness(...).run
  writer_agent.py     # Same
```

Or keep schemas inline (current pattern is fine — each agent has its own output model).

---

## Migration Path

### Phase 1: Build `harness.py`
- `AgentHarness` class with run(), validate_inputs(), validate_output(), trace()
- Supports both `llm_client.call()` (for persona) and `call_json()` (for all others)
- OTel span creation with context propagation
- Retry-on-validation-failure logic

### Phase 2: Port matching_agent.py + writer_agent.py
- Remove pydantic_ai dependency (keep pydantic for schemas)
- Replace `_get_agent()` + `run_sync()` with `harness.run()`
- Update tests: remove `patch.object(matching_module, "_agent", ...)` pattern, use `MockLLMClient` like all other agent tests

### Phase 3 (optional): Port remaining agents
- `profile_agent.py`, `client_research_agent.py`, `gap_agent.py`, `combined_agent.py`, `debrief_agent.py` — wrap in harness
- No change to persona_agent.py (it uses `.call()` not `.call_json()` — special case)

### Phase 4: Move OTel context propagation into harness
- Eliminate the `parent_ctx` / `otel_context.attach()` boilerplate from orchestrator
- Harness handles threading context automatically

---

## Key Open Questions

1. **Keep or kill standalone matching/writer?** They're dead code unless we rewire the orchestrator.
2. **One harness for all 7 agents, or two** (one for `call_json` agents, one for `call`/persona)?
3. **Should validation failure trigger an LLM retry with error feedback?** (Yes — this is a proven technique for improving structured output reliability.)
4. **Token counting**: Do we want real token counts (requires provider-specific API) or character-based estimates?
5. **PII sanitization in traces**: Logfire can capture message content — do we need to redact before logging?

---

## Appendix: Current Code Path Comparison

| Agent | LLM Path | Output Validation | Errors | Traces |
|-------|----------|-------------------|--------|--------|
| profile | `llm_client.call_json()` | None | HTTP retry only | None |
| client_research | `llm_client.call_json()` | None | HTTP retry only | None |
| matching | `pydantic_ai.Agent.run_sync()` | Pydantic model | pydantic_ai retry | None |
| writer | `pydantic_ai.Agent.run_sync()` | Pydantic model | pydantic_ai retry | None |
| combined | `llm_client.call_json()` | None | HTTP retry only | None |
| gap | `llm_client.call_json()` | None | HTTP retry only | None |
| persona | `llm_client.call()` | None | HTTP retry only | None |
| debrief | `llm_client.call_json()` | None | HTTP retry only | None |
