"""
Basic agent tests — uses a mock LLM client to verify agent logic
without making real API calls.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents.profile_agent import run_profile_agent
from agents.client_research_agent import run_client_research_agent
from agents.matching_agent import run_matching_agent
from agents.writer_agent import run_writer_agent
from agents.gap_agent import run_gap_agent
from agents.persona_agent import build_system_prompt, run_persona_agent, run_persona_agent_stream
from agents.debrief_agent import run_debrief_agent


class MockLLMClient:
    """Minimal mock that returns canned JSON responses."""

    def call_stream(self, system_prompt, user_message):
        """Yields three canned tokens."""
        for token in ["Hello", " there", "!"]:
            yield token

    def call(self, system_prompt, user_message):
        return '{"result": "mock"}'

    def call_json(self, system_prompt, user_message):
        # Dispatch by unique first-line identifier of each agent's system prompt
        sp = system_prompt.lower()
        if "consulting sales" in sp:
            # Client Research Agent
            return {
                "company_name": "TestCo", "industry": "FinTech",
                "key_challenges": ["scalability"], "required_skills": ["Python"],
                "nice_to_have_skills": [], "tech_stack_mentioned": ["AWS"],
                "tone": "formal", "keywords_to_mirror": ["scalability"]
            }
        elif "sales intelligence" in sp:
            # Debrief Agent
            return {
                "session_summary": "Client asked about Python experience.",
                "topics_explored": [], "apparent_priorities": ["Python expertise"],
                "concerns_or_hesitations": [], "positive_signals": ["Showed interest"],
                "questions_asked": ["Do you know Python?"],
                "recommended_talking_points": ["Lead with Python projects"],
                "overall_engagement_level": "high", "red_flags": []
            }
        elif "matching expert" in sp:
            # Matching Agent
            return {
                "top_matches": [{"type": "skill", "item": "Python", "relevance_score": 9,
                                 "reason": "Required", "suggested_framing": "Lead with Python"}],
                "secondary_matches": [], "client_tone_match": "Be direct.",
                "headline_positioning": "Strong fit for this engagement."
            }
        elif "proposal writer" in sp:
            # Writer Agent
            return {
                "tailored_cv": "# Tailored CV\n\nTest CV content.",
                "bio": "Test bio paragraph.",
                "talking_points": ["Point 1", "Point 2", "Point 3"]
            }
        elif "candid advisor" in sp:
            # Gap Agent
            return {
                "gaps": [], "overall_fit_score": 9,
                "overall_fit_summary": "Strong fit.",
                "strengths_to_lead_with": ["Python expertise"]
            }
        elif "professional profiler" in sp:
            # Profile Agent
            return {
                "name": "Test Consultant", "title": "Senior Consultant",
                "summary": "Test summary.", "skills": ["Python", "AWS"],
                "experience": [], "projects": [], "education": [],
                "certifications": [], "tone_markers": "Direct and technical."
            }
        return {"result": "mock"}


def test_profile_agent():
    mock = MockLLMClient()
    result = run_profile_agent("John Smith, Senior Dev, Python expert", mock)
    assert "name" in result
    assert "skills" in result
    print("PASS: profile_agent")


def test_client_research_agent():
    mock = MockLLMClient()
    result = run_client_research_agent("We need a Python expert for fintech work", "TestCo", mock)
    assert "industry" in result
    assert "required_skills" in result
    print("PASS: client_research_agent")


def test_matching_agent():
    mock = MockLLMClient()
    profile = {"skills": ["Python"], "experience": [], "projects": []}
    context = {"industry": "FinTech", "required_skills": ["Python"]}
    result = run_matching_agent(profile, context, mock)
    assert "top_matches" in result
    print("PASS: matching_agent")


def test_writer_agent():
    mock = MockLLMClient()
    relevance_map = {"top_matches": [], "secondary_matches": [], "headline_positioning": "Strong fit"}
    profile = {"name": "Test", "skills": [], "experience": []}
    context = {"tone": "formal", "industry": "FinTech"}
    result = run_writer_agent(relevance_map, profile, context, mock)
    assert "tailored_cv" in result
    assert "talking_points" in result
    print("PASS: writer_agent")


def test_gap_agent():
    mock = MockLLMClient()
    context = {"required_skills": ["Python"]}
    profile = {"skills": ["Python"]}
    result = run_gap_agent(context, profile, mock)
    assert "gaps" in result
    assert "overall_fit_score" in result
    print("PASS: gap_agent")


def test_persona_agent():
    mock = MockLLMClient()
    profile = {
        "name": "Test Consultant",
        "skills": ["Python"],
        "experience": [],
        "projects": [],
        "tone_markers": "Direct."
    }
    relevance_map = {"top_matches": [], "headline_positioning": "Strong fit."}
    system_prompt = build_system_prompt(profile, relevance_map)
    assert "Test Consultant" in system_prompt
    assert "CRITICAL RULES" in system_prompt

    # Mock returns plain string for .call()
    response = mock.call(system_prompt, "What is your Python experience?")
    assert response is not None
    print("PASS: persona_agent")


def test_debrief_agent_empty():
    mock = MockLLMClient()
    result = run_debrief_agent([], mock)
    assert result["session_summary"] == "No conversation took place."
    print("PASS: debrief_agent (empty transcript)")


def test_debrief_agent_with_transcript():
    mock = MockLLMClient()
    transcript = [
        {"role": "user", "content": "Do you know Python?", "timestamp": "2026-01-01T10:00:00"},
        {"role": "assistant", "content": "Yes, I have 5 years of Python experience.", "timestamp": "2026-01-01T10:00:05"},
    ]
    result = run_debrief_agent(transcript, mock)
    assert "session_summary" in result
    print("PASS: debrief_agent (with transcript)")


def test_run_persona_agent_stream():
    mock = MockLLMClient()
    profile = {
        "name": "Test Consultant",
        "skills": ["Python"],
        "experience": [],
        "projects": [],
        "tone_markers": "Direct."
    }
    relevance_map = {"top_matches": [], "headline_positioning": "Strong fit."}
    system_prompt = build_system_prompt(profile, relevance_map)

    tokens = list(run_persona_agent_stream(
        user_message="Tell me about yourself.",
        conversation_history=[],
        system_prompt=system_prompt,
        llm_client=mock
    ))
    assert len(tokens) > 0
    assert all(isinstance(t, str) for t in tokens)
    assembled = "".join(tokens)
    assert assembled == "Hello there!"
    print("PASS: run_persona_agent_stream")


def test_run_persona_agent_stream_with_history():
    mock = MockLLMClient()
    profile = {"name": "Test", "skills": [], "experience": [], "projects": [], "tone_markers": "Direct."}
    relevance_map = {"top_matches": [], "headline_positioning": ""}
    system_prompt = build_system_prompt(profile, relevance_map)

    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]
    tokens = list(run_persona_agent_stream(
        user_message="What's your experience?",
        conversation_history=history,
        system_prompt=system_prompt,
        llm_client=mock
    ))
    assert "".join(tokens) == "Hello there!"
    print("PASS: run_persona_agent_stream (with history)")


def test_proposal_status_and_approve_routes():
    """Integration test: status route returns correct values; approve route creates session."""
    import uuid as uuid_mod
    from app import app as flask_app
    import db as db_mod
    from models import Proposal, ConsultantProfile
    from datetime import datetime

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test"

    with flask_app.test_client() as client:
        db_mod.init_db()

        # Create a minimal consultant profile
        profile_id = str(uuid_mod.uuid4())
        profile = ConsultantProfile(
            id=profile_id, name="Tester",
            raw_profile="Test profile",
            structured={},
            created_at=datetime.utcnow().isoformat()
        )
        db_mod.save_profile(profile)

        # Create proposal in awaiting_approval state
        proposal_id = str(uuid_mod.uuid4())
        proposal = Proposal(
            id=proposal_id,
            consultant_id=profile_id,
            client_brief="Test brief",
            company_name="TestCo",
            status="awaiting_approval",
            created_at=datetime.utcnow().isoformat()
        )
        db_mod.save_proposal(proposal)

        # GET /proposal/<id>/status → AWAITING_APPROVAL
        res = client.get(f"/proposal/{proposal_id}/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "AWAITING_APPROVAL"

        # POST /proposal/<id>/approve → creates session, status becomes READY
        res = client.post(f"/proposal/{proposal_id}/approve")
        assert res.status_code in (200, 302)

        res = client.get(f"/proposal/{proposal_id}/status")
        data = res.get_json()
        assert data["status"] == "READY"

        # Session should exist
        sess = db_mod.get_session_by_proposal(proposal_id)
        assert sess is not None

        # Duplicate approve → redirects with flash
        res = client.post(f"/proposal/{proposal_id}/approve", follow_redirects=False)
        assert res.status_code == 302

    print("PASS: proposal_status_and_approve_routes")


def test_proposal_status_generating():
    import uuid as uuid_mod
    from app import app as flask_app
    import db as db_mod
    from models import Proposal, ConsultantProfile
    from datetime import datetime

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        db_mod.init_db()
        profile_id = str(uuid_mod.uuid4())
        db_mod.save_profile(ConsultantProfile(
            id=profile_id, name="T", raw_profile="x", structured={},
            created_at=datetime.utcnow().isoformat()
        ))
        proposal_id = str(uuid_mod.uuid4())
        db_mod.save_proposal(Proposal(
            id=proposal_id, consultant_id=profile_id, client_brief="b",
            company_name="C", status="generating",
            created_at=datetime.utcnow().isoformat()
        ))
        res = client.get(f"/proposal/{proposal_id}/status")
        assert res.get_json()["status"] == "GENERATING"
    print("PASS: proposal_status_generating")


if __name__ == "__main__":
    print("\n=== PitchTwin Agent Tests ===\n")
    test_profile_agent()
    test_client_research_agent()
    test_matching_agent()
    test_writer_agent()
    test_gap_agent()
    test_persona_agent()
    test_debrief_agent_empty()
    test_debrief_agent_with_transcript()
    test_run_persona_agent_stream()
    test_run_persona_agent_stream_with_history()
    test_proposal_status_and_approve_routes()
    test_proposal_status_generating()
    print("\nAll tests passed.")
