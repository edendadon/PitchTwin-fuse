"""
PitchTwin — Flask Application
Your CV, came to life.

Routes:
  GET  /                          — consultant dashboard
  POST /profile/new               — create consultant profile
  POST /profile/extract-cv        — extract text from uploaded CV file (PDF/DOCX/TXT)
  POST /proposal/new              — trigger full pipeline
  GET  /proposal/<id>             — view proposal package
  GET  /twin/<session_id>         — client twin chat interface
  POST /twin/<session_id>/message — client sends message
  POST /twin/<session_id>/end     — end session, trigger debrief
  GET  /debrief/<proposal_id>     — view debrief report
  POST /demo/seed                 — load demo data for quick demo
"""

import os
import uuid
import json
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

import logfire

from observability import configure_logfire, tag_user_on_current_span

# Configure tracing before instrumenting anything else.
configure_logfire()

import db
from models import ConsultantProfile
from orchestrator import (
    run_proposal_pipeline,
    create_twin_session,
    handle_twin_message,
    end_twin_session
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "pitchtwin-dev-secret")

# One span per incoming request, across every route.
logfire.instrument_flask(app)


@app.before_request
def setup():
    db.init_db()
    # Tag the request span with the static Logfire user (if configured).
    tag_user_on_current_span()


# -----------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------

@app.route("/")
def dashboard():
    profiles = db.list_profiles()
    proposals = db.list_proposals()

    # Attach profile name to each proposal
    profile_map = {p.id: p.name for p in profiles}
    return render_template(
        "dashboard.html",
        profiles=profiles,
        proposals=proposals,
        profile_map=profile_map
    )


# -----------------------------------------------------------------------
# Consultant Profile
# -----------------------------------------------------------------------

@app.route("/profile/new", methods=["GET", "POST"])
def new_profile():
    if request.method == "GET":
        return render_template("new_profile.html")

    name = request.form.get("name", "").strip()
    raw_profile = request.form.get("raw_profile", "").strip()

    if not name or not raw_profile:
        return render_template("new_profile.html", error="Name and profile text are required.")

    profile = ConsultantProfile(
        id=str(uuid.uuid4()),
        name=name,
        raw_profile=raw_profile,
        structured={},
        created_at=datetime.utcnow().isoformat()
    )
    db.save_profile(profile)
    return redirect(url_for("dashboard"))


