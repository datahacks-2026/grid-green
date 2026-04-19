"""Gemini wrapper that turns a retrieved alternative into NL reasoning.

Gracefully degrades to a deterministic templated explanation when the
GEMINI_API_KEY is missing or the call fails — so the demo never breaks.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

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


def explain_alternative(
    *,
    original_model: str,
    alternative_model: str,
    carbon_saved_pct: int,
    performance_retained_pct: int,
    citation: str,
) -> str:
    """Return a 1-2 sentence developer-facing justification."""
    prompt = (
        "You are a carbon-aware ML copilot. In 2 short sentences, explain to a "
        "developer why swapping one model for another is a good trade-off. "
        "Be concrete and cite the source.\n\n"
        f"Original model: {original_model}\n"
        f"Alternative: {alternative_model}\n"
        f"Carbon savings: {carbon_saved_pct}%\n"
        f"Performance retained: {performance_retained_pct}%\n"
        f"Source: {citation}\n"
    )

    client = _get_client()
    if client is None:
        return _fallback(
            alternative_model, carbon_saved_pct, performance_retained_pct, citation
        )

    try:
        resp = client.generate_content(prompt)
        text: Optional[str] = getattr(resp, "text", None)
        if text:
            return text.strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("Gemini call failed, falling back: %s", exc)

    return _fallback(
        alternative_model, carbon_saved_pct, performance_retained_pct, citation
    )


def _fallback(
    alternative_model: str,
    carbon_saved_pct: int,
    performance_retained_pct: int,
    citation: str,
) -> str:
    return (
        f"{alternative_model} retains {performance_retained_pct}% of the "
        f"original's task performance while cutting compute carbon by "
        f"{carbon_saved_pct}%. Source: {citation}"
    )


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
