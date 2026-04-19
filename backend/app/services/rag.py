"""RAG over the curated HF model corpus (Phase 5 + a.md §8.8).

Runtime embedding tiers (auto-selected on first request):

1. **sentence-transformers** — when the package is importable (and not
   disabled by `GRIDGREEN_DISABLE_ST=1`), we encode the corpus once with
   `all-MiniLM-L6-v2` (the same model we run on Brev for the sponsor
   evidence run).
2. **TF-IDF fallback** — pure scikit-learn cosine similarity over the
   model id + tags + reasoning text. Always available; the demo never
   breaks when the heavier path is missing.

A separate **Snowflake Cortex** path is exercised offline by
`scripts/build_rag_index.py --target snowflake`, which uploads the
corpus + `VECTOR(FLOAT, 384)` embeddings into `RAG_HF_CORPUS`.

When `GRIDGREEN_RAG_BACKEND=snowflake` is set (and the SBERT model is
loaded so we can encode queries with the same dimension), the runtime
ranker calls Snowflake Cortex with `VECTOR_COSINE_SIMILARITY` against
the uploaded `RAG_HF_CORPUS.embedding` column instead of doing the
cosine product locally. The default (`auto`) prefers local for latency
but falls through to Snowflake if the local SBERT path is unavailable.

The query is the union of model ids extracted from the user's code plus
their associated tag context. The result set is filtered to entries whose
target is *smaller* than the source (otherwise we'd suggest swapping a
small model for a bigger one) and deduped by `(from, to)`.

When no corpus row matches, ``app.services.hf_hub_models`` may call the
public Hugging Face Hub model API (``safetensors`` totals + ``pipeline_tag``)
to propose a smaller sentence-embedding checkpoint without editing
``hf_corpus.json`` (disable with ``GRIDGREEN_DISABLE_HF_HUB=1``).
"""

from __future__ import annotations

