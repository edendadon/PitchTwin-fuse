"""
Agent harness tests — validation, retry, tracing, and the no-hallucination guardrail.
Uses scripted/mock LLM clients; no real API calls.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.harness import AgentHarness, NoHallucinationGuardrail
from agents.schemas import ProfileOutput, ClientContextOutput


class ScriptedLLM:
    """Returns pre-scripted responses in order; records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call_json(self, system_prompt, user_message):
        self.calls.append((system_prompt, user_message))
        return self.responses.pop(0)

    def call(self, system_prompt, user_message):
        self.calls.append((system_prompt, user_message))
        return self.responses.pop(0)


class DispatchLLM:
    """Mock that dispatches canned JSON by a substring of the agent's system prompt."""

    def call(self, system_prompt, user_message):
        return "mock response"

    def call_json(self, system_prompt, user_message):
        sp = system_prompt.lower()
        if "professional profiler" in sp:
            return {
                "name": "Test Consultant", "title": "Senior Consultant",
                "summary": "Test.", "skills": ["Python", "AWS"],
                "experience": [], "projects": [], "education": [],
                "certifications": [], "tone_markers": "Direct.",
            }
        if "consulting sales" in sp:
            return {
                "company_name": "TestCo", "industry": "FinTech",
                "key_challenges": ["scalability"], "required_skills": ["Python"],
                "nice_to_have_skills": [], "tech_stack_mentioned": ["AWS"],
                "tone": "formal", "keywords_to_mirror": ["scalability"],
            }
        return {"result": "mock"}


# --- No-hallucination guardrail (issue #1 acceptance test) ---

def test_no_hallucination_guardrail_flags_fabricated_skill():
    profile = {
        "skills": ["Python", "AWS"],
        "experience": [{"technologies": ["Django"]}],
        "projects": [{"technologies": ["PostgreSQL"]}],
        "certifications": ["AWS Certified"],
    }
    guard = NoHallucinationGuardrail(profile)

    # Kubernetes is NOT anywhere in the profile -> must be flagged
    assert guard.check(["Python", "Kubernetes"]) == ["Kubernetes"]
    # everything supported -> grounded
    assert guard.is_grounded(["Python", "Django", "PostgreSQL"]) is True
    # a fabricated skill -> not grounded
    assert guard.is_grounded(["Kubernetes"]) is False
    print("PASS: no_hallucination_guardrail")


# --- Output validation + retry ---

def test_harness_retries_on_invalid_output_then_succeeds():
    # First response is missing the required "name" field -> ValidationError -> retry.
    llm = ScriptedLLM([
        {"skills": ["Python"]},                       # invalid (no name)
        {"name": "Jane", "skills": ["Python"]},       # valid
    ])
    harness = AgentHarness(llm, name="profile", system_prompt="SP", output_schema=ProfileOutput)

    result = harness.run("raw profile text")

    assert result["name"] == "Jane"
    assert len(llm.calls) == 2  # retried exactly once
    print("PASS: harness_retries_on_invalid_output")


def test_harness_returns_valid_output_without_retry():
    llm = ScriptedLLM([{"name": "Jane", "skills": ["Python"]}])
    harness = AgentHarness(llm, name="profile", system_prompt="SP", output_schema=ProfileOutput)

    result = harness.run("raw")

    assert result["name"] == "Jane"
    assert len(llm.calls) == 1  # no retry needed
    print("PASS: harness_no_retry_on_valid_output")


def test_harness_text_mode_returns_string():
    llm = ScriptedLLM(["  Hello, I am a twin.  "])
    harness = AgentHarness(llm, name="persona", system_prompt="SP", mode="text")

    out = harness.run("hi")

    assert out == "Hello, I am a twin."  # stripped
    assert len(llm.calls) == 1
    print("PASS: harness_text_mode")


# --- Agents run via the harness and produce schema-valid output (T-274) ---

def test_profile_and_client_research_run_via_harness():
    from agents.profile_agent import run_profile_agent
    from agents.client_research_agent import run_client_research_agent

    llm = DispatchLLM()
    profile = run_profile_agent("John Smith, Python expert", llm)
    context = run_client_research_agent("We need Python for fintech", "TestCo", llm)

    # No exception => output conforms to the declared schema.
    ProfileOutput.model_validate(profile)
    ClientContextOutput.model_validate(context)
    assert profile["name"] == "Test Consultant"
    assert context["industry"] == "FinTech"
    print("PASS: profile_and_client_research_via_harness")


if __name__ == "__main__":
    test_no_hallucination_guardrail_flags_fabricated_skill()
    test_harness_retries_on_invalid_output_then_succeeds()
    test_harness_returns_valid_output_without_retry()
    test_harness_text_mode_returns_string()
    test_profile_and_client_research_run_via_harness()
    print("\nAll harness tests passed.")
