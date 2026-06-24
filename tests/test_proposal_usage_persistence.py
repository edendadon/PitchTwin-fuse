"""
Tests for Proposal token/cost persistence (Slice C):
- init_db() migrates a pre-#6 proposals table (adds trace_id / usage_json).
- An old-schema row reads back with safe defaults.
- A proposal with usage round-trips through save_proposal / get_proposal.
"""

import sqlite3

import db as db_module
from models import Proposal

# A pre-#6 proposals table: exactly today's columns minus trace_id / usage_json.
_OLD_PROPOSALS_SCHEMA = """
CREATE TABLE proposals (
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
    created_at TEXT NOT NULL
);
"""


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(proposals)").fetchall()}
    finally:
        conn.close()


def test_init_db_migrates_old_proposals_table(monkeypatch, tmp_path):
    db_path = str(tmp_path / "old.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    # Simulate a database that predates the token/cost columns.
    conn = sqlite3.connect(db_path)
    conn.executescript(_OLD_PROPOSALS_SCHEMA)
    conn.execute(
        "INSERT INTO proposals (id, consultant_id, client_brief, company_name, created_at) "
        "VALUES (?,?,?,?,?)",
        ("old-1", "c-1", "brief", "Acme", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    assert "trace_id" not in _columns(db_path)  # precondition

    db_module.init_db()  # migration runs here

    cols = _columns(db_path)
    assert "trace_id" in cols
    assert "usage_json" in cols

    # Pre-migration row still loads, with defaulted token/cost fields.
    proposal = db_module.get_proposal("old-1")
    assert proposal is not None
    assert proposal.trace_id == ""
    assert proposal.usage == {}


def test_save_and_get_proposal_round_trips_usage(monkeypatch, tmp_path):
    db_path = str(tmp_path / "new.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()

    proposal = Proposal(
        id="p-1", consultant_id="c-1", client_brief="brief", company_name="Acme"
    )
    proposal.trace_id = "trace-1"
    proposal.usage = {
        "trace_id": "trace-1",
        "duration_seconds": 12.3,
        "total_tokens": 1500,
        "cost_usd": 0.003,
        "nodes": {"profile_agent": {"total_tokens": 500, "guardrail_triggers": []}},
    }
    db_module.save_proposal(proposal)

    loaded = db_module.get_proposal("p-1")
    assert loaded.trace_id == "trace-1"
    assert loaded.usage["total_tokens"] == 1500
    assert loaded.usage["cost_usd"] == 0.003
    assert loaded.usage["nodes"]["profile_agent"]["total_tokens"] == 500
