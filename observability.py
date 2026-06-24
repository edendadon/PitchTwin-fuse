"""
Observability — Logfire tracing setup.

Call configure_logfire() once at startup. Tracing is exported only when a
LOGFIRE_TOKEN is present (`send_to_logfire="if-token-present"`), so local runs
without a token still work — spans are created but go nowhere.

A static LOGFIRE_USER (if set) is attached as a baseline `user` attribute on
every request span; per-request work additionally tags the consultant it is
about (see orchestrator spans).
"""

import os

import logfire

LOGFIRE_USER = os.getenv("LOGFIRE_USER", "")

_configured = False


def configure_logfire() -> None:
    """Configure Logfire once. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    logfire.configure(
        service_name="pitchtwin",
        # Only ship spans when LOGFIRE_TOKEN is set; otherwise no-op locally.
        send_to_logfire="if-token-present",
    )
    _configured = True


def tag_user_on_current_span() -> None:
    """Attach the static LOGFIRE_USER to the active span, if configured."""
    if not LOGFIRE_USER:
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    if span is not None:
        span.set_attribute("user", LOGFIRE_USER)
