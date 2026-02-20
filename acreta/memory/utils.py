"""Shared DSPy helpers used by memory extraction and trace summarization pipelines."""

from __future__ import annotations

import os
from typing import Any

import dspy
from dotenv import load_dotenv
from openrouter import OpenRouter

from acreta.config.logging import logger


def configure_dspy_lm() -> dspy.LM:
    """Configure DSPy LM from environment for either ollama or openrouter."""
    load_dotenv()
    provider = str(os.environ.get("ACRETA_DSPY_PROVIDER", "ollama") or "ollama").strip().lower()
    logger.info(f"Configuring DSPy LM for provider: {provider}")

    if provider == "ollama":
        ollama_api_base = os.environ.get("ACRETA_DSPY_OLLAMA_API_BASE", "http://127.0.0.1:11434")
        ollama_model = os.environ.get("ACRETA_DSPY_OLLAMA_MODEL", "qwen3:8b")
        logger.info(f"Configuring DSPy LM for ollama: {ollama_model}")

        lm = dspy.LM(
            f"ollama_chat/{ollama_model}",
            api_base=ollama_api_base,
            api_key="ollama",
            cache=False,
        )
        dspy.configure(lm=lm)
        return lm

    if provider == "openrouter":
        api_key = str(os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when ACRETA_DSPY_PROVIDER=openrouter")

        http_referer = str(os.environ.get("OPENROUTER_HTTP_REFERER") or "").strip() or None
        x_title = str(os.environ.get("OPENROUTER_X_TITLE") or "").strip() or None
        OpenRouter(api_key=api_key, http_referer=http_referer, x_title=x_title)

        model = str(os.environ.get("ACRETA_DSPY_OPENROUTER_MODEL") or "openai/gpt-4o-mini").strip()
        api_base = str(os.environ.get("ACRETA_DSPY_OPENROUTER_API_BASE") or "https://openrouter.ai/api/v1").strip()
        logger.info(f"Configuring DSPy LM for openrouter: {model}")

        headers: dict[str, str] = {}
        if http_referer:
            headers["HTTP-Referer"] = http_referer
        if x_title:
            headers["X-Title"] = x_title

        lm_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "api_base": api_base,
            "cache": False,
        }
        if headers:
            lm_kwargs["extra_headers"] = headers

        lm = dspy.LM(f"openrouter/{model}", **lm_kwargs)
        dspy.configure(lm=lm)
        return lm

    raise RuntimeError(f"Unsupported ACRETA_DSPY_PROVIDER={provider!r}; use 'ollama' or 'openrouter'")


def env_positive_int(name: str, default: int) -> int:
    """Read a positive integer env value and clamp invalid values to the default."""
    raw = os.environ.get(name, str(default))
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


if __name__ == "__main__":
    """Run direct smoke checks for helper behaviors without mocking."""
    os.environ["ACRETA_UTILS_SMOKE_INT"] = "7"
    assert env_positive_int("ACRETA_UTILS_SMOKE_INT", 3) == 7
    assert env_positive_int("ACRETA_UTILS_MISSING_INT", 3) == 3
