"""
Agent harness — one calling convention for every agent.

See `spec/spec.harness-brainstorm.md` (Option A: a thin harness over
`llm_client.call_json()` / `call()`). It adds, as cross-cutting concerns:

  * output validation against a Pydantic schema, with retry-on-failure
    (the model is re-prompted with the validation error appended);
  * console tracing per call (agent name, latency, retry count, validity);
  * a no-hallucination guardrail that flags skills/technologies in the output
    that are absent from the consultant's profile.

The harness returns the *original* parsed dict (not `model_dump()`), so wrapping
an agent never adds or drops fields — it is a behaviour-preserving migration.
"""

import time

from pydantic import ValidationError


class NoHallucinationGuardrail:
    """
    Flags skills/technologies claimed in agent output that are not present
    anywhere in the consultant's profile (skills, certifications, or the
    technologies listed under experience/projects).
    """

    def __init__(self, profile: dict):
        self.allowed = self._build_vocab(profile or {})

    @staticmethod
    def _build_vocab(profile: dict) -> set:
        vocab: set = set()
        for key in ("skills", "certifications"):
            for s in profile.get(key, []) or []:
                vocab.add(str(s).strip().lower())
        for section in ("experience", "projects"):
            for item in profile.get(section, []) or []:
                if isinstance(item, dict):
                    for tech in item.get("technologies", []) or []:
                        vocab.add(str(tech).strip().lower())
        return vocab

    def check(self, claimed_skills) -> list:
        """Return the claimed skills that are NOT supported by the profile."""
        return [s for s in (claimed_skills or []) if str(s).strip().lower() not in self.allowed]

    def is_grounded(self, claimed_skills) -> bool:
        return not self.check(claimed_skills)


def _trace(name, status, latency_ms, retries, valid, unsupported=0):
    line = (f"[harness] agent={name} status={status} latency_ms={latency_ms} "
            f"retries={retries} output_valid={valid}")
    if unsupported:
        line += f" unsupported_skills={unsupported}"
    print(line)


class AgentHarness:
    """
    Wrap a single agent's LLM call.

    Args:
        llm_client: object exposing ``call_json(system_prompt, user_message)`` and
            ``call(system_prompt, user_message)``.
        name: agent name (used in traces).
        system_prompt: the agent's system prompt.
        output_schema: optional Pydantic model validating the JSON response.
        mode: ``"json"`` (default) parses + validates JSON; ``"text"`` returns the
            raw string response (used by the persona twin).
        max_retries: extra LLM attempts when output validation fails.
    """

    def __init__(self, llm_client, name, system_prompt, *,
                 output_schema=None, mode="json", max_retries=2):
        self.llm = llm_client
        self.name = name
        self.system_prompt = system_prompt
        self.output_schema = output_schema
        self.mode = mode
        self.max_retries = max_retries

    def run(self, user_message, *, ground_against=None, grounded_field="skills"):
        """Execute the agent. Returns a validated dict (json mode) or string (text mode)."""
        start = time.monotonic()
        if self.mode == "text":
            result, retries, valid = self._run_text(user_message), 0, True
        else:
            result, retries, valid = self._run_json(user_message)

        unsupported = 0
        if ground_against is not None and isinstance(result, dict):
            guard = NoHallucinationGuardrail(ground_against)
            flagged = guard.check(result.get(grounded_field, []))
            unsupported = len(flagged)
            if flagged:
                print(f"[harness] guardrail: {self.name} claimed unsupported skill(s): {flagged}")

        latency_ms = int((time.monotonic() - start) * 1000)
        _trace(self.name, "ok", latency_ms, retries, valid, unsupported)
        return result

    def _run_text(self, user_message) -> str:
        return self.llm.call(self.system_prompt, user_message).strip()

    def _run_json(self, user_message):
        msg = user_message
        last_err = None
        parsed = None
        for attempt in range(self.max_retries + 1):
            try:
                parsed = self.llm.call_json(self.system_prompt, msg)
                if self.output_schema is None:
                    return parsed, attempt, True
                self.output_schema.model_validate(parsed)
                return parsed, attempt, True
            except (ValidationError, ValueError) as e:
                last_err = e
                msg = (f"{user_message}\n\nYour previous response was invalid:\n{e}\n"
                       f"Respond again with valid JSON only that matches the required schema.")

        if parsed is None:
            # Never produced parseable JSON across all attempts.
            raise RuntimeError(
                f"[harness] {self.name} failed to produce valid JSON after "
                f"{self.max_retries + 1} attempts: {last_err}"
            )
        # Parseable but never schema-valid: don't crash the pipeline — warn and
        # return the best-effort dict (the orchestrator stays robust for demos).
        print(f"[harness] WARNING: {self.name} output failed validation after "
              f"{self.max_retries + 1} attempts: {last_err}")
        return parsed, self.max_retries, False
