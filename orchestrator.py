"""
Orchestrator — runs the full PitchTwin pipeline.

Phase 1 (PARALLEL):   Profile Agent + Client Research Agent
Phase 2 (SINGLE):     Combined Agent (Matching + Writer + Gap in one LLM call)
Phase 3 (ON DEMAND):  Persona Agent (per message, called from Flask route)
Phase 4 (TRIGGERED):  Debrief Agent (fires on session end)
"""

import uuid
import threading
import json
from datetime import datetime

import db
from models import Proposal, TwinSession
from llm_client import LLMClient
from agents.profile_agent import run_profile_agent
from agents.client_research_agent import run_client_research_agent
from agents.combined_agent import run_combined_agent
from agents.persona_agent import build_system_prompt, run_persona_agent
from agents.debrief_agent import run_debrief_agent


def run_proposal_pipeline(consultant_id: str, client_brief: str, company_name: str) -> Proposal:
    """
    Full pipeline: profile + research → matching → writer + gap → proposal stored.

    Returns:
        Completed Proposal object with all artifacts populated.
    """
    llm = LLMClient()

    # Load consultant profile
    profile = db.get_profile(consultant_id)
    if not profile:
        raise ValueError(f"Consultant profile {consultant_id} not found")

    print(f"\n[Orchestrator] Starting pipeline for {profile.name} → {company_name}")

    # --- PHASE 1: PARALLEL ---
    structured_profile_result = {}
    client_context_result = {}
    errors = []

    def run_profile():
        try:
            result = run_profile_agent(profile.raw_profile, llm)
            structured_profile_result.update(result)
        except Exception as e:
            errors.append(f"Profile Agent failed: {e}")

    def run_research():
        try:
            result = run_client_research_agent(client_brief, company_name, llm)
            client_context_result.update(result)
        except Exception as e:
            errors.append(f"Client Research Agent failed: {e}")

    t1 = threading.Thread(target=run_profile)
    t2 = threading.Thread(target=run_research)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    if errors:
        raise RuntimeError(f"Parallel phase failed: {errors}")

    # Save structured profile back to db
    profile.structured = structured_profile_result
    db.save_profile(profile)

    print("[Orchestrator] Phase 1 complete. Starting Phase 2 (combined)...")

    # --- PHASE 2: SINGLE COMBINED CALL ---
    # HANDOFF: profile data + client context → combined agent (match + write + gap)
    combined = run_combined_agent(structured_profile_result, client_context_result, llm)

    relevance_map = combined.get("relevance_map", {})
    gap_result = combined.get("gap_analysis", {})

    # --- STORE PROPOSAL ---
    proposal = Proposal(
        id=str(uuid.uuid4()),
        consultant_id=consultant_id,
        client_brief=client_brief,
        company_name=company_name,
        tailored_cv=combined.get("tailored_cv", ""),
        bio=combined.get("bio", ""),
        talking_points=combined.get("talking_points", []),
        gap_analysis=json.dumps(gap_result),
        relevance_map=relevance_map,
        client_context=client_context_result,
        status="ready",
        created_at=datetime.utcnow().isoformat()
    )
    db.save_proposal(proposal)

    print(f"[Orchestrator] Pipeline complete. Proposal ID: {proposal.id}")
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

    # Build system prompt with real profile data (grounding constraint)
    system_prompt = build_system_prompt(profile.structured, proposal.relevance_map)

    # Get response from Persona Agent
    response = run_persona_agent(
        user_message=user_message,
        conversation_history=session.transcript,
        system_prompt=system_prompt,
        llm_client=llm
    )

    # Append both turns to transcript
    db.append_message(session_id, "user", user_message)
    db.append_message(session_id, "assistant", response)

    return response


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
    debrief_data = run_debrief_agent(session.transcript, llm)

    # Format debrief as readable text
    debrief_text = json.dumps(debrief_data, indent=2)

    session.debrief = debrief_text
    db.save_session(session)

    print(f"[Orchestrator] Session {session_id} ended. Debrief generated.")
    return debrief_text
