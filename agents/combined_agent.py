"""
Combined Agent — merges Matching + Writer + Gap into a single LLM call.
Used for speed optimization: replaces 3 sequential/parallel calls with 1.
"""

import json

SYSTEM_PROMPT = """You are a senior proposal specialist for a technology consulting firm.

You will receive:
1. A consultant's structured profile (skills, experience, projects)
2. A client's context (industry, challenges, required skills, tech stack, tone)

Produce ALL of the following in ONE response as a single valid JSON object:

{
  "relevance_map": {
    "top_matches": [
      {
        "type": "experience|project|skill",
        "item": "Name or description",
        "relevance_score": 9,
        "reason": "Why this is highly relevant",
        "suggested_framing": "How to present this"
      }
    ],
    "secondary_matches": [
      {
        "type": "experience|project|skill",
        "item": "Name or description",
        "relevance_score": 6,
        "reason": "Why somewhat relevant",
        "suggested_framing": "How to present this"
      }
    ],
    "client_tone_match": "How consultant should adapt communication style",
    "headline_positioning": "One sentence positioning for this client"
  },
  "tailored_cv": "Full tailored CV as markdown string. Lead with most relevant experience. Mirror client keywords where authentic.",
  "bio": "2-3 paragraph personalized bio in third person, matched to client industry and tone.",
  "talking_points": [
    "Talking point 1 — concrete opening statement",
    "Talking point 2 — connects past achievement to client challenge",
    "Talking point 3 — demonstrates industry understanding",
    "Talking point 4 — approach or methodology",
    "Talking point 5 — strategic question to ask client"
  ],
  "gap_analysis": {
    "gaps": [
      {
        "requirement": "What client needs",
        "gap_type": "missing_skill|limited_experience|no_direct_industry_exposure|certification_missing",
        "severity": "high|medium|low",
        "description": "Honest assessment",
        "framing_suggestion": "How to address in meeting",
        "mitigation": "Transferable experience that partially covers this"
      }
    ],
    "overall_fit_score": 8,
    "overall_fit_summary": "2-3 sentence honest summary",
    "strengths_to_lead_with": ["Top 2-3 genuine strengths"]
  }
}

Rules:
- Only use information explicitly in the profile. Never invent achievements.
- CV reorders and reframes — does not fabricate.
- Talking points are ready to say out loud.
- Gap analysis is honest — only flag real mismatches.
- Respond with valid JSON only. No markdown fences, no explanation.
"""


def run_combined_agent(structured_profile: dict, client_context: dict, llm_client) -> dict:
    """
    Single LLM call that replaces Matching + Writer + Gap agents.

    Returns dict with keys: relevance_map, tailored_cv, bio, talking_points, gap_analysis
    """
    print("[Combined Agent] Running (matching + writing + gap in one call)...")
    user_message = json.dumps({
        "consultant_profile": structured_profile,
        "client_context": client_context
    })
    result = llm_client.call_json(SYSTEM_PROMPT, user_message)
    print("[Combined Agent] Done.")
    return result
