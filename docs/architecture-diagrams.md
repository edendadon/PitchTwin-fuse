# PitchTwin — Agent Architecture Diagrams

> FUSE 2026 Judges Bonus Challenge — *The Visuals.*
> Mandatory **Happy Path** + **Non-Happy Path (error recovery)** for PitchTwin's
> multi-agent pipeline. Diagrams are self-explanatory; the box→code map at the
> bottom ties every node to the source.

PitchTwin runs **5 agents** across **4 phases**. Phase 2 folds the Matching,
Writer and Gap agents into a single "Combined Agent" LLM call. Resilience lives
in two layers: provider retry + backoff in `LLMClient.call`, and JSON repair /
schema re-prompt / graceful degradation in `AgentHarness`.

PNG renders live in [`docs/diagrams/`](./diagrams). Regenerate with:

```bash
npx -y -p @mermaid-js/mermaid-cli mmdc -i docs/diagrams/happy-path.mmd \
  -o docs/diagrams/happy-path.png -b "#0d1117" -s 2
```

---

## Happy Path — full pipeline & where agents interact

![Happy path](./diagrams/happy-path.png)

```mermaid
flowchart TD
    U([Consultant submits<br/>brief + company + profile]) --> P1
    subgraph P1["PHASE 1 — PARALLEL threads"]
        direction LR
        PA["Profile Agent<br/>structures raw CV / profile"]
        CRA["Client Research Agent<br/>extracts client context"]
    end
    PA -- structured_profile --> H{{"HANDOFF<br/>profile + client context"}}
    CRA -- client_context --> H
    H --> P2
    subgraph P2["PHASE 2 — SINGLE LLM CALL"]
        CA["Combined Agent<br/>Matching + Writer + Gap"]
    end
    P2 --> PROP[("Proposal stored<br/>CV · bio · talking points · gaps")]
    PROP --> READY([Proposal page · status = ready])
    READY --> P3
    subgraph P3["PHASE 3 — ON DEMAND per client message"]
        PERSONA["Persona Agent<br/>grounded twin chat"]
    end
    P3 -.->|client ends session| P4
    subgraph P4["PHASE 4 — TRIGGERED on session end"]
        DEBRIEF["Debrief Agent<br/>summarizes transcript"]
    end
    P4 --> END([Debrief report])
```

---

## Non-Happy Path — error recovery (one agent call)

![Non-happy path](./diagrams/non-happy-path.png)

```mermaid
flowchart TD
    A([Agent.run]) --> B["LLMClient.call → provider<br/>litellm / gemini / groq"]
    B --> C{Provider error?}
    C -- yes --> R{"attempts left?<br/>max 3"}
    R -- yes --> W["sleep 2^attempt s<br/>exponential backoff"]
    W --> B
    R -- no --> X1[["RuntimeError —<br/>LLM failed after 3 tries"]]
    C -- no --> P["Parse JSON<br/>strip code fences"]
    P --> Q{Parseable?}
    Q -- no --> RX["regex-extract first object"]
    RX --> Q2{Recovered?}
    Q2 -- yes --> V
    Q2 -- no --> RP
    Q -- yes --> V["Validate vs<br/>Pydantic schema"]
    V --> S{Schema OK?}
    S -- yes --> G["Guardrail:<br/>flag skills absent from profile"]
    G --> Z([Validated output])
    S -- no --> RP{"harness retries<br/>left? max 2"}
    RP -- yes --> AP["Re-prompt with<br/>validation error appended"]
    AP --> B
    RP -- "no · parseable" --> D[["WARN + return best-effort dict<br/>pipeline survives"]]
    D --> Z
    RP -- "no · unparseable" --> X1
    X1 --> ESC["Orchestrator aggregates<br/>thread errors → RuntimeError"]
    ESC --> UI[["Flask route catches →<br/>renders error to consultant"]]
```

---

## Box → code map

| Diagram node | Source |
|---|---|
| Profile Agent | `agents/profile_agent.py` → `run_profile_agent` |
| Client Research Agent | `agents/client_research_agent.py` → `run_client_research_agent` |
| Combined Agent (Matching + Writer + Gap) | `agents/combined_agent.py` → `run_combined_agent` |
| Persona Agent | `agents/persona_agent.py` → `run_persona_agent` |
| Debrief Agent | `agents/debrief_agent.py` → `run_debrief_agent` |
| Phase orchestration / parallel threads / handoff | `orchestrator.py` → `run_proposal_pipeline` |
| Provider retry + exponential backoff | `llm_client.py:50` → `LLMClient.call` |
| JSON parse + fence strip + regex repair | `llm_client.py:107` → `LLMClient.call_json` |
| Schema re-prompt + graceful degradation | `agents/harness.py` → `AgentHarness._run_json` |
| Unsupported-skill guardrail | `agents/harness.py` → `NoHallucinationGuardrail` |
| Top-level error rendering | `app.py` route handlers (`try/except`) |