import ast
import json
import logging
import os
import threading
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.services import hf_hub_models

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
        self._st_init_started = False
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

            # Run sentence-transformers init in the background so the first
            # request never blocks on model downloads/network retries.
            self._start_st_init_background(docs)

            self._loaded = True

    def _start_st_init_background(self, docs: List[str]) -> None:
        if self._st_init_started:
            return
        self._st_init_started = True

        if os.environ.get("GRIDGREEN_DISABLE_ST", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            logger.info("sentence-transformers disabled via GRIDGREEN_DISABLE_ST")
            return

        model_name = os.environ.get(
            "GRIDGREEN_ST_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        ).strip()
        if not model_name:
            logger.info("GRIDGREEN_ST_MODEL empty — skipping ST upgrade")
            return

        def _load() -> None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
            except Exception as exc:  # noqa: BLE001
                logger.info("sentence-transformers not importable (%s)", exc)
                return

            try:
                os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "3")
                os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "3")
                self._st_model = SentenceTransformer(model_name)
                self._st_matrix = self._st_model.encode(
                    docs,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                logger.info("RAG upgraded to sentence-transformers (%s)", model_name)
            except Exception as exc:  # noqa: BLE001
                self._st_model = None
                self._st_matrix = None
                logger.warning(
                    "sentence-transformers init failed (%s); using TF-IDF only",
                    exc,
                )

        threading.Thread(
            target=_load,
            name="rag-st-init",
            daemon=True,
        ).start()

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

            # Live Hugging Face Hub metadata when the corpus has no exact `from`
            # match for this hit (embedding-class models only; see hf_hub_models).
            n_on_line = len([s for s in suggestions if s.line == line])
            if n_on_line == 0:
                plan = hf_hub_models.plan_embedding_downgrade_from_hub(
                    line, snippet, model_id
                )
                if plan is not None:
                    dyn_to = hf_hub_models.EMBEDDING_FALLBACK_MODEL_ID
                    dkey = (model_id.lower(), dyn_to.lower())
                    if dkey not in seen:
                        seen.add(dkey)
                        suggestions.append(
                            Suggestion(
                                line=plan.line,
                                original_snippet=plan.original_snippet,
                                alternative_snippet=plan.alternative_snippet,
                                carbon_saved_pct=plan.carbon_saved_pct,
                                performance_retained_pct=plan.performance_retained_pct,
                                citation=plan.citation,
                                reasoning=_reasoning_with_part_a(
                                    plan.reasoning, line, context
                                ),
                            )
                        )

        return suggestions

    def _rank(self, query: str) -> List[Tuple[CorpusEntry, float]]:
        sims = self._similarity_scores(query)

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

    def _similarity_scores(self, query: str):
        """Per-entry similarity in `self._entries` order.

        Backend selection (env ``GRIDGREEN_RAG_BACKEND``):

        - ``snowflake`` — force Cortex ``VECTOR_COSINE_SIMILARITY`` against
          ``RAG_HF_CORPUS``; raises a warning + falls back if it fails.
        - ``local`` — never call Snowflake; use in-process SBERT then TF-IDF.
        - ``auto`` (default) — try Snowflake when ``SNOWFLAKE_*`` is
          configured, else local SBERT, else TF-IDF.
        """
        backend = os.environ.get("GRIDGREEN_RAG_BACKEND", "auto").strip().lower()

        if backend in {"snowflake", "auto"}:
            sims = self._similarity_snowflake(query)
            if sims is not None:
                return sims
            if backend == "snowflake":
                logger.warning(
                    "GRIDGREEN_RAG_BACKEND=snowflake requested but Cortex "
                    "scoring unavailable; falling back to local."
                )

        if self._st_model is not None and self._st_matrix is not None:
            qv = self._st_model.encode([query], normalize_embeddings=True)
            return (self._st_matrix @ qv.T).flatten()

        assert self._vectorizer is not None and self._matrix is not None
        qv = self._vectorizer.transform([query])
        return cosine_similarity(self._matrix, qv).flatten()

    def _similarity_snowflake(self, query: str):
        """Score the query against `RAG_HF_CORPUS.embedding` via Cortex.

        Returns a numpy-like array aligned with ``self._entries``, or
        ``None`` if Snowflake is not configured / connection fails / the
        local SBERT encoder isn't available (we need it to embed the
        query in the same 384-d space as the uploaded vectors).
        """
        if self._st_model is None:
            return None
        try:
            from app.config import get_settings  # local import to keep cold start fast
        except Exception:  # noqa: BLE001
            return None
        settings = get_settings()
        if not settings.use_snowflake:
            return None
        try:
            import snowflake.connector  # type: ignore
        except Exception:  # noqa: BLE001
            return None

        try:
            qv = self._st_model.encode([query], normalize_embeddings=True)[0]
            qv_json = json.dumps([float(x) for x in qv])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Snowflake RAG: query encode failed (%s)", exc)
            return None

        try:
            ctx = snowflake.connector.connect(
                account=settings.snowflake_account,
                user=settings.snowflake_user,
                password=settings.snowflake_password,
                warehouse=settings.snowflake_warehouse,
                database=settings.snowflake_database,
                schema=settings.snowflake_schema,
                role=settings.snowflake_role,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Snowflake RAG: connect failed (%s)", exc)
            return None

        try:
            cs = ctx.cursor()
            cs.execute(
                """
                SELECT id,
                       VECTOR_COSINE_SIMILARITY(
                         embedding,
                         PARSE_JSON(%s)::VECTOR(FLOAT, 384)
                       ) AS score
                FROM rag_hf_corpus
                """,
                (qv_json,),
            )
            score_by_id = {row[0]: float(row[1] or 0.0) for row in cs.fetchall()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Snowflake RAG: query failed (%s)", exc)
            return None
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

        if not score_by_id:
            return None

        import numpy as np  # already a transitive dep via sklearn

        sims = np.zeros(len(self._entries), dtype=float)
        for i, e in enumerate(self._entries):
            sims[i] = score_by_id.get(f"{e.from_model}->{e.to_model}", 0.0)
        logger.debug("Snowflake Cortex ranked %d entries", len(score_by_id))
        return sims


# ---------------------------------------------------------------------------
# Code parsing
# ---------------------------------------------------------------------------

# Calls that explicitly take a model id as their first positional arg or as
# `model=`/`repo_id=`/`model_name=`. We deliberately keep the regex broad —
# false positives are filtered later by `_looks_like_model_id`.
_CALL_RE = re.compile(
    r"""\b(?:from_pretrained|pipeline|SentenceTransformer|CrossEncoder|LLM|"""
    r"""ChatOpenAI|ChatAnthropic|ChatGoogleGenerativeAI|ChatBedrock|BedrockChat|"""
    r"""ChatCohere|ChatGroq|ChatTogether|"""
    r"""HuggingFaceEndpoint|HuggingFaceHub|HuggingFacePipeline|"""
    r"""AutoModel[A-Za-z]*|AutoTokenizer|AutoProcessor|"""
    r"""DiffusionPipeline|StableDiffusionPipeline|"""
    r"""AutoPipelineForText2Image|AutoPipelineForImage2Image|"""
    r"""WhisperForConditionalGeneration|whisper\.load_model|"""
    r"""replicate\.run|Replicate|timm\.create_model|create_model)\s*\(""",
    re.IGNORECASE,
)

# `model=...`, `model_name=...`, `model_id=...`, `repo_id=...`, `modelId=...`
# (Bedrock camelCase) keyword args. `re.IGNORECASE` makes `modelId`,
# `model_id`, `MODEL_ID`, `MODELID`, etc. all match a single alternation.
_KWARG_RE = re.compile(
    r"""\b(?:model|model_name|model_id|modelId|repo_id|model_path|"""
    r"""pretrained_model_name_or_path)"""
    r"""\s*=\s*['"]([^'"\n]{2,200})['"]""",
    re.IGNORECASE,
)

# `MODEL_ID = "..."`, `model_name = "..."`, etc. Top-level assignments.
_ASSIGN_RE = re.compile(
    r"""^\s*(?:MODEL(?:_ID|_NAME)?|model(?:_id|_name)?|HF_MODEL|CHECKPOINT)"""
    r"""\s*[:=]\s*['"]([^'"\n]{2,200})['"]""",
    re.IGNORECASE,
)

# Inline `# comment` stripper that respects string literals.
_INLINE_COMMENT_RE = re.compile(
    r"""(?<!['"])\#.*$"""
)

_KNOWN_HF_ORGS = (
    "meta-llama/", "mistralai/", "openai/", "google/", "microsoft/", "facebook/",
    "stabilityai/", "runwayml/", "BAAI/", "sentence-transformers/", "tiiuae/",
    "EleutherAI/", "Qwen/", "deepset/", "huggingface/", "nvidia/", "anthropic/",
    "cohere/", "ai21/", "databricks/", "mosaicml/", "01-ai/", "Salesforce/",
    "bigscience/", "bigcode/", "intfloat/", "thenlper/", "jinaai/", "mixedbread-ai/",
    "tiiuae/", "togethercomputer/", "WizardLM/", "lmsys/",
    # Replicate / Together / Groq / etc — short org prefixes seen in
    # community-published model slugs like
    # ``meta/meta-llama-3-70b-instruct:abc123`` (Replicate).
    "meta/", "replicate/", "together/", "groq/", "perplexity/", "deepseek-ai/",
)

# Bedrock-style vendor-prefixed model IDs (no slash). When a user calls
# `bedrock.invoke_model(modelId="anthropic.claude-3-sonnet-20240229")` the
# id starts with `anthropic.`, `meta.`, `amazon.`, `cohere.`, `ai21.`,
# `mistral.`, `stability.` — none of which are HF orgs. We treat the
# segment after the dot as the actual model name for prefix matching.
_BEDROCK_VENDOR_PREFIXES = (
    "anthropic.", "meta.", "amazon.", "cohere.", "ai21.",
    "mistral.", "stability.", "deepseek.",
)

def _looks_like_hf_hub_id(s: str) -> bool:
    """True for ``namespace/model`` strings typical of Hugging Face Hub ids.

    Unknown orgs (e.g. ``FremyCompany/BioLORD-2023``) are not listed in
    ``_KNOWN_HF_ORGS`` but are still real model references when passed to
    ``SentenceTransformer``, ``from_pretrained``, etc.

    Kept conservative: single slash, slug-like segments, and the model
    segment must look "versioned" (digit, hyphen, or underscore) or be
    a long tail — avoids common ``type/subtype`` MIME pairs.
    """
    if s.count("/") != 1:
        return False
    left, right = s.split("/", 1)
    if len(left) < 2 or len(right) < 2:
        return False
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", left):
        return False
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", right):
        return False
    if left.lower() in {"http", "https", "file", "git", "ssh", "text", "application"}:
        return False
    if any(ch.isspace() for ch in (left + right)):
        return False
    return bool(re.search(r"[\d\-_]", right)) or len(right) >= 12


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
    "bert-", "roberta-", "distilbert", "distilgpt2", "albert-", "electra-",
    "xlnet-", "xlm-", "mobilebert",
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
    if _looks_like_hf_hub_id(s):
        return True
    # Strip Replicate's `:sha` version suffix and Bedrock's `vendor.` prefix
    # before checking against bare-name prefixes so e.g.
    #   ``meta/meta-llama-3-70b-instruct:abc123``         (Replicate)
    #   ``anthropic.claude-3-sonnet-20240229``            (Bedrock)
    #   ``vit_base_patch16_224``                          (timm)
    # all resolve to a recognised model family.
    sl = s.lower().split(":", 1)[0]
    for vendor in _BEDROCK_VENDOR_PREFIXES:
        if sl.startswith(vendor):
            sl = sl[len(vendor):]
            break
    sl_norm = sl.replace("_", "-")
    return any(
        sl.startswith(p) or sl_norm.startswith(p)
        for p in _KNOWN_MODEL_PREFIXES
    )


def _extract_model_hits(code: str) -> List[Tuple[int, str, str]]:
    """Return (line_number, original_snippet, model_id) for each model use.

    A "hit" only counts when a model id is *actually used*, i.e. it appears
    as one of:

    1. A keyword arg recognised as a model location:
       ``model=``, ``model_name=``, ``model_id=``, ``modelId=``,
       ``repo_id=``, ``model_path=``, ``pretrained_model_name_or_path=``.
       Also matches dict-spread kwargs like ``**{"model": "gpt-4"}``
       (requires AST parsing to reach inside the dict literal).
    2. A top-level assignment to a model-shaped variable:
       ``MODEL_ID = "..."``, ``model_name = "..."``, ``CHECKPOINT = "..."``,
       and the same variable is later passed into a known call.
    3. The first positional string literal of a known model-loading call:
       ``from_pretrained("...")``, ``pipeline("text-gen", "...")``,
       ``SentenceTransformer("...")``, ``ChatOpenAI("...")``, etc.
    4. F-strings whose **constant prefix** uniquely identifies a family,
       e.g. ``from_pretrained(f"meta-llama/Llama-{size}-Instruct")``
       extracts ``meta-llama/Llama-`` so the catalog can pick a
       worst-case family member.

    We deliberately do **not** scan every bare string literal — that would
    flag random strings inside lists, descriptions, doc-strings, log
    messages, and inline comments as "models" and produce ghost
    suggestions for snippets the user never executes.

    Implementation: we run **AST extraction first** (handles variables,
    dict-spread, f-strings) and then union with the **regex extractor**
    which is more permissive about wrapper functions (any callable with a
    recognised ``model=`` kwarg, even if its name is unknown to us).
    """
    seen: set[Tuple[int, str]] = set()
    hits: List[Tuple[int, str, str]] = []

    def _add(line_no: int, snippet: str, candidate: str) -> None:
        if not _looks_like_model_id(candidate):
            return
        key = (line_no, candidate.lower())
        if key in seen:
            return
        seen.add(key)
        hits.append((line_no, snippet, candidate))

    for line_no, snippet, candidate in _extract_via_ast(code):
        _add(line_no, snippet, candidate)
    for line_no, snippet, candidate in _extract_via_regex(code):
        _add(line_no, snippet, candidate)
    return hits


def _extract_via_regex(code: str) -> List[Tuple[int, str, str]]:
    """Original regex extractor — matches kwargs, MODEL_* assignments, and
    positional literals of known calls. Robust on partial / non-parseable
    snippets where the AST path bails out."""
    out: List[Tuple[int, str, str]] = []
    for idx, raw in enumerate(code.splitlines(), start=1):
        # Strip trailing inline `# ...` comments so models referenced only in
        # a comment never trigger suggestions.
        line = _INLINE_COMMENT_RE.sub("", raw).strip()
        if not line or line.startswith("#"):
            continue

        for m in _KWARG_RE.finditer(line):
            out.append((idx, line, m.group(1)))

        am = _ASSIGN_RE.match(line)
        if am:
            out.append((idx, line, am.group(1)))

        # Positional first arg of a known call (heuristic — parse the literal
        # that follows the opening paren until the next ')' or ',').
        for cm in _CALL_RE.finditer(line):
            tail = line[cm.end():]
            lit = _first_string_literal(tail)
            if lit:
                out.append((idx, line, lit))
    return out


def _first_string_literal(s: str) -> str | None:
    m = re.match(r"""\s*['"]([^'"\n]{2,200})['"]""", s)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# AST extractor — handles variables, dict-spread kwargs, and f-strings
# ---------------------------------------------------------------------------

# Kwargs that are known to carry a model id. Mirrors `_KWARG_RE` (the
# regex variant) but lookup-friendly. Compared case-insensitively below.
_MODEL_KWARG_NAMES = frozenset(
    s.lower()
    for s in (
        "model",
        "model_name",
        "model_id",
        "modelId",
        "repo_id",
        "model_path",
        "pretrained_model_name_or_path",
    )
)

# Bare callable names that take a model id positionally. Mirrors `_CALL_RE`.
# Compared case-insensitively. The `AutoModel*` family is handled with a
# `startswith("automodel")` check below.
_KNOWN_CALL_NAMES = frozenset(
    s.lower()
    for s in (
        "from_pretrained",
        "pipeline",
        "SentenceTransformer",
        "CrossEncoder",
        "LLM",
        "ChatOpenAI",
        "ChatAnthropic",
        "ChatGoogleGenerativeAI",
        "ChatBedrock",
        "BedrockChat",
        "ChatCohere",
        "ChatGroq",
        "ChatTogether",
        "HuggingFaceEndpoint",
        "HuggingFaceHub",
        "HuggingFacePipeline",
        "AutoTokenizer",
        "AutoProcessor",
        "DiffusionPipeline",
        "StableDiffusionPipeline",
        "AutoPipelineForText2Image",
        "AutoPipelineForImage2Image",
        "WhisperForConditionalGeneration",
        "load_model",  # whisper.load_model
        "run",  # replicate.run
        "Replicate",
        "create_model",  # timm.create_model
    )
)

_MODEL_NAMED_ASSIGN_RE = re.compile(
    r"^(?:MODEL(?:_ID|_NAME)?|model(?:_id|_name)?|HF_MODEL|CHECKPOINT)$",
    re.IGNORECASE,
)


def _extract_via_ast(code: str) -> List[Tuple[int, str, str]]:
    """AST-based extractor. Returns [] if the code doesn't parse."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    code_lines = code.splitlines()
    sym_table = _build_symbol_table(tree)
    hits: List[Tuple[int, str, str]] = []

    def _snippet_for(line_no: int) -> str:
        if 0 < line_no <= len(code_lines):
            return code_lines[line_no - 1].strip()
        return ""

    # Top-level MODEL_*-shaped assignments: pull the literal even if the
    # value is never wired into a known call (matches the legacy
    # _ASSIGN_RE behaviour so existing UX is preserved).
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and _MODEL_NAMED_ASSIGN_RE.match(target.id):
                lit = _resolve_to_string(node.value, sym_table)
                if lit:
                    hits.append((node.lineno, _snippet_for(node.lineno), lit))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        line = node.lineno
        snippet = _snippet_for(line)
        is_known = _is_known_callable(node.func)

        # Dict-spread `**{"model": "gpt-4"}` is checked for *every* call,
        # not just known ones, because closed-API SDK calls like
        # `OpenAI().chat.completions.create(**{"model": "..."})` use
        # generic terminal callables (`create`, `invoke`) that we can't
        # safely add to `_KNOWN_CALL_NAMES` without producing false
        # positives. The strong filter `_looks_like_model_id` on the
        # resolved value protects us.
        for kw in node.keywords:
            if kw.arg is None and isinstance(kw.value, ast.Dict):
                for k_node, v_node in zip(kw.value.keys, kw.value.values):
                    if (
                        isinstance(k_node, ast.Constant)
                        and isinstance(k_node.value, str)
                        and k_node.value.lower() in _MODEL_KWARG_NAMES
                    ):
                        lit = _resolve_to_string(v_node, sym_table)
                        if lit:
                            hits.append((line, snippet, lit))

        if not is_known:
            # Direct kwargs and positional args of unknown callables are
            # left to the regex extractor — adding them here would flag
            # too many incidental string literals as "models".
            continue

        # First two positional args (covers `pipeline("task", "model")`).
        for pos_arg in node.args[:2]:
            lit = _resolve_to_string(pos_arg, sym_table)
            if lit:
                hits.append((line, snippet, lit))
                break

        # Direct keyword args of known callables.
        for kw in node.keywords:
            if kw.arg is None:
                continue  # dict-spread already handled above
            if kw.arg.lower() in _MODEL_KWARG_NAMES:
                lit = _resolve_to_string(kw.value, sym_table)
                if lit:
                    hits.append((line, snippet, lit))

    return hits


def _build_symbol_table(tree: ast.AST) -> dict[str, str]:
    """Map ``NAME -> "literal string"`` for any top-level / nested simple
    assignment of a string constant. Lets us resolve
    ``MID = "gpt2-xl"; from_pretrained(MID)`` across statements."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                # Last assignment wins — matches Python runtime semantics
                # closely enough for static lookup.
                table[target.id] = node.value.value
            elif isinstance(node.value, ast.JoinedStr):
                joined = _join_fstring(node.value)
                if joined:
                    table[target.id] = joined
    return table


def _resolve_to_string(node: ast.AST, sym_table: dict[str, str]) -> Optional[str]:
    """Best-effort: turn an AST expression into a string literal candidate.

    Handles:
    - ``ast.Constant("...")``
    - ``ast.Name`` looked up in ``sym_table``
    - ``ast.JoinedStr`` (f-string) — concatenates leading constants until
      the first runtime expression and stops; if the resulting prefix is
      "long enough" to be a model id, returns it.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return sym_table.get(node.id)
    if isinstance(node, ast.JoinedStr):
        return _join_fstring(node)
    return None


def _join_fstring(node: ast.JoinedStr) -> Optional[str]:
    """Concatenate the leading constant pieces of an f-string up to (but
    not including) the first ``FormattedValue``. Returns ``None`` if no
    usable prefix exists.

    The prefix is the only part we can statically rely on; downstream
    matching (`_looks_like_model_id`, catalog lookup) treats it as a
    "family hint" and the carbon estimator's prefix-family fallback
    picks the worst-case variant in that family.
    """
    parts: List[str] = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            break
    prefix = "".join(parts)
    return prefix if len(prefix) >= 4 else None


def _is_known_callable(node: ast.AST) -> bool:
    """True if `node` is a Name / Attribute whose final segment matches
    one of `_KNOWN_CALL_NAMES` (or the `AutoModel*` family)."""
    name: Optional[str] = None
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    if not name:
        return False
    n = name.lower()
    if n in _KNOWN_CALL_NAMES:
        return True
    if n.startswith("automodel"):
        return True
    return False


def _ids_match(a: str, b: str) -> bool:
    """True when `a` and `b` refer to the same model.

    Tolerated variations:

    - case (HF mirrors are case-preserving; APIs are not)
    - the optional ``org/`` HF prefix on either side
    - the optional Bedrock ``vendor.`` prefix (``anthropic.``, ``meta.``)
    - Replicate's trailing ``:sha`` version pin
    - ``_`` vs ``-`` (timm uses underscores; the HF mirror uses dashes)

    On top of straight equality, we accept a **token-anchored substring
    match** so that Replicate-style slugs like
    ``meta/meta-llama-3-70b-instruct`` still match a corpus ``from`` of
    ``meta-llama/Llama-3-70B`` (the canonical id is "contained in" the
    Replicate slug, separated by ``-`` boundaries). The shorter side
    must be at least 5 chars to avoid spurious matches against generic
    tokens like ``base`` or ``v2``.
    """

    def _normalise(x: str) -> str:
        x = x.lower().split(":", 1)[0]
        for vendor in _BEDROCK_VENDOR_PREFIXES:
            if x.startswith(vendor):
                x = x[len(vendor):]
                break
        x = x.split("/", 1)[-1]
        return x.replace("_", "-")

    na, nb = _normalise(a), _normalise(b)
    if na == nb:
        return True

    def _contained(short: str, long: str) -> bool:
        """`short` appears in `long` bounded by `-` (or string ends)."""
        if len(short) < 5 or short not in long:
            return False
        # Require dash/edge boundary so `bert-base` doesn't match
        # `roberta-base` (would substring-hit on `bert-base` → no, `roberta`
        # ends with `a`, not `bert`; the real risk is e.g. `gpt2` matching
        # inside `gpt2-xl`. We anchor on `-` to forbid that.)
        i = long.find(short)
        before = long[i - 1] if i > 0 else "-"
        after_idx = i + len(short)
        after = long[after_idx] if after_idx < len(long) else "-"
        return before == "-" and after == "-"

    if len(na) >= len(nb):
        return _contained(nb, na)
    return _contained(na, nb)


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