@app.route("/profile/extract-cv", methods=["POST"])
def extract_cv():
    """Extract plain text from an uploaded CV file (PDF, DOCX, or TXT)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext not in ("pdf", "docx", "txt"):
        return jsonify({"error": "Unsupported file type. Use PDF, DOCX, or TXT."}), 400

    try:
        if ext == "txt":
            text = file.read().decode("utf-8", errors="ignore")

        elif ext == "pdf":
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(file.read()))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages)

        elif ext == "docx":
            from docx import Document
            import io
            doc = Document(io.BytesIO(file.read()))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)

        text = text.strip()
        if not text:
            return jsonify({"error": "Could not extract any text from this file. Try copy-pasting instead."}), 422

        # Best-effort: grab first non-empty line as candidate name
        first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
        # Heuristic: likely a name if it's 2-4 words, no numbers
        words = first_line.split()
        detected_name = first_line if 2 <= len(words) <= 4 and first_line.replace(" ", "").isalpha() else ""

        return jsonify({
            "text": text,
            "char_count": len(text),
            "detected_name": detected_name
        })

    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500


# -----------------------------------------------------------------------
# Proposal Pipeline
# -----------------------------------------------------------------------

@app.route("/proposal/new", methods=["GET", "POST"])
def new_proposal():
    if request.method == "GET":
        profiles = db.list_profiles()
        return render_template("new_proposal.html", profiles=profiles)

    consultant_id = request.form.get("consultant_id", "").strip()
    company_name = request.form.get("company_name", "").strip()
    client_brief = request.form.get("client_brief", "").strip()

    if not all([consultant_id, company_name, client_brief]):
        profiles = db.list_profiles()
        return render_template("new_proposal.html", profiles=profiles, error="All fields are required.")

    # Run pipeline synchronously for demo (switch to background thread for prod)
    try:
        proposal = run_proposal_pipeline(consultant_id, client_brief, company_name)
        # Auto-create twin session
        twin_session = create_twin_session(proposal.id)
        return redirect(url_for("view_proposal", proposal_id=proposal.id))
    except Exception as e:
        profiles = db.list_profiles()
        return render_template("new_proposal.html", profiles=profiles, error=str(e))


@app.route("/proposal/<proposal_id>")
def view_proposal(proposal_id):
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        return "Proposal not found", 404

    profile = db.get_profile(proposal.consultant_id)
    twin_session = db.get_session_by_proposal(proposal_id)

    gap_data = {}
    if proposal.gap_analysis:
        try:
            gap_data = json.loads(proposal.gap_analysis)
        except Exception:
            gap_data = {"raw": proposal.gap_analysis}

    return render_template(
        "proposal.html",
        proposal=proposal,
        profile=profile,
        gap_data=gap_data,
        twin_session=twin_session
    )


# -----------------------------------------------------------------------
# Twin Chat (Client-facing)
# -----------------------------------------------------------------------

@app.route("/twin/<session_id>")
def twin_chat(session_id):
    sess = db.get_session(session_id)
    if not sess:
        return "Session not found", 404

    proposal = db.get_proposal(sess.proposal_id)
    profile = db.get_profile(proposal.consultant_id) if proposal else None

    return render_template(
        "twin_chat.html",
        session=sess,
        proposal=proposal,
        profile=profile
    )


@app.route("/twin/<session_id>/message", methods=["POST"])
def twin_message(session_id):
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    try:
        response = handle_twin_message(session_id, user_message)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/twin/<session_id>/end", methods=["POST"])
def end_session(session_id):
    try:
        debrief = end_twin_session(session_id)
        sess = db.get_session(session_id)
        return jsonify({"status": "ended", "proposal_id": sess.proposal_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------------------
# Debrief (Consultant-facing)
# -----------------------------------------------------------------------

@app.route("/debrief/<proposal_id>")
def view_debrief(proposal_id):
    proposal = db.get_proposal(proposal_id)
    if not proposal:
        return "Proposal not found", 404

    sess = db.get_session_by_proposal(proposal_id)
    if not sess or not sess.debrief:
        return render_template("debrief.html", proposal=proposal, sess=sess, debrief_data=None)

    debrief_data = {}
    try:
        debrief_data = json.loads(sess.debrief)
    except Exception:
        debrief_data = {"raw": sess.debrief}

    return render_template("debrief.html", proposal=proposal, sess=sess, debrief_data=debrief_data)


# -----------------------------------------------------------------------
# Demo Seed
# -----------------------------------------------------------------------

@app.route("/demo/seed", methods=["POST"])
def demo_seed():
    """Load demo consultant profile and brief for quick demo runs."""
    demo_profile_path = os.path.join(os.path.dirname(__file__), "data", "sample_profile.json")
    demo_brief_path = os.path.join(os.path.dirname(__file__), "data", "sample_brief.json")

    try:
        with open(demo_profile_path) as f:
            sample_profile = json.load(f)
        with open(demo_brief_path) as f:
            sample_brief = json.load(f)
    except FileNotFoundError as e:
        return jsonify({"error": f"Demo data not found: {e}"}), 500

    # Check if demo profile already exists
    existing = [p for p in db.list_profiles() if p.name == sample_profile["name"]]
    if existing:
        profile = existing[0]
    else:
        profile = ConsultantProfile(
            id=str(uuid.uuid4()),
            name=sample_profile["name"],
            raw_profile=sample_profile["raw_profile"],
            structured={},
            created_at=datetime.utcnow().isoformat()
        )
        db.save_profile(profile)

    return jsonify({
        "profile_id": profile.id,
        "profile_name": profile.name,
        "company_name": sample_brief["company_name"],
        "client_brief": sample_brief["client_brief"]
    })


# -----------------------------------------------------------------------
# API: Status check
# -----------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "PitchTwin"})


if __name__ == "__main__":
    db.init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
