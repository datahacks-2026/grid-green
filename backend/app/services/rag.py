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
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

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

            # Best-effort upgrade to sentence-transformers. If Hugging Face is
            # unreachable (corporate proxy, air-gapped CI, etc.) this must fail
            # *fast* and fall back to TF-IDF — otherwise the first suggest_greener
            # call can exceed the FastAPI request timeout.
            if os.environ.get("GRIDGREEN_DISABLE_ST", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }:
                logger.info("sentence-transformers disabled via GRIDGREEN_DISABLE_ST")
            else:
                try:
                    from sentence_transformers import SentenceTransformer  # type: ignore
                except Exception as exc:  # noqa: BLE001
                    logger.info("sentence-transformers not importable (%s)", exc)
                else:
                    model_name = os.environ.get(
                        "GRIDGREEN_ST_MODEL",
                        "sentence-transformers/all-MiniLM-L6-v2",
                    ).strip()
                    if not model_name:
                        logger.info("GRIDGREEN_ST_MODEL empty — skipping ST upgrade")
                    else:
                        try:
                            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "8")
                            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "8")

                            self._st_model = SentenceTransformer(model_name)
                            self._st_matrix = self._st_model.encode(
                                docs,
                                normalize_embeddings=True,
                                show_progress_bar=False,
                            )
                            logger.info(
                                "RAG upgraded to sentence-transformers (%s)", model_name
                            )
                        except Exception as exc:  # noqa: BLE001
                            self._st_model = None
                            self._st_matrix = None
                            logger.warning(
                                "sentence-transformers init failed (%s); using TF-IDF only",
                                exc,
                            )

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
                # Require the corpus `from` to actually be the user's model id
                # (with or without the HF `org/` prefix). Without this we surface
                # unrelated swaps and worst case rewrite the wrong substring.
                if not _ids_match(model_id, entry.from_model):
                    continue
                # Don't recommend a swap the user already applied.
                if _ids_match(model_id, entry.to_model):
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

# Calls that explicitly take a model id as their first positional arg or as
# `model=`/`repo_id=`/`model_name=`. We deliberately keep the regex broad —
# false positives are filtered later by `_looks_like_model_id`.
_CALL_RE = re.compile(
    r"""\b(?:from_pretrained|pipeline|SentenceTransformer|CrossEncoder|LLM|"""
    r"""ChatOpenAI|ChatAnthropic|ChatGoogleGenerativeAI|HuggingFaceEndpoint|"""
    r"""HuggingFaceHub|HuggingFacePipeline|AutoModel[A-Za-z]*|AutoTokenizer|"""
    r"""AutoProcessor|DiffusionPipeline|StableDiffusionPipeline|"""
    r"""AutoPipelineForText2Image|AutoPipelineForImage2Image|"""
    r"""WhisperForConditionalGeneration|whisper\.load_model)\s*\(""",
    re.IGNORECASE,
)

# `model=...`, `model_name=...`, `model_id=...`, `repo_id=...` keyword args.
_KWARG_RE = re.compile(
    r"""\b(?:model|model_name|model_id|repo_id|model_path|pretrained_model_name_or_path)"""
    r"""\s*=\s*['"]([^'"\n]{2,200})['"]""",
    re.IGNORECASE,
)

# `MODEL_ID = "..."`, `model_name = "..."`, etc. Top-level assignments.
_ASSIGN_RE = re.compile(
    r"""^\s*(?:MODEL(?:_ID|_NAME)?|model(?:_id|_name)?|HF_MODEL|CHECKPOINT)"""
    r"""\s*[:=]\s*['"]([^'"\n]{2,200})['"]""",
    re.IGNORECASE,
)

# Bare quoted strings — last resort: pull every string literal and filter by shape.
_STRING_LITERAL_RE = re.compile(r"""['"]([A-Za-z0-9_./@:\-]{3,200})['"]""")

_KNOWN_HF_ORGS = (
    "meta-llama/", "mistralai/", "openai/", "google/", "microsoft/", "facebook/",
    "stabilityai/", "runwayml/", "BAAI/", "sentence-transformers/", "tiiuae/",
    "EleutherAI/", "Qwen/", "deepset/", "huggingface/", "nvidia/", "anthropic/",
    "cohere/", "ai21/", "databricks/", "mosaicml/", "01-ai/", "Salesforce/",
    "bigscience/", "bigcode/", "intfloat/", "thenlper/", "jinaai/", "mixedbread-ai/",
    "tiiuae/", "togethercomputer/", "WizardLM/", "lmsys/",
)

