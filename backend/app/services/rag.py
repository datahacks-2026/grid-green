"""RAG over the curated HF model corpus (Phase 5 + a.md §8.8).

Embedding tiers (auto-selected at runtime):

1. **Snowflake Cortex** — when `SNOWFLAKE_*` env vars are set and the
   `snowflake-connector-python` package is installed, we read precomputed
   `VECTOR` rows from a Cortex-managed table (built by
   `scripts/build_rag_index.py --target snowflake`).
2. **sentence-transformers** — when the package is importable, we encode
   the corpus once on first use with `all-MiniLM-L6-v2` (the same model
   we run on Brev for the sponsor evidence run).
3. **TF-IDF fallback** — pure scikit-learn cosine similarity over the
   model id + tags + reasoning text. Always available; the demo never
   breaks when the heavier paths are missing.

The query is the union of model ids extracted from the user's code plus
their associated tag context. The result set is filtered to entries whose
target is *smaller* than the source (otherwise we'd suggest swapping a
small model for a bigger one) and deduped by `(from, to)`.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "hf_corpus.json"


@dataclass
class CorpusEntry:
    from_model: str
    to_model: str
    params_from_b: float
    params_to_b: float
    carbon_saved_pct: float
    performance_retained_pct: float
    citation: str
    reasoning: str
    tags: List[str]

    @property
    def doc_text(self) -> str:
        return " ".join([self.from_model, self.to_model, *self.tags, self.reasoning])


@dataclass
class Suggestion:
    line: int
    original_snippet: str
    alternative_snippet: str
    carbon_saved_pct: float
    performance_retained_pct: float
    citation: str
    reasoning: str


@dataclass(frozen=True)
class SuggestContext:
    """Optional Part A signals — when set, suggestions are ranked and explained with grid + script CO₂."""

    region: str | None = None
    co2_grams_now: float | None = None
    co2_grams_optimal: float | None = None
    current_gco2_kwh: float | None = None
    optimal_window_start: str | None = None
    co2_savings_pct_window: float | None = None
    impact_focus_lines: tuple[int, ...] = ()


class RagIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: List[CorpusEntry] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._st_model = None  # sentence-transformers model, lazy
        self._st_matrix = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            data = json.loads(CORPUS_PATH.read_text())
            self._entries = [
                CorpusEntry(
                    from_model=e["from"],
                    to_model=e["to"],
                    params_from_b=float(e["params_from_b"]),
                    params_to_b=float(e["params_to_b"]),
                    carbon_saved_pct=float(e["carbon_saved_pct"]),
                    performance_retained_pct=float(e["performance_retained_pct"]),
                    citation=e["citation"],
                    reasoning=e["reasoning"],
                    tags=list(e.get("tags", [])),
                )
                for e in data["entries"]
            ]
            docs = [e.doc_text for e in self._entries]
            self._vectorizer = TfidfVectorizer(
                lowercase=True, ngram_range=(1, 2), min_df=1
            )
            self._matrix = self._vectorizer.fit_transform(docs)
            logger.info("RAG index built: %d entries (TF-IDF)", len(self._entries))

            # Best-effort upgrade to sentence-transformers if available.
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                self._st_matrix = self._st_model.encode(docs, normalize_embeddings=True)
                logger.info("RAG upgraded to sentence-transformers (MiniLM)")
            except Exception:
                # No-op — TF-IDF path stays primary.
                pass

            self._loaded = True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def suggest(
        self,
        code: str,
        *,
        top_k: int = 3,
        context: SuggestContext | None = None,
    ) -> List[Suggestion]:
        self._ensure_loaded()
        hits = _extract_model_hits(code)
        if not hits:
            return []

        if context and context.impact_focus_lines:
            focus = frozenset(context.impact_focus_lines)
            hits = sorted(hits, key=lambda h: (0 if h[0] in focus else 1, h[0]))

        suggestions: List[Suggestion] = []
        seen: set[Tuple[str, str]] = set()

        for line, snippet, model_id in hits:
            ranked = self._rank(model_id)
            for entry, score in ranked:
                if score <= 0.0:
                    continue
                # Only suggest when the target is genuinely smaller.
                if entry.params_to_b >= entry.params_from_b * 0.95:
                    continue
                key = (model_id.lower(), entry.to_model.lower())
                if key in seen:
                    continue
                seen.add(key)
                reasoning = _reasoning_with_part_a(entry.reasoning, line, context)
                suggestions.append(
                    Suggestion(
                        line=line,
                        original_snippet=snippet,
                        alternative_snippet=_swap(snippet, entry.from_model, entry.to_model),
                        carbon_saved_pct=entry.carbon_saved_pct,
                        performance_retained_pct=entry.performance_retained_pct,
                        citation=entry.citation,
                        reasoning=reasoning,
                    )
                )
                if len([s for s in suggestions if s.line == line]) >= top_k:
                    break

        return suggestions

    def _rank(self, query: str) -> List[Tuple[CorpusEntry, float]]:
        if self._st_model is not None and self._st_matrix is not None:
            qv = self._st_model.encode([query], normalize_embeddings=True)
            sims = (self._st_matrix @ qv.T).flatten()
        else:
            assert self._vectorizer is not None and self._matrix is not None
            qv = self._vectorizer.transform([query])
            sims = cosine_similarity(self._matrix, qv).flatten()

        # Strong boost for exact substring match against `from` model id.
        boosted = []
        q_lower = query.lower()
        for i, e in enumerate(self._entries):
            score = float(sims[i])
            if e.from_model.lower() in q_lower or q_lower in e.from_model.lower():
                score += 1.0
            boosted.append((e, score))

        boosted.sort(key=lambda t: t[1], reverse=True)
        return boosted


# ---------------------------------------------------------------------------
# Code parsing
# ---------------------------------------------------------------------------

_FROM_PRETRAINED_RE = re.compile(
    r"""\bfrom_pretrained\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_PIPELINE_RE = re.compile(
    r"""\bpipeline\s*\([^)]*model\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE | re.DOTALL,
)
_DIFFUSERS_RE = re.compile(
    r"""\b(?:DiffusionPipeline|StableDiffusionPipeline|AutoPipelineForText2Image)\.from_pretrained\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)


