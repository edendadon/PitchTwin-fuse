"""
End-to-end integration test: drives PitchTwin through the exact UI flow.

  1. POST /demo/seed                          (load sample profile + brief)
  2. GET  /proposal/new                       (render the form)
  3. POST /proposal/new                       (pipeline starts in background, 302 redirect)
  4. GET  /proposal/<id>/status               (poll until AWAITING_APPROVAL)
  5. POST /proposal/<id>/approve              (consultant approves → creates twin session)
  6. GET  /proposal/<id>                      (render proposal; extract twin link)
  7. GET  /twin/<session_id>                  (open the twin chat)
  8. POST /twin/<session_id>/message {"aws"}  (ask the twin)

Runs with NO real LLM calls and NO API key: conftest patches
orchestrator.LLMClient with FakeLLMClient and points DB_PATH at a temp file.
"""

import re
import time

# str(uuid.uuid4()) is lowercase hex with dashes; accept either case to be safe.
# Anchored inside the href so it matches the clickable anchor, not the
# <code id="twin-link"> block (which embeds the same uuid via host_url).
TWIN_HREF_RE = re.compile(r'href="/twin/([0-9a-fA-F-]{36})"')


def test_full_demo_flow(client):
    # --- STEP 1: Load sample profile & brief --------------------------------
    r = client.post("/demo/seed")
    assert r.status_code == 200
    seed = r.get_json()
    assert seed["profile_name"] == "Alex Rivera"
    assert seed["company_name"] == "NovaPay Financial"
    assert seed["profile_id"]
    assert seed["client_brief"]
    consultant_id = seed["profile_id"]

    # --- STEP 2: Open the "create proposal" form ----------------------------
    r = client.get("/proposal/new")
    assert r.status_code == 200

    # --- STEP 3: Submit proposal (pipeline starts in background thread) -----
    r = client.post(
        "/proposal/new",
        data={
            "consultant_id": consultant_id,
            "company_name": seed["company_name"],
            "client_brief": seed["client_brief"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers["Location"]
    m = re.search(r"/proposal/([^/?#]+)$", location)
    assert m, f"unexpected redirect target: {location!r}"
    proposal_id = m.group(1)

    # Immediately the proposal is in "generating" state
    r = client.get(f"/proposal/{proposal_id}/status")
    assert r.status_code == 200

    # --- STEP 4: Poll status until pipeline completes -----------------------
    for _ in range(60):  # up to ~30 s
        status_data = client.get(f"/proposal/{proposal_id}/status").get_json()
        if status_data["status"] == "AWAITING_APPROVAL":
            break
        assert status_data["status"] not in ("ERROR", "error"), \
            f"Pipeline reported error: {status_data}"
        time.sleep(0.5)
    else:
        raise AssertionError("Pipeline did not reach AWAITING_APPROVAL within 30 s")

    # --- STEP 5: Consultant approves ----------------------------------------
    r = client.post(f"/proposal/{proposal_id}/approve", follow_redirects=False)
    assert r.status_code == 302

    status_data = client.get(f"/proposal/{proposal_id}/status").get_json()
    assert status_data["status"] == "READY"

    # --- STEP 6: View proposal; extract the twin link from rendered HTML ----
    r = client.get(f"/proposal/{proposal_id}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Open Client Twin Link" in html
    href_match = TWIN_HREF_RE.search(html)
    assert href_match, 'twin link href="/twin/<uuid>" not found in proposal page'
    session_id = href_match.group(1)

    # Cross-check: the link the UI renders matches the DB session.
    import db

    db_session = db.get_session_by_proposal(proposal_id)
    assert db_session is not None and db_session.id == session_id

    # --- STEP 7: Open the Client Twin chat page -----------------------------
    r = client.get(f"/twin/{session_id}")
    assert r.status_code == 200

    # --- STEP 8: Ask the twin "aws" -----------------------------------------
    r = client.post(f"/twin/{session_id}/message", json={"message": "aws"})
    assert r.status_code == 200
    body = r.get_json()
    assert "response" in body
    assert isinstance(body["response"], str)
    assert body["response"].strip()
    assert "AWS" in body["response"]
