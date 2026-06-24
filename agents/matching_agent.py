"""
Matching Agent
Input:  structured_profile (from Profile Agent) + client_context (from Client Research Agent)
Output: ranked relevance map — which parts of the consultant's background matter most for this client

Runs sequentially after both parallel agents complete. This is the central HANDOFF point.
"""

import json
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from agents.pydantic_ai_setup import create_model

SYSTEM_PROMPT = """You are a strategic consultant matching expert.

You will receive:
1. A consultant's structured profile (skills, experience, projects)
2. A client's context (industry, challenges, required skills, tech stack)

Your job is to produce a ranked relevance map that scores which parts of the consultant's background
are most relevant to this specific client engagement.

You MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.

Output format:
{
  "top_matches": [
    {
      "type": "experience|project|skill",
      "item": "Name or description of the experience/project/skill",
      "relevance_score": 9,
      "reason": "Why this is highly relevant to the client",
      "suggested_framing": "How to present this for maximum impact"
    }
  ],
  "secondary_matches": [
    {
      "type": "experience|project|skill",
      "item": "Name or description",
      "relevance_score": 6,
      "reason": "Why this is somewhat relevant",
      "suggested_framing": "How to present this"
    }
  ],
  "client_tone_match": "How should the consultant adapt their communication style to match this client?",
  "headline_positioning": "In one sentence, how should this consultant position themselves for this client?"
}

Score from 1-10. Top matches = 7-10. Secondary matches = 4-6. Exclude anything below 4.
Rank by relevance to the CLIENT's stated challenges and requirements, not by impressiveness alone.

GROUNDING (hard rule — no fabrication):
- Use ONLY facts explicitly present in the consultant's profile. Reframe and
  position them; never invent new facts.
- Do NOT upgrade or embellish a fact. A skill listed in the profile (e.g. "AWS")
  is NOT a certification ("AWS-certified"), a title, or "expertise" / "N years"
  unless the profile states exactly that.
- Never invent certifications, employers, clients, job titles, durations, or
  numeric metrics that are not in the profile.
- If the client requires a skill the consultant lacks, do NOT manufacture a match
  for it — omit it (the gap is handled elsewhere).
- When the client context is sparse, stay conservative: position only on what the
  profile actually supports rather than guessing client needs.
- Every "item" must name a real profile entry; "reason"/"suggested_framing"/
  "headline_positioning" may interpret and synthesize those facts but must assert
  no new concrete fact about the consultant.
"""


class MatchItem(BaseModel):
    type: str = Field(description="experience|project|skill")
    item: str = Field(description="Name or description")
    relevance_score: int = Field(ge=1, le=10, description="Relevance score 1-10")
    reason: str = Field(description="Why this is relevant")
    suggested_framing: str = Field(description="How to present this for maximum impact")


class MatchingOutput(BaseModel):
    top_matches: list[MatchItem] = Field(description="Top matches scored 7-10")
    secondary_matches: list[MatchItem] = Field(description="Secondary matches scored 4-6")
    client_tone_match: str = Field(description="How to adapt communication style")
    headline_positioning: str = Field(description="One-sentence positioning statement")


_agent: Agent | None = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            create_model(),
            output_type=MatchingOutput,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


def run_matching_agent(structured_profile: dict, client_context: dict) -> dict:
    """
    Produce ranked relevance map of consultant's background vs client needs.

    Args:
        structured_profile: Output from Profile Agent
        client_context: Output from Client Research Agent

    Returns:
        Relevance map dict
    """
    print("[Matching Agent] Running...")
    user_message = json.dumps({
        "consultant_profile": structured_profile,
        "client_context": client_context
    })
    agent = _get_agent()
    result = agent.run_sync(user_message)
    print("[Matching Agent] Done.")
    return result.output.model_dump()
