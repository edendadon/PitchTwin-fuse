"""
Shared pytest fixtures.

The workflow-engine tests instantiate MemoryStore() directly and expect a clean,
schema-initialized SQLite database. This autouse fixture points the store at an
isolated temporary database per test so runs are deterministic and never touch
(or cross-contaminate) the real data/pitchtwin.db.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    # Point both the app DB layer and the orchestrator store at the temp DB.
    import db as db_module
    import orchestrator.memory as mem_module

    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(mem_module, "DB_PATH", db_path)

    # MemoryStore._get_connection() creates the workflow tables on demand; create
    # the full app schema too so pipeline-level code (proposals, profiles) works.
    db_module.init_db()

    yield db_path

    os.unlink(db_path)
