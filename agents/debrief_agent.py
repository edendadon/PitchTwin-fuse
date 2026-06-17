"""
Debrief Agent
Input:  full conversation transcript (list of {role, content, timestamp})
Output: structured debrief report for the consultant

Triggered automatically when the client ends or exits the twin session.
"""

import json

SYSTEM_PROMPT = """You are an expert sales intelligence analyst.

You will receive a transcript of a conversation between a potential client and a consultant's digital twin.

Your job is to extract actionable intelligence for the consultant before their first real meeting.

Respond with valid JSON only.

Output format:
{
  "session_summary": "2-3 sentence overview of the conversation",
  "topics_explored": [
    {
      "topic": "Topic name",
      "depth": "deep|surface|briefly_mentioned",
      "client_sentiment": "positive|neutral|concerned|enthusiastic"
    }
  ],
  "apparent_priorities": ["What the client seems to care most about, ranked"],
  "concerns_or_hesitations": ["Any hesitations, doubts, or concerns the client expressed"],
  "positive_signals": ["Statements or questions that suggest genuine interest"],
  "questions_asked": ["Every distinct question the client asked, verbatim or paraphrased"],
  "recommended_talking_points": [
    "Specific thing the consultant should open with based on what this client cares about",
    "A concern they should proactively address",
    "A topic to go deeper on",
    "A question to ask the client"
  ],
  "overall_engagement_level": "high|medium|low",
  "red_flags": ["Any signals that suggest the client has reservations or the fit may be poor"]
}

Be specific and actionable. The consultant reads this 5 minutes before the real meeting.
"""


def run_debrief_agent(transcript: list, llm_client) -> dict:
    """
    Analyze client-twin conversation and produce debrief report.

    Args:
        transcript: List of {role, content, timestamp} dicts
        llm_client: LLMClient instance

    Returns:
        Debrief report dict
    """
    print("[Debrief Agent] Running...")

    if not transcript:
        return {
            "session_summary": "No conversation took place.",
            "topics_explored": [],
            "apparent_priorities": [],
            "concerns_or_hesitations": [],
            "positive_signals": [],
            "questions_asked": [],
            "recommended_talking_points": [],
            "overall_engagement_level": "low",
            "red_flags": []
        }

    # Format transcript for LLM
    formatted = "\n".join(
        f"{turn['role'].upper()} [{turn.get('timestamp', '')}]: {turn['content']}"
        for turn in transcript
    )

    result = llm_client.call_json(SYSTEM_PROMPT, f"TRANSCRIPT:\n{formatted}")
    print("[Debrief Agent] Done.")
    return result
