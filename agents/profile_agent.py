"""
Profile Agent
Input:  raw consultant profile text
Output: structured JSON {skills, experience, projects, tone_markers}

Runs in parallel with Client Research Agent.
"""

import json

SYSTEM_PROMPT = """You are a professional profiler for technology consultants.

Your job is to extract and structure all relevant information from a consultant's raw profile/CV.

You MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.

Output format:
{
  "name": "Full Name",
  "title": "Current or primary title",
  "summary": "2-3 sentence professional summary",
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {
      "company": "Company Name",
      "role": "Role Title",
      "duration": "e.g. 2021-2023",
      "description": "What they did",
      "technologies": ["tech1", "tech2"],
      "achievements": ["achievement1", ...]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "client_or_context": "Who it was for",
      "description": "What was done",
      "technologies": ["tech1", "tech2"],
      "outcomes": "Measurable result if any"
    }
  ],
  "education": [
    {
      "degree": "Degree name",
      "institution": "Institution",
      "year": "Year"
    }
  ],
  "certifications": ["cert1", "cert2"],
  "tone_markers": "Describe this consultant's communication style in 2-3 sentences. Are they formal/informal? Technical/strategic? Concise/detailed?"
}

Extract ONLY what is explicitly stated in the profile. Do not invent or infer details that are not present.
"""


def run_profile_agent(raw_profile: str, llm_client) -> dict:
    """
    Parse raw consultant profile into structured data.

    Args:
        raw_profile: Raw text of the consultant's profile/CV
        llm_client: LLMClient instance

    Returns:
        Structured profile dict
    """
    print("[Profile Agent] Running...")
    result = llm_client.call_json(SYSTEM_PROMPT, raw_profile)
    print("[Profile Agent] Done.")
    return result
