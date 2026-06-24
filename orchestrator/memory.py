"""
orchestrator/memory.py — MemoryStore for checkpoint and trace persistence via SQLite.

Uses the existing db.py connection pattern. Provides:
- Checkpoint save/load for resume-after-failure
- Trace event append/query for observability
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

# Keep this in sync with db.py so checkpoints and proposals live in the same DB.
DB_PATH = os.getenv("DB_PATH", "data/pitchtwin.db")

_SCHEMA = """
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
"""


def _get_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Idempotently ensure the workflow tables exist so the store is usable
    # standalone (tests, CLI) even if db.init_db() has not been called.
    conn.executescript(_SCHEMA)
    return conn


def _row_to_checkpoint(row) -> dict:
    return {
        "proposal_id": row["proposal_id"],
        "trace_id": row["trace_id"],
        "node_id": row["node_id"],
        "phase": row["phase"],
        "input_data": json.loads(row["input_data"]),
        "output_data": json.loads(row["output_data"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


class MemoryStore:
    def save_checkpoint(self, checkpoint: dict) -> None:
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO workflow_checkpoints
                   (proposal_id, trace_id, node_id, phase, input_data, output_data, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint["proposal_id"],
                    checkpoint["trace_id"],
                    checkpoint["node_id"],
                    checkpoint["phase"],
                    json.dumps(checkpoint["input_data"]),
                    json.dumps(checkpoint["output_data"]),
                    checkpoint["status"],
                    checkpoint.get("created_at", datetime.utcnow().isoformat()),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_latest_checkpoint(self, proposal_id: str) -> dict | None:
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT * FROM workflow_checkpoints
                   WHERE proposal_id=? ORDER BY created_at DESC LIMIT 1""",
                (proposal_id,),
            ).fetchone()
            return _row_to_checkpoint(row) if row else None
        finally:
            conn.close()

    def get_latest_in_progress(self, proposal_id: str) -> dict | None:
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT * FROM workflow_checkpoints
                   WHERE proposal_id=? AND status='in_progress'
                   ORDER BY created_at DESC LIMIT 1""",
                (proposal_id,),
            ).fetchone()
            return _row_to_checkpoint(row) if row else None
        finally:
            conn.close()

    def get_latest_completed_node(self, proposal_id: str, trace_id: str) -> dict | None:
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT * FROM workflow_checkpoints
                   WHERE proposal_id=? AND trace_id=? AND status='completed'
                   ORDER BY created_at DESC LIMIT 1""",
                (proposal_id, trace_id),
            ).fetchone()
            return _row_to_checkpoint(row) if row else None
        finally:
            conn.close()

    def get_completed_checkpoints(self, proposal_id: str, trace_id: str) -> list[dict]:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM workflow_checkpoints
                   WHERE proposal_id=? AND trace_id=? AND status='completed'""",
                (proposal_id, trace_id),
            ).fetchall()
            return [_row_to_checkpoint(row) for row in rows]
        finally:
            conn.close()

    def save_trace(self, trace: dict) -> None:
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT INTO execution_traces
                   (trace_id, node_id, event, timestamp, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    trace["trace_id"],
                    trace["node_id"],
                    trace["event"],
                    trace["timestamp"],
                    trace.get("duration_ms"),
                    trace.get("error"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_trace(self, trace_id: str) -> list[dict]:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM execution_traces
                   WHERE trace_id=? ORDER BY timestamp""",
                (trace_id,),
            ).fetchall()
            return [
                {
                    "trace_id": row["trace_id"],
                    "node_id": row["node_id"],
                    "event": row["event"],
                    "timestamp": row["timestamp"],
                    "duration_ms": row["duration_ms"],
                    "error": row["error"],
                }
                for row in rows
            ]
        finally:
            conn.close()