"""
Matching Agent
Input:  structured_profile (from Profile Agent) + client_context (from Client Research Agent)
Output: ranked relevance map — which parts of the consultant's background matter most for this client

Runs sequentially after both parallel agents complete. This is the central HANDOFF point.
"""

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
"""


def run_matching_agent(structured_profile: dict, client_context: dict, llm_client) -> dict:
    """
    Produce ranked relevance map of consultant's background vs client needs.

    Args:
        structured_profile: Output from Profile Agent
        client_context: Output from Client Research Agent
        llm_client: LLMClient instance

    Returns:
        Relevance map dict
    """
    import json
    print("[Matching Agent] Running...")
    user_message = json.dumps({
        "consultant_profile": structured_profile,
        "client_context": client_context
    })
    result = llm_client.call_json(SYSTEM_PROMPT, user_message)
    print("[Matching Agent] Done.")
    return result
