"""
Observability — Logfire tracing setup.

Call configure_logfire() once at startup. Tracing is exported only when a
LOGFIRE_TOKEN is present (`send_to_logfire="if-token-present"`), so local runs
without a token still work — spans are created but go nowhere.

A static LOGFIRE_USER (if set) is attached as a baseline `user` attribute on
every request span; per-request work additionally tags the consultant it is
about (see orchestrator spans).
"""

import contextlib
import os

import logfire

LOGFIRE_USER = os.getenv("LOGFIRE_USER", "")

_configured = False


def agents_only() -> bool:
    """When LOGFIRE_AGENTS_ONLY is set, trace only agent calls.

    Framework spans (Flask requests, orchestrator phases, raw LLM-client spans)
    are suppressed so Logfire shows a single clean span per agent invocation.
    """
    return os.getenv("LOGFIRE_AGENTS_ONLY", "").strip().lower() in ("1", "true", "yes", "on")


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


def agent_span(name: str, **attrs):
    """Span for a single agent call. No-op when Logfire isn't configured.

    This is the one span that survives `LOGFIRE_AGENTS_ONLY` mode.
    """
    if not _configured:
        return contextlib.nullcontext()
    return logfire.span("agent: {agent_name}", agent_name=name, **attrs)


def framework_span(msg_template: str, **attrs):
    """Span for framework/infra work (orchestrator phases, raw provider calls).

    No-op when Logfire isn't configured OR when `agents_only()` is on — so these
    spans disappear in agents-only mode.
    """
    if not _configured or agents_only():
        return contextlib.nullcontext()
    return logfire.span(msg_template, **attrs)


def tag_user_on_current_span() -> None:
    """Attach the static LOGFIRE_USER to the active span, if configured."""
    if not LOGFIRE_USER:
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    if span is not None:
        span.set_attribute("user", LOGFIRE_USER)
