"""
Pydantic output schemas for every agent.

Used by `AgentHarness` to validate LLM responses (and to drive retry-on-failure).
Schemas are intentionally lenient: a single identifying field is required per agent
so validation has teeth, everything else has a default, and unknown keys are ignored
so a richer-than-expected LLM response still validates. The harness returns the
original parsed dict (not `model_dump()`), so no fields are ever added or dropped.
"""

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProfileOutput(_Base):
    name: str
    title: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    tone_markers: str = ""


class ClientContextOutput(_Base):
    industry: str
    company_name: str = ""
    key_challenges: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    tech_stack_mentioned: list[str] = Field(default_factory=list)
    tone: str = ""
    keywords_to_mirror: list[str] = Field(default_factory=list)


class MatchItem(_Base):
    type: str = ""
    item: str = ""
    relevance_score: int = 0
    reason: str = ""
    suggested_framing: str = ""


class MatchingOutput(_Base):
    top_matches: list[MatchItem]
    secondary_matches: list[MatchItem] = Field(default_factory=list)
    client_tone_match: str = ""
    headline_positioning: str = ""


class WriterOutput(_Base):
    tailored_cv: str
    bio: str = ""
    talking_points: list[str] = Field(default_factory=list)


class GapItem(_Base):
    requirement: str = ""
    gap_type: str = ""
    severity: str = ""
    description: str = ""
    framing_suggestion: str = ""
    mitigation: str = ""


class GapAnalysisOutput(_Base):
    gaps: list[GapItem] = Field(default_factory=list)
    overall_fit_score: int
    overall_fit_summary: str = ""
    strengths_to_lead_with: list[str] = Field(default_factory=list)


class DebriefOutput(_Base):
    session_summary: str
    topics_explored: list[dict] = Field(default_factory=list)
    apparent_priorities: list[str] = Field(default_factory=list)
    concerns_or_hesitations: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    questions_asked: list[str] = Field(default_factory=list)
    recommended_talking_points: list[str] = Field(default_factory=list)
    overall_engagement_level: str = ""
    red_flags: list[str] = Field(default_factory=list)


class CombinedOutput(_Base):
    relevance_map: dict = Field(default_factory=dict)
    tailored_cv: str
    bio: str = ""
    talking_points: list[str] = Field(default_factory=list)
    gap_analysis: dict = Field(default_factory=dict)
