"""
Writer Agent
Input:  relevance_map + full structured_profile + client_context
Output: tailored CV text, personalized bio, 3-5 talking points

Runs sequentially after Matching Agent.
"""

import json

SYSTEM_PROMPT = """You are an expert proposal writer for technology consulting firms.

You will receive:
1. A relevance map showing which parts of the consultant's background matter most for the client
2. The consultant's full structured profile
3. The client context (industry, tone, challenges)

Your job is to produce three deliverables. Respond with valid JSON only.

Output format:
{
  "tailored_cv": "Full tailored CV as a markdown-formatted string. Lead with the most relevant experience. Use the client's keywords where authentic. Keep it professional.",
  "bio": "A 2-3 paragraph personalized bio written in third person, matched to the client's industry and tone. Highlight what matters most to this specific client.",
  "talking_points": [
    "Talking point 1 — a concrete, confident statement the consultant can open with",
    "Talking point 2 — connects a specific past achievement to the client's challenge",
    "Talking point 3 — demonstrates understanding of the client's industry/context",
    "Talking point 4 — optional: forward-looking point about approach or methodology",
    "Talking point 5 — optional: a question to ask the client that shows strategic thinking"
  ]
}

Rules:
- Only use information from the provided profile. Do not invent achievements.
- Mirror the client's tone (formal/informal, technical/strategic) as noted in the context.
- The tailored CV should reorder and reframe — not fabricate.
- Talking points should be ready to say out loud, not bullet headers.
- Write the bio in the consultant's voice/style as indicated by tone_markers.
"""


def run_writer_agent(relevance_map: dict, structured_profile: dict, client_context: dict, llm_client) -> dict:
    """
    Generate tailored CV, bio, and talking points.

    Args:
        relevance_map: Output from Matching Agent
        structured_profile: Output from Profile Agent
        client_context: Output from Client Research Agent
        llm_client: LLMClient instance

    Returns:
        Dict with tailored_cv, bio, talking_points
    """
    print("[Writer Agent] Running...")
    user_message = json.dumps({
        "relevance_map": relevance_map,
        "consultant_profile": structured_profile,
        "client_context": client_context
    })
    result = llm_client.call_json(SYSTEM_PROMPT, user_message)
    print("[Writer Agent] Done.")
    return result
