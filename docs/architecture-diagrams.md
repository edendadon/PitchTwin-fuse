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

## Requirements coverage (issue #35)

| Challenge requirement | Where it's shown |
|---|---|
| **Happy Path** — end-to-end flow | Happy-path diagram: `Consultant submits …` → … → `Debrief report` |
| **Non-Happy Path** — error recovery | Non-happy diagram: provider retry/backoff + schema re-prompt + graceful degradation |
| **Show the agents** | All 5 agents are explicit nodes (Profile, Client Research, Combined, Persona, Debrief) |
| **…and where they interact** | 4 numbered **INTERACTION** points on the happy path |
| **Clearly mark interaction points** | `INTERACTION 1–4` callouts (handoff, validate/approve, grounding, transcript) |

### Agent roles (mapped to the challenge's example template)

| Challenge role | PitchTwin agent(s) | Phase |
|---|---|---|
| Collects Information | Profile Agent + Client Research Agent | 1 (parallel) |
| Processes Data | Combined Agent (Matching + Writer + Gap) | 2 |
| Validates & Approves | `AgentHarness` schema check + no-hallucination guardrail | gate after 2 |
| Notifies User | Proposal page (consultant) · Persona Agent (client) · Debrief Agent | 2 → 3 → 4 |

### Interaction points

1. **HANDOFF** — Profile + Client Research outputs merge into the Combined Agent input.
2. **VALIDATE & APPROVE** — Combined Agent draft passes the harness schema check (+ guardrail when grounded) before it's stored.
3. **GROUNDING** — stored `relevance_map` + structured profile seed the Persona Agent's system prompt.
4. **TRANSCRIPT** — the twin transcript is handed to the Debrief Agent on session end.

---

## Happy Path — full pipeline & where agents interact

![Happy path](./diagrams/happy-path.png)

```mermaid
flowchart TD
    U([Consultant submits<br/>brief + company + profile]) --> P1
    subgraph P1["PHASE 1 · PARALLEL threads — role: COLLECT"]
        direction LR
        PA["Profile Agent<br/>structures raw CV / profile"]
        CRA["Client Research Agent<br/>extracts client context"]
    end
    PA -- "structured_profile" --> H{{"INTERACTION 1 · HANDOFF<br/>profile + client context"}}
    CRA -- "client_context" --> H
    H --> P2
    subgraph P2["PHASE 2 · SINGLE LLM CALL — role: PROCESS"]
        CA["Combined Agent<br/>Matching + Writer + Gap"]
    end
    CA -- "draft JSON" --> VAL{{"INTERACTION 2 · VALIDATE & APPROVE<br/>AgentHarness: schema check<br/>+ guardrail when grounded"}}
    VAL --> PROP[("Proposal stored<br/>CV · bio · talking points · gaps")]
    PROP --> READY([Proposal page · status = ready<br/>role: NOTIFY consultant])
    READY -- "INTERACTION 3<br/>relevance_map + profile grounding" --> P3
    subgraph P3["PHASE 3 · ON DEMAND per client message — role: NOTIFY client"]
        PERSONA["Persona Agent<br/>grounded twin chat"]
    end
    P3 -. "INTERACTION 4 · transcript" .-> P4
    subgraph P4["PHASE 4 · TRIGGERED on session end — role: DEBRIEF / NOTIFY"]
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
| Validate & Approve gate (schema + guardrail) | `agents/harness.py` → `AgentHarness` / `NoHallucinationGuardrail` |
| Provider retry + exponential backoff | `llm_client.py:50` → `LLMClient.call` |
| JSON parse + fence strip + regex repair | `llm_client.py:107` → `LLMClient.call_json` |
| Schema re-prompt + graceful degradation | `agents/harness.py` → `AgentHarness._run_json` |
| Top-level error rendering | `app.py` route handlers (`try/except`) |
