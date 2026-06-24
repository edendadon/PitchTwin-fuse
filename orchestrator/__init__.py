"""
Orchestrator — runs the full PitchTwin pipeline.

Phase 1 (PARALLEL):   Profile Agent + Client Research Agent
Phase 2 (SINGLE):     Combined Agent (Matching + Writer + Gap in one LLM call)
Phase 3 (ON DEMAND):  Persona Agent (per message, called from Flask route)
Phase 4 (TRIGGERED):  Debrief Agent (fires on session end)
"""

import time
import uuid
import json
from datetime import datetime

import logfire

import db
from models import Proposal, TwinSession
from llm_client import LLMClient
from token_tracking import UsageTracker
from agents.profile_agent import run_profile_agent
from agents.client_research_agent import run_client_research_agent
from agents.combined_agent import run_combined_agent
from agents.persona_agent import build_system_prompt, run_persona_agent, run_persona_agent_stream
from agents.debrief_agent import run_debrief_agent
from orchestrator.workflow import WorkflowEngine, NodeConfig, CircuitBreakerOpen, WorkflowTimeout, MaxIterationsExceeded, DAGValidationError
from orchestrator.memory import MemoryStore


def _build_proposal_dag(profile_id: str, client_brief: str, company_name: str,
                        llm: LLMClient, tracker: UsageTracker):
    """Build the DAG for the proposal pipeline.

    Each wrapper sets the tracker's current node (node ids match the DAG ids
    AND the execution_traces.node_id values, so the debug-trace UI joins
    cleanly). The engine runs every wrapper in its own thread, so the
    thread-local node context cleanly attributes the LLM calls made inside.
    """

    def profile_agent_wrapper(input_data: dict) -> dict:
        with tracker.node("profile_agent"):
            profile = db.get_profile(input_data["consultant_id"])
            if not profile:
                raise ValueError(f"Consultant profile {input_data['consultant_id']} not found")
            result = run_profile_agent(profile.raw_profile, llm)
            profile.structured = result
            db.save_profile(profile)
            return result

    def research_agent_wrapper(input_data: dict) -> dict:
        with tracker.node("client_research"):
            return run_client_research_agent(
                input_data["client_brief"],
                input_data["company_name"],
                llm
            )

    def combined_agent_wrapper(input_data: dict) -> dict:
        with tracker.node("combined_agent"):
            structured_profile = input_data.get("profile_agent", {})
            client_context = input_data.get("client_research", {})
            return run_combined_agent(structured_profile, client_context, llm)

    dag = [
        {
            "id": "profile_agent",
            "type": "agent",
            # Single-shot transformer: one LLM call, retried on failure.
            "config": {"max_retries": 2, "timeout_sec": 60, "max_iterations": 1},
            "inputs": [],
            "agent_fn": profile_agent_wrapper,
        },
        {
            "id": "client_research",
            "type": "agent",
            "config": {"max_retries": 2, "timeout_sec": 60, "max_iterations": 1},
            "inputs": [],
            "agent_fn": research_agent_wrapper,
        },
        {
            "id": "combined_agent",
            "type": "agent",
            "config": {"max_retries": 2, "timeout_sec": 120, "max_iterations": 1},
            "inputs": ["profile_agent", "client_research"],
            "agent_fn": combined_agent_wrapper,
        },
    ]
    return dag


def run_proposal_pipeline(consultant_id: str, client_brief: str, company_name: str, proposal_id: str = None) -> Proposal:
    """
    Full pipeline: profile + research → matching → writer + gap → proposal stored.

    Uses WorkflowEngine with DAG-based execution for determinism, checkpointing,
    loop detection, circuit breaker, and timeout management.

    Returns:
        Completed Proposal object with all artifacts populated.
    """
    llm = LLMClient()

    # Per-run token/cost aggregator. Wired into the LLM client so every agent
    # call in the pipeline is captured, and into the DAG wrappers (below) so
    # each call is attributed to the node that made it.
    tracker = UsageTracker()
    llm.set_tracker(tracker)
    t0 = time.perf_counter()

    profile = db.get_profile(consultant_id)
    if not profile:
        raise ValueError(f"Consultant profile {consultant_id} not found")

    print(f"\n[Orchestrator] Starting pipeline for {profile.name} → {company_name}")

    if proposal_id is None:
        proposal_id = str(uuid.uuid4())

    with logfire.span(
        "proposal pipeline",
        consultant_id=consultant_id,
        consultant_name=profile.name,
        company_name=company_name,
    ):
        checkpoint_store = MemoryStore()
        trace_store = MemoryStore()

        dag = _build_proposal_dag(consultant_id, client_brief, company_name, llm, tracker)

        engine = WorkflowEngine(
            dag=dag,
            checkpoint_store=checkpoint_store,
            trace_store=trace_store,
            global_timeout_sec=240,
            circuit_breaker_threshold=3,
        )

        context = {
            "consultant_id": consultant_id,
            "client_brief": client_brief,
            "company_name": company_name,
        }

        try:
            result = engine.execute(proposal_id=proposal_id, context=context)
        except (CircuitBreakerOpen, WorkflowTimeout, MaxIterationsExceeded, DAGValidationError) as e:
            print(f"[Orchestrator] Pipeline error: {e}")
            raise

        combined = result["outputs"].get("combined_agent", {})
        relevance_map = combined.get("relevance_map", {}) if combined else {}
        gap_result = combined.get("gap_analysis", {}) if combined else {}

        client_context = result["outputs"].get("client_research", {})
        trace_id = result.get("trace_id", "")

    # --- STORE PROPOSAL ---
    proposal = Proposal(
        id=proposal_id,
        consultant_id=consultant_id,
        client_brief=client_brief,
        company_name=company_name,
        tailored_cv=combined.get("tailored_cv", ""),
        bio=combined.get("bio", ""),
        talking_points=combined.get("talking_points", []),
        gap_analysis=json.dumps(gap_result),
        relevance_map=relevance_map,
        client_context=client_context,
        status="awaiting_approval",
        created_at=datetime.utcnow().isoformat()
    )

    # Attach token/cost tracking (issue #6): status + latency live in
    # execution_traces (keyed by trace_id), tokens + cost live here on the
    # proposal's own usage blob, keyed per node_id so the UI can join them.
    duration = time.perf_counter() - t0
    proposal.trace_id = trace_id
    proposal.usage = tracker.to_usage_dict(duration, trace_id)

    db.save_proposal(proposal)

    print(f"[Orchestrator] Pipeline complete. Proposal ID: {proposal.id}, Trace: {trace_id}")
    return proposal