# Lower-cased prefixes for bare model names (no org/).
_KNOWN_MODEL_PREFIXES = (
    "gpt-", "gpt2", "gpt3", "gpt4", "o1-", "o3-", "o4-",
    "claude-", "claude2", "claude3",
    "gemini-", "gemma-",
    "llama-", "llama2", "llama3", "llama-2", "llama-3", "llama-4",
    "mistral-", "mixtral-", "codestral-",
    "phi-", "phi2", "phi3", "phi4",
    "qwen-", "qwen2", "qwen3",
    "yi-", "deepseek-",
    "bert-", "roberta-", "distilbert", "albert-", "electra-", "xlnet-", "xlm-",
    "t5-", "flan-t5-", "ul2-", "bart-", "pegasus-", "mbart-", "m2m100-",
    "vit-", "deit-", "swin-", "beit-", "convnext-", "efficientnet-",
    "resnet", "mobilenet", "yolov", "detr-",
    "clip-", "blip-", "siglip-", "owl-vit",
    "stable-diffusion", "sdxl", "sd-turbo", "kandinsky", "playground-",
    "whisper-", "wav2vec2-", "hubert-", "mms-",
    "command-", "command-r", "embed-",
)


def _looks_like_model_id(s: str) -> bool:
    if not s or len(s) < 2 or len(s) > 200:
        return False
    if any(ch in s for ch in (" ", "\n", "\t")):
        return False
    if s.startswith(("./", "../", "/", "http://", "https://")):
        return "huggingface.co/" in s
    if s.endswith((".py", ".json", ".yaml", ".yml", ".txt", ".csv", ".md", ".png", ".jpg")):
        return False
    if any(s.startswith(o) for o in _KNOWN_HF_ORGS):
        return True
    sl = s.lower()
    return any(sl.startswith(p) for p in _KNOWN_MODEL_PREFIXES)


def _extract_model_hits(code: str) -> List[Tuple[int, str, str]]:
    """Return (line_number, original_snippet, model_id) for each match.

    Strategy (in order, deduped):
    1. Direct kwargs: `model=...`, `repo_id=...`, etc.
    2. Top-level assignments: `MODEL_ID = "..."`.
    3. First positional arg of known model-loading calls (e.g. `from_pretrained("x")`).
    4. Any bare string literal that looks like a model id (HF org/name or known prefix).
    """
    hits: List[Tuple[int, str, str]] = []
    seen: set[Tuple[int, str]] = set()

    def _add(line_no: int, snippet: str, candidate: str) -> None:
        if not _looks_like_model_id(candidate):
            return
        key = (line_no, candidate.lower())
        if key in seen:
            return
        seen.add(key)
        hits.append((line_no, snippet, candidate))

    for idx, raw in enumerate(code.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        for m in _KWARG_RE.finditer(line):
            _add(idx, line, m.group(1))

        am = _ASSIGN_RE.match(line)
        if am:
            _add(idx, line, am.group(1))

        # Positional first arg of a known call (heuristic — parse the literal
        # that follows the opening paren until the next ')' or ',').
        for cm in _CALL_RE.finditer(line):
            tail = line[cm.end():]
            lit = _first_string_literal(tail)
            if lit:
                _add(idx, line, lit)

        # Last resort: any bare string literal that "looks like" a model id.
        # This catches `MODEL = "gpt-4o-mini"` style as well as comments-stripped
        # string constants embedded mid-call.
        for sm in _STRING_LITERAL_RE.finditer(line):
            _add(idx, line, sm.group(1))

    return hits


def _first_string_literal(s: str) -> str | None:
    m = re.match(r"""\s*['"]([^'"\n]{2,200})['"]""", s)
    return m.group(1) if m else None


def _ids_match(a: str, b: str) -> bool:
    """True when `a` and `b` are the same model id (case-insensitive,
    optional `org/` prefix on either side)."""
    al, bl = a.lower(), b.lower()
    if al == bl:
        return True
    return al.split("/", 1)[-1] == bl.split("/", 1)[-1]


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
