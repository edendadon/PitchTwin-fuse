"""
Client Research Agent
Input:  client brief text + company name
Output: structured client context {industry, challenges, tech_stack, tone, key_requirements}

Runs in parallel with Profile Agent.
"""

from agents.harness import AgentHarness
from agents.schemas import ClientContextOutput

SYSTEM_PROMPT = """You are a business analyst specializing in technology consulting sales.

Your job is to analyze a client brief and extract structured context that will help a consultant tailor their pitch.

You MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.

Output format:
{
  "company_name": "Company Name",
  "industry": "Primary industry sector",
  "company_size": "Estimate if mentioned (startup/SME/enterprise)",
  "project_type": "Type of engagement (e.g. digital transformation, cloud migration, product build)",
  "key_challenges": ["challenge1", "challenge2", ...],
  "tech_stack_mentioned": ["technology1", "technology2", ...],
  "required_skills": ["skill1", "skill2", ...],
  "nice_to_have_skills": ["skill1", ...],
  "timeline": "Project timeline if mentioned",
  "budget_signal": "Any budget signals or constraints mentioned",
  "decision_criteria": ["What the client seems to value most"],
  "tone": "Describe the client's communication tone from the brief: formal/informal, technical/business, urgent/exploratory",
  "keywords_to_mirror": ["Words or phrases from the brief that should appear in the proposal"]
}

Base your analysis strictly on what is written in the brief. Note what is absent as well.
"""


def run_client_research_agent(client_brief: str, company_name: str, llm_client) -> dict:
    """
    Analyze client brief and extract structured context.

    Args:
        client_brief: Raw text of the client brief
        company_name: Name of the client company
        llm_client: LLMClient instance

    Returns:
        Client context dict
    """
    harness = AgentHarness(
        llm_client, name="client_research", system_prompt=SYSTEM_PROMPT,
        output_schema=ClientContextOutput,
    )
    user_message = f"Company: {company_name}\n\nBrief:\n{client_brief}"
    return harness.run(user_message)