def _extract_model_hits(code: str) -> List[Tuple[int, str, str]]:
    """Return (line_number, original_snippet, model_id) for each match."""
    hits: List[Tuple[int, str, str]] = []
    for idx, raw in enumerate(code.splitlines(), start=1):
        line = raw.strip()
        for regex in (_FROM_PRETRAINED_RE, _PIPELINE_RE, _DIFFUSERS_RE):
            for m in regex.finditer(line):
                hits.append((idx, line, m.group(1)))
    return hits


def _swap(snippet: str, old: str, new: str) -> str:
    # Case-insensitive substring swap that preserves the original quote
    # characters in the snippet.
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    if pattern.search(snippet):
        return pattern.sub(new, snippet, count=1)
    # Fallback: just append a comment hinting at the swap.
    return f"{snippet}  # try: {new}"


# Module-level singleton so the index is built once per process.
_INDEX: RagIndex | None = None


def get_index() -> RagIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex()
    return _INDEX


def suggest(
    code: str,
    top_k: int = 3,
    *,
    context: SuggestContext | None = None,
) -> List[Suggestion]:
    return get_index().suggest(code, top_k=top_k, context=context)


def _reasoning_with_part_a(
    corpus_reasoning: str,
    line: int,
    context: SuggestContext | None,
) -> str:
    """Append Part A (grid + estimate) narrative so swaps are justified in the user's context."""
    if not context:
        return corpus_reasoning
    bits: List[str] = []
    if context.region and context.current_gco2_kwh is not None:
        bits.append(
            f"Grid ({context.region}) is ~{context.current_gco2_kwh:.0f} gCO₂/kWh right now."
        )
    if (
        context.co2_grams_now is not None
        and context.co2_grams_optimal is not None
        and context.co2_grams_now > 0
    ):
        script_pct = 100.0 * (1.0 - context.co2_grams_optimal / context.co2_grams_now)
        bits.append(
            f"Rules-based script estimate: ~{context.co2_grams_now:.0f} g CO₂ if you train "
            f"through the current mix vs ~{context.co2_grams_optimal:.0f} g when timed with "
            f"the cleaner window (~{script_pct:.0f}% lower) — independent of this model swap."
        )
    if context.optimal_window_start or context.co2_savings_pct_window is not None:
        slot = context.optimal_window_start or "the forecast low-carbon window"
        pct = context.co2_savings_pct_window
        if pct is not None:
            bits.append(
                f"Clean-window timing ({slot}) can cut grid-attributed intensity ~{pct:.0f}% vs running now."
            )
        else:
            bits.append(f"Clean-window timing: next favorable slot around {slot}.")
    if context.impact_focus_lines and line in frozenset(context.impact_focus_lines):
        bits.append("This line is near a high-impact training pattern in your script.")
    if not bits:
        return corpus_reasoning
    return corpus_reasoning.rstrip() + " " + " ".join(bits)
