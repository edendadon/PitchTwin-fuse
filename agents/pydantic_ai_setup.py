"""Pydantic AI model factory — creates a LiteLLM-backed model from env vars."""

import os
from dotenv import load_dotenv

load_dotenv()

LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://litellm.tikalk.dev/v1")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "kimi-k2.5")


def create_model():
    """Return a pydantic-ai OpenAIChatModel backed by our LiteLLM proxy."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.litellm import LiteLLMProvider
    return OpenAIChatModel(
        LITELLM_MODEL,
        provider=LiteLLMProvider(
            api_base=LITELLM_BASE_URL,
            api_key=LITELLM_API_KEY,
        ),
    )