def create_twin_session(proposal_id: str) -> TwinSession:
    """
    Initialize a new twin session for a given proposal.
    Returns TwinSession with unique link ID.
    """
    session = TwinSession(
        id=str(uuid.uuid4()),
        proposal_id=proposal_id,
        transcript=[],
        status="active",
        created_at=datetime.utcnow().isoformat()
    )
    db.save_session(session)
    print(f"[Orchestrator] Twin session created: {session.id}")
    return session


def handle_twin_message(session_id: str, user_message: str) -> str:
    """
    Process a client message in the twin session.
    Loads context, calls Persona Agent, appends to transcript.

    Returns:
        Twin's response string
    """
    session = db.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session.status == "ended":
        return "This conversation has ended."

    proposal = db.get_proposal(session.proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {session.proposal_id} not found")

    profile = db.get_profile(proposal.consultant_id)
    if not profile:
        raise ValueError(f"Profile not found for proposal {proposal.consultant_id}")

    llm = LLMClient()

    with logfire.span(
        "twin message (persona agent)",
        session_id=session_id,
        consultant_id=proposal.consultant_id,
        consultant_name=profile.name,
        turn_count=len(session.transcript),
    ):
        # Build system prompt with real profile data (grounding constraint)
        system_prompt = build_system_prompt(profile.structured, proposal.relevance_map)

        # Get response from Persona Agent
        response = run_persona_agent(
            user_message=user_message,
            conversation_history=session.transcript,
            system_prompt=system_prompt,
            llm_client=llm
        )

    db.append_message(session_id, "user", user_message)
    db.append_message(session_id, "assistant", response)

    return response


def handle_twin_message_stream(session_id: str, user_message: str):
    """
    Generator yielding SSE-formatted token chunks for streaming twin response.
    User message is appended immediately; assistant response is assembled and
    saved only after the generator is fully consumed (client stayed connected).
    """
    session = db.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session.status == "ended":
        yield 'data: {"token": "This conversation has ended."}\n\n'
        yield 'data: {"done": true}\n\n'
        return

    proposal = db.get_proposal(session.proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {session.proposal_id} not found")

    profile = db.get_profile(proposal.consultant_id)
    if not profile:
        raise ValueError(f"Profile not found for proposal {proposal.consultant_id}")

    llm = LLMClient()

    prior_transcript = list(session.transcript)
    system_prompt = build_system_prompt(profile.structured, proposal.relevance_map)

    db.append_message(session_id, "user", user_message)

    full_tokens = []
    with logfire.span(
        "twin message stream (persona agent)",
        session_id=session_id,
        consultant_id=proposal.consultant_id,
        consultant_name=profile.name,
        turn_count=len(prior_transcript),
    ):
        for token in run_persona_agent_stream(
            user_message=user_message,
            conversation_history=prior_transcript,
            system_prompt=system_prompt,
            llm_client=llm,
        ):
            full_tokens.append(token)
            yield f'data: {json.dumps({"token": token})}\n\n'

    assembled = "".join(full_tokens)
    if assembled:
        db.append_message(session_id, "assistant", assembled)
    yield 'data: {"done": true}\n\n'


def end_twin_session(session_id: str) -> str:
    """
    End the twin session and trigger Debrief Agent.
    Returns debrief report text.
    """
    session = db.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    session.status = "ended"
    db.save_session(session)

    llm = LLMClient()
    with logfire.span(
        "debrief agent",
        session_id=session_id,
        turn_count=len(session.transcript),
    ):
        debrief_data = run_debrief_agent(session.transcript, llm)

    debrief_text = json.dumps(debrief_data, indent=2)

    session.debrief = debrief_text
    db.save_session(session)

    print(f"[Orchestrator] Session {session_id} ended. Debrief generated.")
    return debrief_text