"""
Basic agent tests — uses a mock LLM client to verify agent logic
without making real API calls.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from unittest.mock import MagicMock, patch
from agents.profile_agent import run_profile_agent
from agents.client_research_agent import run_client_research_agent
from agents.matching_agent import run_matching_agent
import agents.matching_agent as matching_module
from agents.writer_agent import run_writer_agent
import agents.writer_agent as writer_module
from agents.gap_agent import run_gap_agent
from agents.persona_agent import build_system_prompt, run_persona_agent
from agents.debrief_agent import run_debrief_agent


class MockLLMClient:
    """Minimal mock that returns canned JSON responses."""

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
    profile = {"skills": ["Python"], "experience": [], "projects": []}
    context = {"industry": "FinTech", "required_skills": ["Python"]}
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output.model_dump.return_value = {
        "top_matches": [{"type": "skill", "item": "Python", "relevance_score": 9,
                         "reason": "Required", "suggested_framing": "Lead with Python"}],
        "secondary_matches": [], "client_tone_match": "Be direct.",
        "headline_positioning": "Strong fit for this engagement."
    }
    with patch.object(matching_module, "_agent", mock_agent):
        result = run_matching_agent(profile, context)
    assert "top_matches" in result
    print("PASS: matching_agent")


def test_writer_agent():
    relevance_map = {"top_matches": [], "secondary_matches": [], "headline_positioning": "Strong fit"}
    profile = {"name": "Test", "skills": [], "experience": []}
    context = {"tone": "formal", "industry": "FinTech"}
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output.model_dump.return_value = {
        "tailored_cv": "# Tailored CV\n\nTest CV content.",
        "bio": "Test bio paragraph.",
        "talking_points": ["Point 1", "Point 2", "Point 3"]
    }
    with patch.object(writer_module, "_agent", mock_agent):
        result = run_writer_agent(relevance_map, profile, context)
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
    print("\nAll tests passed.")
