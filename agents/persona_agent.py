"""
Persona Agent
Input:  full structured_profile + relevance_map + conversation history
Output: a single chat response in the consultant's voice

This agent powers the interactive twin. It is called once per client message.
CRITICAL: It must never invent experience not present in the profile.
"""

import json

from agents.harness import AgentHarness


def build_system_prompt(structured_profile: dict, relevance_map: dict) -> str:
    """
    Build the persona system prompt by injecting the real profile data.
    This is called once at session start and reused for the entire conversation.
    """
    profile_json = json.dumps(structured_profile, indent=2)
    top_matches = json.dumps(relevance_map.get("top_matches", []), indent=2)
    tone_markers = structured_profile.get("tone_markers", "Professional and direct.")
    name = structured_profile.get("name", "the consultant")
    headline = relevance_map.get("headline_positioning", "")

    return f"""You are a digital twin of {name}, a technology consultant.

Your entire knowledge base is the profile below. You represent this person in pre-meeting conversations with potential clients.

CRITICAL RULES:
1. You ONLY reference experiences, skills, and projects that are explicitly listed in the profile below.
2. If a client asks about something NOT in the profile, say so honestly: "That's not something I have direct experience with" or "My background doesn't include that specifically."
3. Never fabricate projects, clients, certifications, or achievements.
4. Respond in {name}'s communication style: {tone_markers}
5. Be helpful, confident, and concise. This is a professional pre-meeting conversation.
6. You may say "I" — you are representing {name} in first person.
7. Keep responses to 3-5 sentences unless the client asks for detail.

POSITIONING FOR THIS CLIENT:
{headline}

TOP RELEVANT EXPERIENCE FOR THIS ENGAGEMENT:
{top_matches}

FULL PROFILE (your only source of truth):
{profile_json}

When asked what you can't help with, suggest the client ask about topics covered in the profile above.
"""


def run_persona_agent(
    user_message: str,
    conversation_history: list,
    system_prompt: str,
    llm_client
) -> str:
    """
    Generate a single twin response to a client message.

    Args:
        user_message: The client's latest message
        conversation_history: List of {role, content} dicts (prior turns)
        system_prompt: Pre-built system prompt with injected profile data
        llm_client: LLMClient instance

    Returns:
        Twin's response as a string
    """
    # Build conversation context for the LLM
    # Format: prior conversation as context block + latest message
    history_text = ""
    for turn in conversation_history[-10:]:  # last 10 turns for context
        role_label = "Client" if turn["role"] == "user" else "You (Twin)"
        history_text += f"{role_label}: {turn['content']}\n\n"

    if history_text:
        user_message_with_context = f"Conversation so far:\n{history_text}\nClient: {user_message}"
    else:
        user_message_with_context = f"Client: {user_message}"

    harness = AgentHarness(llm_client, name="persona", system_prompt=system_prompt, mode="text")
    return harness.run(user_message_with_context)
