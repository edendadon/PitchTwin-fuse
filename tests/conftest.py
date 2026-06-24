"""
Shared fixtures for integration tests.

CRITICAL ORDERING: DB_PATH must be set in os.environ BEFORE importing `db` or
`app`, because db.py reads `DB_PATH = os.getenv("DB_PATH", ...)` at module
import time. pytest imports conftest.py before collecting test modules, so
setting it here (at conftest import time) guarantees the correct ordering.
"""

import os
import sys
import tempfile

# Make project-root modules (db, app, orchestrator, agents.*) importable,
# mirroring the sys.path shim in tests/test_agents.py.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Point the SQLite DB at a throwaway temp file BEFORE importing db/app.
# Use a real temp directory: db.get_connection() calls
# os.makedirs(os.path.dirname(DB_PATH)), which needs a non-empty dirname.
_TMP_DIR = tempfile.mkdtemp(prefix="pitchtwin-test-")
os.environ["DB_PATH"] = os.path.join(_TMP_DIR, "test_pitchtwin.db")

# Keep everything offline: no real LLM provider, no logfire export.
for _key in ("LITELLM_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "LOGFIRE_TOKEN"):
    os.environ.pop(_key, None)
# Force logfire offline even if local `logfire auth` credentials exist, so the
# test never reaches the network regardless of the developer's machine.
os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"

import pytest  # noqa: E402

import app as app_module  # noqa: E402  (must come after the env setup above)


class FakeLLMClient:
    """
    Drop-in replacement for llm_client.LLMClient used by the orchestrator.

    Dispatch mirrors tests/test_agents.py: lowercase the system prompt and
    match a unique phrase. Covers every prompt the live proposal + twin flow
    hits: profile, client research, combined (match + write + gap), persona.
    """

    def __init__(self, *args, **kwargs):
        # The real __init__ builds a provider client + instruments logfire;
        # the fake must be inert.
        self._tracker = None

    def set_tracker(self, tracker):
        # Mirror the real LLMClient contract so the orchestrator can wire usage
        # capture in tests exactly as it does in production.
        self._tracker = tracker

    def _emit_fake_usage(self):
        # Record deterministic, non-zero usage attributed to whatever DAG node
        # is current on this thread, so the offline pipeline produces a real
        # proposal.usage blob (per-node tokens/cost) without any network call.
        if self._tracker is None:
            return
        from token_tracking import CallUsage, estimate_cost

        prompt, completion = 1000, 500
        self._tracker.record_usage(
            CallUsage(
                "fake-model",
                prompt,
                completion,
                prompt + completion,
                estimate_cost("fake-model", prompt, completion),
            )
        )

    def call(self, system_prompt, user_message, retries=3):
        self._emit_fake_usage()
        sp = system_prompt.lower()
        # persona_agent.build_system_prompt embeds "CRITICAL RULES" + name.
        # orchestrator calls .call() then .strip(), so return a real str.
        if "critical rules" in sp or "digital twin" in sp:
            return (
                "Yes — AWS is core to my background. I led a 14-month cloud "
                "migration moving 60+ legacy systems to AWS for a Tier-1 bank, "
                "and I hold the AWS Solutions Architect - Professional cert. "
                "Happy to go deeper on the target-state architecture for NovaPay."
            )
        return "I can speak to the experience listed in my profile."

    def call_json(self, system_prompt, user_message):
        self._emit_fake_usage()
        sp = system_prompt.lower()

        # Profile Agent
        if "professional profiler" in sp:
            return {
                "name": "Alex Rivera",
                "title": "Senior Technology Consultant",
                "summary": "Senior consultant; cloud migration and microservices.",
                "skills": ["AWS", "Microservices", "Python", "Kafka"],
                "experience": [
                    {
                        "company": "Tikal Tech",
                        "role": "Senior Consultant",
                        "duration": "2020-Present",
                        "description": "Led AWS cloud migration for a Tier-1 bank.",
                        "technologies": ["AWS", "Microservices"],
                        "achievements": ["Reduced infra cost 35%"],
                    }
                ],
                "projects": [
                    {
                        "name": "Bank CloudShift",
                        "client_or_context": "Tier-1 bank",
                        "description": "Full cloud migration to AWS.",
                        "technologies": ["AWS"],
                        "outcomes": "On time, 8% under budget",
                    }
                ],
                "education": [
                    {"degree": "B.Sc. CS", "institution": "Tel Aviv University", "year": "2015"}
                ],
                "certifications": ["AWS Solutions Architect - Professional", "TOGAF 9"],
                "tone_markers": "Direct and pragmatic; uses concrete metrics.",
            }

        # Client Research Agent
        if "consulting sales" in sp:
            return {
                "company_name": "NovaPay Financial",
                "industry": "FinTech / Payments",
                "company_size": "SME (400 employees)",
                "project_type": "Monolith-to-microservices migration on AWS",
                "key_challenges": ["Legacy Java monolith", "PCI-DSS compliance"],
                "tech_stack_mentioned": ["AWS", "Java", "Kafka"],
                "required_skills": ["AWS", "Microservices", "Payments domain"],
                "nice_to_have_skills": ["PCI-DSS", "Kafka", "Fintech"],
                "timeline": "Q3 2026, 6 months",
                "budget_signal": "Quality over cost",
                "decision_criteria": ["Directness", "Concrete outcomes"],
                "tone": "Direct, fast-moving, technical",
                "keywords_to_mirror": ["AWS", "microservices", "PCI-DSS", "payments"],
            }

        # Combined Agent (match + write + gap) — NOT covered by the old mock.
        if "proposal specialist" in sp:
            return {
                "relevance_map": {
                    "top_matches": [
                        {
                            "type": "experience",
                            "item": "AWS cloud migration for Tier-1 bank",
                            "relevance_score": 9,
                            "reason": "Directly matches AWS + migration need",
                            "suggested_framing": "Lead with the bank migration.",
                        }
                    ],
                    "secondary_matches": [],
                    "client_tone_match": "Be direct, use metrics, skip fluff.",
                    "headline_positioning": "Proven AWS migration lead for payments.",
                },
                "tailored_cv": "# Alex Rivera\n\nSenior consultant — AWS migrations.",
                "bio": (
                    "Alex Rivera is a senior technology consultant focused on "
                    "AWS migrations for financial services clients."
                ),
                # MUST be a list: db.save_proposal json.dumps it and
                # proposal.html iterates it.
                "talking_points": [
                    "Led a 14-month AWS migration of 60+ systems for a Tier-1 bank.",
                    "Cut infrastructure costs by 35% post-migration.",
                    "Built real-time fraud detection at 2M+ tx/day, <100ms latency.",
                    "Comfortable presenting to both engineers and the C-suite.",
                    "What does NovaPay see as the riskiest module to migrate first?",
                ],
                "gap_analysis": {
                    "gaps": [
                        {
                            "requirement": "PCI-DSS compliance",
                            "gap_type": "limited_experience",
                            "severity": "low",
                            "description": "Compliance adjacent, not a named cert.",
                            "framing_suggestion": "Cite regulated-bank delivery.",
                            "mitigation": "Worked under banking compliance regimes.",
                        }
                    ],
                    "overall_fit_score": 9,
                    "overall_fit_summary": "Strong fit: AWS + payments + migration.",
                    "strengths_to_lead_with": ["AWS migration", "Payments domain"],
                },
            }

        # Defensive default; should not be reached in this flow.
        return {"result": "mock"}


@pytest.fixture
def fake_llm_cls():
    return FakeLLMClient


@pytest.fixture
def client(mocker, fake_llm_cls):
    """
    Flask test client with orchestrator.LLMClient patched to FakeLLMClient.

    Patch target is orchestrator.LLMClient because orchestrator.py does
    `from llm_client import LLMClient`, binding the name into the orchestrator
    module namespace; the pipeline + twin paths construct it via that name.
    """
    mocker.patch("orchestrator.LLMClient", fake_llm_cls)
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """
    Give every test a fresh, schema-initialized SQLite database.

    The workflow-engine tests instantiate MemoryStore() directly and reuse the
    same proposal_id across tests, so a shared DB would cross-contaminate
    checkpoints/traces. This points both the app DB layer (db.DB_PATH) and the
    orchestrator store (orchestrator.memory.DB_PATH) at an isolated temp file per
    test and creates the full schema (proposals, checkpoints, traces, ...).
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    import db as db_module
    import orchestrator.memory as mem_module

    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(mem_module, "DB_PATH", db_path)
    db_module.init_db()

    yield db_path

    os.unlink(db_path)
