"""Gemini wrapper that turns a retrieved alternative into NL reasoning.

Gracefully degrades to a deterministic templated explanation when the
GEMINI_API_KEY is missing or the call fails — so the demo never breaks.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_MODEL_NAME = "gemini-2.0-flash"
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        _client = genai.GenerativeModel(_MODEL_NAME)
        return _client
    except Exception as exc:  # pragma: no cover
        logger.warning("Gemini init failed, falling back: %s", exc)
        return None


def polish_reasoning_paragraph(text: str) -> str:
    """Tighten corpus + grid narrative into 2–4 sentences when Gemini is available."""
    text = text.strip()
    if not text:
        return text
    client = _get_client()
    if client is None:
        return text
    prompt = (
        "You are GridGreen, a carbon-aware ML copilot. Rewrite the paragraph below "
        "into 2–4 concise sentences for a developer. Preserve every numeric fact "
        "(grams, %, gCO₂/kWh, region codes). Do not invent new numbers.\n\n"
        f"{text}"
    )
    try:
        resp = client.generate_content(prompt)
        out: str | None = getattr(resp, "text", None)
        if out:
            return out.strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("Gemini polish failed, using raw text: %s", exc)
    return text
