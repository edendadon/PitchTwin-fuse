"""
Gap Agent
Input:  client_context (required skills/challenges) + structured_profile
Output: gap analysis — what's missing and how to address it

Runs sequentially after Matching Agent (can run in parallel with Writer Agent).
"""

import json

SYSTEM_PROMPT = """You are a candid advisor to technology consultants preparing for pitches.

You will receive:
1. Client context including required skills and key challenges
2. The consultant's structured profile

Your job is to honestly identify gaps — requirements the client has that the consultant does NOT clearly demonstrate in their profile — and suggest how to frame or address each gap.

Respond with valid JSON only.

Output format:
{
  "gaps": [
    {
      "requirement": "What the client needs",
      "gap_type": "missing_skill|limited_experience|no_direct_industry_exposure|certification_missing",
      "severity": "high|medium|low",
      "description": "Honest assessment of the gap",
      "framing_suggestion": "How the consultant can acknowledge or bridge this gap in the meeting",
      "mitigation": "Any transferable experience or adjacent skill that partially addresses this"
    }
  ],
  "overall_fit_score": 8,
  "overall_fit_summary": "2-3 sentence honest summary of fit quality",
  "strengths_to_lead_with": ["Top 2-3 genuine strengths that address this client's needs directly"]
}

Be honest. A gap note that catches a real problem before the meeting is more valuable than false reassurance.
Do not list gaps for things the consultant clearly has. Only flag genuine mismatches.
"""


def run_gap_agent(client_context: dict, structured_profile: dict, llm_client) -> dict:
    """
    Identify gaps between client requirements and consultant profile.

    Args:
        client_context: Output from Client Research Agent
        structured_profile: Output from Profile Agent
        llm_client: LLMClient instance

    Returns:
        Gap analysis dict
    """
    print("[Gap Agent] Running...")
    user_message = json.dumps({
        "client_context": client_context,
        "consultant_profile": structured_profile
    })
    result = llm_client.call_json(SYSTEM_PROMPT, user_message)
    print("[Gap Agent] Done.")
    return result
