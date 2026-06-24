"""
LLM Client — wraps Gemini, Groq, and LiteLLM proxy.
All agents call this; swap provider via LLM_PROVIDER env var.
"""

import os
import time
import json
from dotenv import load_dotenv

import logfire

from token_tracking import CallUsage, estimate_cost

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "litellm")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://litellm.tikalk.dev/v1")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "kimi-k2.5")


class LLMClient:
    def __init__(self, provider: str = None):
        self.provider = provider or LLM_PROVIDER
        # Optional usage aggregator, injected by the orchestrator via
        # set_tracker(). Duck-typed: record_usage(CallUsage) + record_guardrail(str).
        # Kept decoupled so the client has no hard dependency on the tracker.
        self._tracker = None
        self._init_client()

    def set_tracker(self, tracker) -> None:
        """Attach a usage tracker (UsageTracker-like) to capture tokens/cost."""
        self._tracker = tracker

    def _emit_usage(self, model: str, response) -> None:
        """Extract token usage from a provider response and record it.

        Best-effort and guarded: a missing tracker or an unexpected response
        shape must never break the LLM call. Handles the OpenAI/Groq shape
        (``response.usage.*``) and the Gemini shape (``response.usage_metadata.*``).
        """
        if self._tracker is None:
            return
        try:
            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt = getattr(usage, "prompt_tokens", 0) or 0
                completion = getattr(usage, "completion_tokens", 0) or 0
                total = getattr(usage, "total_tokens", 0) or (prompt + completion)
            else:
                meta = getattr(response, "usage_metadata", None)  # gemini
                if meta is None:
                    return
                prompt = getattr(meta, "prompt_token_count", 0) or 0
                completion = getattr(meta, "candidates_token_count", 0) or 0
                total = getattr(meta, "total_token_count", 0) or (prompt + completion)
            cost = estimate_cost(model, prompt, completion)
            self._tracker.record_usage(
                CallUsage(model, prompt, completion, total, cost)
            )
        except Exception:
            # Usage capture is observability, never load-bearing.
            pass

    def _emit_guardrail(self, kind: str) -> None:
        """Record a guardrail trigger (e.g. "retry", "json_repair")."""
        if self._tracker is None:
            return
        try:
            self._tracker.record_guardrail(kind)
        except Exception:
            pass

    def _init_client(self):
        # In agents-only mode, skip the raw provider instrumentation so Logfire
        # shows one clean span per agent call (emitted by AgentHarness) instead
        # of low-level HTTP/client spans.
        from observability import agents_only
        instrument = not agents_only()

        if self.provider == "gemini":
            import google.genai as genai
            # Required for prompts/completions to be captured in spans.
            os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
            self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            if instrument:
                logfire.instrument_google_genai()
        elif self.provider == "groq":
            from groq import Groq
            # Groq has no dedicated Logfire integration; calls are wrapped in
            # a manual span in _call_groq instead.
            self._groq_client = Groq(api_key=GROQ_API_KEY)
        elif self.provider == "litellm":
            from openai import OpenAI
            self._litellm_client = OpenAI(
                api_key=LITELLM_API_KEY,
                base_url=LITELLM_BASE_URL
            )
            # litellm proxy speaks the OpenAI protocol, so the OpenAI
            # instrumentation captures these calls.
            if instrument:
                logfire.instrument_openai(self._litellm_client)

    def call(self, system_prompt: str, user_message: str, retries: int = 3) -> str:
        """
        Call LLM with system prompt + user message.
        Returns raw string response.
        Retries up to `retries` times with exponential backoff.
        """
        last_error = None
        for attempt in range(retries):
            try:
                if self.provider == "gemini":
                    return self._call_gemini(system_prompt, user_message)
                elif self.provider == "groq":
                    return self._call_groq(system_prompt, user_message)
                elif self.provider == "litellm":
                    return self._call_litellm(system_prompt, user_message)
                else:
                    raise ValueError(f"Unknown provider: {self.provider}")
            except Exception as e:
                last_error = e
                self._emit_guardrail("retry")
                wait = 2 ** attempt
                print(f"[LLMClient] Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
        raise RuntimeError(f"LLM call failed after {retries} attempts: {last_error}")

    def _call_gemini(self, system_prompt: str, user_message: str) -> str:
        import google.genai.types as types
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
            )
        )
        self._emit_usage("gemini-2.0-flash", response)
        return response.text

    def _call_groq(self, system_prompt: str, user_message: str) -> str:
        model = "llama-3.3-70b-versatile"
        from observability import framework_span
        with framework_span("groq chat completion", model=model):
            response = self._groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
            )
        self._emit_usage(model, response)
        return response.choices[0].message.content

    def _call_litellm(self, system_prompt: str, user_message: str) -> str:
        response = self._litellm_client.chat.completions.create(
            model=LITELLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        self._emit_usage(LITELLM_MODEL, response)
        return response.choices[0].message.content

    def call_stream(self, system_prompt: str, user_message: str):
        """
        Stream LLM response as token chunks.
        Yields string tokens as they arrive from the provider.
        Falls back to yielding the full response as a single chunk on error.
        No retries — streaming is best-effort.
        """
        try:
            if self.provider == "gemini":
                yield from self._stream_gemini(system_prompt, user_message)
            elif self.provider == "groq":
                yield from self._stream_groq(system_prompt, user_message)
            elif self.provider == "litellm":
                yield from self._stream_litellm(system_prompt, user_message)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
        except Exception as e:
            print(f"[LLMClient] Streaming failed, falling back to non-streaming: {e}")
            # Fallback: yield the full response as a single chunk
            yield self.call(system_prompt, user_message)

    def _stream_gemini(self, system_prompt: str, user_message: str):
        import google.genai.types as types
        for chunk in self._gemini_client.models.generate_content_stream(
            model="gemini-2.0-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
            ),
        ):
            if chunk.text:
                yield chunk.text

    def _stream_groq(self, system_prompt: str, user_message: str):
        model = "llama-3.3-70b-versatile"
        from observability import framework_span
        with framework_span("groq chat completion stream", model=model):
            stream = self._groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                stream=True,
            )
            for chunk in stream:
                token = chunk.choices[0].delta.content
                if token is not None:
                    yield token

    def _stream_litellm(self, system_prompt: str, user_message: str):
        stream = self._litellm_client.chat.completions.create(
            model=LITELLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token is not None:
                yield token

    def call_json(self, system_prompt: str, user_message: str) -> dict:
        """
        Call LLM and parse JSON response.
        System prompt should instruct the model to respond with valid JSON only.
        """
        raw = self.call(system_prompt, user_message)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            self._emit_guardrail("json_repair")
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Last resort: try to extract JSON from the response
            self._emit_guardrail("json_repair")
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")
