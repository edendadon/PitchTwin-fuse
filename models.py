"""
Data models — dataclasses mirroring SQLite schema.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ConsultantProfile:
    id: str
    name: str
    raw_profile: str
    structured: Dict[str, Any] = field(default_factory=dict)  # skills, experience, projects, tone_markers
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Proposal:
    id: str
    consultant_id: str
    client_brief: str
    company_name: str
    tailored_cv: str = ""
    bio: str = ""
    talking_points: List[str] = field(default_factory=list)
    gap_analysis: str = ""
    relevance_map: Dict[str, Any] = field(default_factory=dict)
    client_context: Dict[str, Any] = field(default_factory=dict)
    status: str = "generating"  # generating | awaiting_approval | ready
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TwinSession:
    id: str
    proposal_id: str
    transcript: List[Dict[str, str]] = field(default_factory=list)  # [{role, content, timestamp}]
    debrief: str = ""
    status: str = "active"  # active | ended
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
