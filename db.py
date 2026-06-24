"""
Database layer — SQLite-backed storage for profiles, proposals, sessions.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from models import ConsultantProfile, Proposal, TwinSession

DB_PATH = os.getenv("DB_PATH", "data/pitchtwin.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS consultant_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                raw_profile TEXT NOT NULL,
                structured TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                consultant_id TEXT NOT NULL,
                client_brief TEXT NOT NULL,
                company_name TEXT NOT NULL,
                tailored_cv TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                talking_points TEXT DEFAULT '[]',
                gap_analysis TEXT DEFAULT '',
                relevance_map TEXT DEFAULT '{}',
                client_context TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY (consultant_id) REFERENCES consultant_profiles(id)
            );

            CREATE TABLE IF NOT EXISTS twin_sessions (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                transcript TEXT DEFAULT '[]',
                debrief TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY (proposal_id) REFERENCES proposals(id)
            );

            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                proposal_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                input_data TEXT NOT NULL,
                output_data TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'in_progress')),
                created_at TEXT NOT NULL,
                PRIMARY KEY (proposal_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS execution_traces (
                trace_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('started', 'completed', 'failed', 'timed_out', 'circuit_breaker')),
                timestamp TEXT NOT NULL,
                duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
                error TEXT,
                PRIMARY KEY (trace_id, node_id, event, timestamp)
            );

            CREATE INDEX IF NOT EXISTS idx_checkpoint_proposal_status ON workflow_checkpoints (proposal_id, status);
            CREATE INDEX IF NOT EXISTS idx_trace_trace_id ON execution_traces (trace_id);
        """)
    print(f"[DB] Initialized at {DB_PATH}")


# --- ConsultantProfile CRUD ---

def save_profile(profile: ConsultantProfile):
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO consultant_profiles (id, name, raw_profile, structured, created_at) VALUES (?,?,?,?,?)",
            (profile.id, profile.name, profile.raw_profile, json.dumps(profile.structured), profile.created_at)
        )


def get_profile(profile_id: str) -> ConsultantProfile | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM consultant_profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        return None
    return ConsultantProfile(
        id=row["id"], name=row["name"], raw_profile=row["raw_profile"],
        structured=json.loads(row["structured"]), created_at=row["created_at"]
    )


def list_profiles() -> list[ConsultantProfile]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM consultant_profiles ORDER BY created_at DESC").fetchall()
    return [ConsultantProfile(
        id=r["id"], name=r["name"], raw_profile=r["raw_profile"],
        structured=json.loads(r["structured"]), created_at=r["created_at"]
    ) for r in rows]


# --- Proposal CRUD ---

def save_proposal(proposal: Proposal):
    with db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO proposals
            (id, consultant_id, client_brief, company_name, tailored_cv, bio,
             talking_points, gap_analysis, relevance_map, client_context, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            proposal.id, proposal.consultant_id, proposal.client_brief, proposal.company_name,
            proposal.tailored_cv, proposal.bio, json.dumps(proposal.talking_points),
            proposal.gap_analysis, json.dumps(proposal.relevance_map),
            json.dumps(proposal.client_context), proposal.status, proposal.created_at
        ))


def get_proposal(proposal_id: str) -> Proposal | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        return None
    return _row_to_proposal(row)


def list_proposals(consultant_id: str = None) -> list[Proposal]:
    with db() as conn:
        if consultant_id:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE consultant_id=? ORDER BY created_at DESC",
                (consultant_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM proposals ORDER BY created_at DESC").fetchall()
    return [_row_to_proposal(r) for r in rows]


def _row_to_proposal(row) -> Proposal:
    return Proposal(
        id=row["id"], consultant_id=row["consultant_id"],
        client_brief=row["client_brief"], company_name=row["company_name"],
        tailored_cv=row["tailored_cv"], bio=row["bio"],
        talking_points=json.loads(row["talking_points"]),
        gap_analysis=row["gap_analysis"],
        relevance_map=json.loads(row["relevance_map"]),
        client_context=json.loads(row["client_context"]),
        status=row["status"], created_at=row["created_at"]
    )


# --- TwinSession CRUD ---

def save_session(session: TwinSession):
    with db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO twin_sessions (id, proposal_id, transcript, debrief, status, created_at)
            VALUES (?,?,?,?,?,?)
        """, (session.id, session.proposal_id, json.dumps(session.transcript),
              session.debrief, session.status, session.created_at))


def get_session(session_id: str) -> TwinSession | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM twin_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return None
    return TwinSession(
        id=row["id"], proposal_id=row["proposal_id"],
        transcript=json.loads(row["transcript"]),
        debrief=row["debrief"], status=row["status"], created_at=row["created_at"]
    )


def get_session_by_proposal(proposal_id: str) -> TwinSession | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM twin_sessions WHERE proposal_id=? ORDER BY created_at DESC LIMIT 1",
            (proposal_id,)
        ).fetchone()
    if not row:
        return None
    return TwinSession(
        id=row["id"], proposal_id=row["proposal_id"],
        transcript=json.loads(row["transcript"]),
        debrief=row["debrief"], status=row["status"], created_at=row["created_at"]
    )


def append_message(session_id: str, role: str, content: str):
    """Append a single message to the session transcript."""
    from datetime import datetime
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    session.transcript.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_session(session)
