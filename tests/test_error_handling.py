"""
Regression tests for CodeQL `py/stack-trace-exposure` (alerts #66-69).

Every error-handling branch in app.py must return a *generic* message to the
client and never echo the raw exception (which can carry stack frames, file
paths, or internal state). Each test forces the underlying call to raise an
exception carrying a recognisable secret token, then asserts the token never
reaches the HTTP response body.
"""

import io


SECRET = "INTERNAL_STACKTRACE_TOKEN_DO_NOT_LEAK"


def test_extract_cv_does_not_leak_exception(client, mocker):
    # PdfReader is imported inside the handler (`from pypdf import PdfReader`),
    # so patching the module attribute intercepts it at call time.
    mocker.patch("pypdf.PdfReader", side_effect=RuntimeError(SECRET))
    data = {"file": (io.BytesIO(b"%PDF-1.4 not-a-real-pdf"), "resume.pdf")}

    r = client.post(
        "/profile/extract-cv", data=data, content_type="multipart/form-data"
    )

    assert r.status_code == 500
    assert SECRET not in (r.get_json().get("error") or "")


def test_new_proposal_does_not_leak_exception(client, mocker):
    mocker.patch("app.run_proposal_pipeline", side_effect=RuntimeError(SECRET))

    r = client.post(
        "/proposal/new",
        data={"consultant_id": "x", "company_name": "y", "client_brief": "z"},
    )

    # Handler re-renders the form (HTTP 200) with an error message.
    assert SECRET not in r.get_data(as_text=True)


def test_twin_message_does_not_leak_exception(client, mocker):
    mocker.patch("app.handle_twin_message", side_effect=RuntimeError(SECRET))

    r = client.post("/twin/any-session/message", json={"message": "hello"})

    assert r.status_code == 500
    assert SECRET not in (r.get_json().get("error") or "")


def test_end_session_does_not_leak_exception(client, mocker):
    mocker.patch("app.end_twin_session", side_effect=RuntimeError(SECRET))

    r = client.post("/twin/any-session/end")

    assert r.status_code == 500
    assert SECRET not in (r.get_json().get("error") or "")


def test_demo_seed_does_not_leak_exception(client, mocker):
    # The demo-seed handler catches FileNotFoundError and previously formatted
    # the raw exception (which embeds the absolute filesystem path).
    mocker.patch("builtins.open", side_effect=FileNotFoundError(SECRET))

    r = client.post("/demo/seed")

    assert r.status_code == 500
    assert SECRET not in (r.get_json().get("error") or "")
