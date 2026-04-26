"""POST /api/analyze_repo — fetch a GitHub repo and run greener-model suggestions across it.

Sister endpoint to `POST /api/suggest_greener` which only inspects a single
pasted snippet. This one downloads the repo's zipball, extracts `.py` and
`.ipynb` files, runs the broadened model detector against each, and returns
per-file suggestions plus a small aggregate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models.schemas import GreenerSuggestion, Region
from app.services import gemini_service, rag
from app.services.repo_fetcher import (
    RepoFetchError,
    RepoFile,
    extract_python_from_notebook,
    fetch_repo_files,
    parse_github_url,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["model-intelligence"])


class AnalyzeRepoRequest(BaseModel):
    repo_url: str = Field(..., description="https://github.com/owner/repo")
    ref: str | None = Field(default=None, description="Branch / tag / sha (defaults to HEAD).")
    region: Region | None = Field(default=None, description="Optional region for grid-aware reasoning.")
    top_k_per_file: int = Field(default=2, ge=1, le=5)
    max_files_with_hits: int = Field(default=25, ge=1, le=100)


class FileSuggestions(BaseModel):
    path: str
    suggestions: List[GreenerSuggestion]


class AnalyzeRepoResponse(BaseModel):
    repo_url: str
    owner: str
    repo: str
    files_scanned: int
    files_with_hits: int
    total_suggestions: int
    files: List[FileSuggestions]
    # Concatenated `.py` / notebook code (capped) for POST /api/estimate_carbon
    # so the UI can run the same “when to train” grid + forecast analysis as code mode.
    aggregated_code_for_estimate: str
    aggregate_file_count: int
    aggregate_truncated: bool


@dataclass(frozen=True)
class _AggregateResult:
    text: str
    file_count: int
    truncated: bool


def _aggregate_repo_sources(
    files: list[RepoFile],
    *,
    max_code_bytes: int,
) -> _AggregateResult:
    """Join repo sources with path markers; UTF-8 byte cap matches estimate_carbon."""
    parts: List[str] = []
    byte_len = 0
    count = 0
    truncated = False
    for f in files:
        if not isinstance(f, RepoFile):
            continue
        raw = f.content
        if f.path.lower().endswith(".ipynb"):
            raw = extract_python_from_notebook(raw)
        header = f"\n\n# --- repo:{f.path} ---\n"
        piece = header + raw
        enc = piece.encode("utf-8")
        if byte_len + len(enc) <= max_code_bytes:
            parts.append(piece)
            byte_len += len(enc)
            count += 1
            continue
        remaining = max_code_bytes - byte_len
        if remaining <= 0:
            truncated = True
            break
        parts.append(enc[:remaining].decode("utf-8", errors="ignore"))
        truncated = True
        count += 1  # partial file still counts toward "used for estimate"
        break
    return _AggregateResult(text="".join(parts), file_count=count, truncated=truncated)


@router.post("/analyze_repo", response_model=AnalyzeRepoResponse)
def analyze_repo(payload: AnalyzeRepoRequest) -> AnalyzeRepoResponse:
    settings = get_settings()
    try:
        owner, repo = parse_github_url(payload.repo_url)
    except RepoFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        files = fetch_repo_files(payload.repo_url, ref=payload.ref)
    except RepoFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("repo fetch crashed")
        raise HTTPException(status_code=502, detail=f"Could not fetch repo: {exc}") from exc

    agg = _aggregate_repo_sources(files, max_code_bytes=settings.max_code_bytes)

    ctx = (
        rag.SuggestContext(region=payload.region) if payload.region else None
    )

    out: List[FileSuggestions] = []
    total = 0
    # Repo scans fan out over many files; forcing local RAG avoids opening a
    # Snowflake connection per file which can cause slow scans/timeouts.
    previous_backend = os.environ.get("GRIDGREEN_RAG_BACKEND")
    os.environ["GRIDGREEN_RAG_BACKEND"] = "local"
    try:
        for f in files:
            code = f.content
            if f.path.lower().endswith(".ipynb"):
                code = extract_python_from_notebook(code)
            if len(code.encode("utf-8")) > settings.max_code_bytes:
                # Truncate rather than skip — long files often still have valuable
                # model loads in their first few hundred KB.
                code = code.encode("utf-8")[: settings.max_code_bytes].decode(
                    "utf-8", errors="ignore"
                )
            raw = rag.suggest(code, top_k=payload.top_k_per_file, context=ctx)
            if not raw:
                continue
            suggestions = [
                GreenerSuggestion(
                    line=s.line,
                    original_snippet=s.original_snippet,
                    alternative_snippet=s.alternative_snippet,
                    carbon_saved_pct=s.carbon_saved_pct,
                    performance_retained_pct=s.performance_retained_pct,
                    citation=s.citation,
                    # Skip the Gemini polish per-suggestion to keep repo scans
                    # fast — the raw RAG reasoning already cites numbers.
                    reasoning=s.reasoning,
                )
                for s in raw
            ]
            out.append(FileSuggestions(path=f.path, suggestions=suggestions))
            total += len(suggestions)
            if len(out) >= payload.max_files_with_hits:
                break
    finally:
        if previous_backend is None:
            os.environ.pop("GRIDGREEN_RAG_BACKEND", None)
        else:
            os.environ["GRIDGREEN_RAG_BACKEND"] = previous_backend

    # Polish only the *first* suggestion per file with Gemini if available —
    # bounded LLM cost, still demonstrates the integration.
    if out:
        first = out[0].suggestions[0]
        first.reasoning = gemini_service.polish_reasoning_paragraph(first.reasoning)

    return AnalyzeRepoResponse(
        repo_url=payload.repo_url,
        owner=owner,
        repo=repo,
        files_scanned=len(files),
        files_with_hits=len(out),
        total_suggestions=total,
        files=out,
        aggregated_code_for_estimate=agg.text,
        aggregate_file_count=agg.file_count,
        aggregate_truncated=agg.truncated,
    )
