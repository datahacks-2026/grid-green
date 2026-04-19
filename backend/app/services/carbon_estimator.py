"""Rules-based code → carbon estimator.

Detects model loads (HF `from_pretrained`, sklearn `.fit`, torch training
loops, etc.), looks up parameter counts from a small built-in catalog, and
maps to GPU-hours and kWh assuming an A100-class baseline. Multiplied by
current grid intensity to yield gCO2.

Phase 5 swaps the catalog for a richer source / RAG-backed lookup. The
shape returned matches `EstimateCarbonResponse` in CONTRACT.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Static knowledge — small, hand-curated. Phase 5 replaces with HF lookups.
# ---------------------------------------------------------------------------

# Keys are model id patterns (lowercased substring match against the
# detected model id; the FIRST key found wins, so order longer/more
# specific keys before shorter ones — e.g. `flan-t5-xxl` before
# `flan-t5`, `gpt2-xl` before `gpt2`, `gpt-4-turbo` before `gpt-4`).
# Values: (parameters_in_billions, training_gpu_hours_full, family).
MODEL_CATALOG: Dict[str, Tuple[float, float, str]] = {
    # LLM families — open-weights
    "flan-t5-xxl":     (11.0, 7000.0, "t5"),
    "flan-t5-xl":      (3.0,  2200.0, "t5"),
    "flan-t5-large":   (0.78,  600.0, "t5"),
    "flan-t5-base":    (0.25,  150.0, "t5"),
    "flan-t5-small":   (0.08,   60.0, "t5"),
    "t5-11b":          (11.0, 7000.0, "t5"),
    "t5-3b":           (3.0,  2200.0, "t5"),
    "t5-large":        (0.77,  600.0, "t5"),
    "t5-base":         (0.22,  150.0, "t5"),
    "t5-small":        (0.06,   60.0, "t5"),
    "llama-3.1-70b":   (70.0, 64000.0, "llama"),
    "llama-3.1-8b":    (8.0,  6500.0, "llama"),
    "llama-3.2-3b":    (3.0,  2400.0, "llama"),
    "llama-3.2-1b":    (1.0,   800.0, "llama"),
    "llama-3-70b":     (70.0, 64000.0, "llama"),
    "llama-3-8b":      (8.0,  6500.0, "llama"),
    "llama-2-70b":     (70.0, 60000.0, "llama"),
    "llama-2-13b":     (13.0, 10000.0, "llama"),
    "llama-2-7b":      (7.0,  5000.0, "llama"),
    "mistral-7b":      (7.0,  4500.0, "mistral"),
    "mixtral-8x22b":   (141.0, 80000.0, "mistral"),
    "mixtral-8x7b":    (47.0, 24000.0, "mistral"),
    # GPT2 family
    "gpt2-xl":         (1.5,  900.0, "gpt2"),
    "gpt2-large":      (0.77,  500.0, "gpt2"),
    "gpt2-medium":     (0.355, 250.0, "gpt2"),
    "distilgpt2":      (0.082,  50.0, "gpt2"),
    "gpt2":            (0.124,  90.0, "gpt2"),
    # Microsoft Phi / Qwen / Gemma / Falcon / GPT-NeoX
    "phi-3.5-mini":    (3.8, 2400.0, "phi"),
    "phi-3-medium":    (14.0, 8000.0, "phi"),
    "phi-3-mini":      (3.8, 2400.0, "phi"),
    "qwen2.5-72b":     (72.0, 65000.0, "qwen"),
    "qwen2.5-7b":      (7.0,  5500.0, "qwen"),
    "qwen2-72b":       (72.0, 60000.0, "qwen"),
    "qwen2-7b":        (7.0,  5000.0, "qwen"),
    "gemma-2-27b":     (27.0, 18000.0, "gemma"),
    "gemma-2-9b":      (9.0,  6000.0, "gemma"),
    "gemma-2-2b":      (2.0,  1200.0, "gemma"),
    "falcon-40b":      (40.0, 28000.0, "falcon"),
    "falcon-7b":       (7.0,  4500.0, "falcon"),
    "gpt-neox-20b":    (20.0, 13000.0, "neox"),
    "pythia-6.9b":     (6.9,  4000.0, "neox"),
    # Encoders + classics
    "bert-large":      (0.34,  300.0, "bert"),
    "bert-base":       (0.11,  120.0, "bert"),
    "distilbert":      (0.066,  60.0, "bert"),
    "mobilebert":      (0.025,  30.0, "bert"),
    "albert-large":    (0.018,  50.0, "bert"),
    "albert-base":     (0.012,  35.0, "bert"),
    "roberta-large":   (0.355, 280.0, "roberta"),
    "roberta-base":    (0.125, 110.0, "roberta"),
    "xlnet-large":     (0.34,  300.0, "xlnet"),
    "xlnet-base":      (0.11,  120.0, "xlnet"),
    "bart-large":      (0.40,  400.0, "bart"),
    "bart-base":       (0.14,  120.0, "bart"),
    "pegasus-large":   (0.57,  500.0, "pegasus"),
    # Vision
    "vit-large":       (0.30,  280.0, "vit"),
    "vit-base":        (0.086, 100.0, "vit"),
    "clip-vit-large":  (0.43,  350.0, "clip"),
    "clip-vit-base":   (0.15,  120.0, "clip"),
    "resnet50":        (0.025,  20.0, "cnn"),
    "resnet18":        (0.011,   8.0, "cnn"),
    # Diffusion / generative / audio
    "stable-diffusion-xl": (3.5, 6250.0, "diffusion"),
    "stable-diffusion":    (0.86, 1500.0, "diffusion"),
    "sd-turbo":            (0.86,  900.0, "diffusion"),
    "whisper-large":   (1.55, 1800.0, "whisper"),
    "whisper-medium":  (0.77,  900.0, "whisper"),
    "whisper-small":   (0.24,  300.0, "whisper"),
    "wav2vec2-large":  (0.32,  300.0, "audio"),
    "wav2vec2-base":   (0.095, 120.0, "audio"),
    # Embeddings
    "all-mpnet-base":  (0.11,   80.0, "embedding"),
    # Biomedical / domain SBERT-style checkpoints (substring match on full HF id).
    "biolord":         (0.12,   85.0, "embedding"),
    "all-minilm-l6":   (0.022,  20.0, "embedding"),
    "bge-large":       (0.34,  220.0, "embedding"),
    "bge-small":       (0.033,  30.0, "embedding"),
    # Closed / API LLMs (params/hours are public best-guesses, used only
    # to scale the *relative* cost story; absolute numbers are illustrative).
    "gpt-4-turbo":     (220.0, 0.0, "openai"),
    "gpt-4o-mini":     (8.0,   0.0, "openai"),
    "gpt-4o":          (200.0, 0.0, "openai"),
    "gpt-4":           (175.0, 0.0, "openai"),
    "gpt-3.5-turbo":   (20.0,  0.0, "openai"),
    "claude-3-opus":   (200.0, 0.0, "anthropic"),
    "claude-3-5-sonnet": (175.0, 0.0, "anthropic"),
    "claude-3-5-haiku":  (20.0, 0.0, "anthropic"),
    "claude-3-sonnet": (70.0,  0.0, "anthropic"),
    "claude-3-haiku":  (20.0,  0.0, "anthropic"),
    "gemini-1.5-pro":  (175.0, 0.0, "google"),
    "gemini-1.5-flash": (8.0,  0.0, "google"),
    "command-r-plus":  (104.0, 0.0, "cohere"),
    "command-r":       (35.0,  0.0, "cohere"),
}

# Keys ordered longest-first so substring matches resolve to the most
# specific entry (e.g. `gpt2-xl` matches `gpt2-xl`, not `gpt2`).
_CATALOG_KEYS_ORDERED = sorted(MODEL_CATALOG.keys(), key=len, reverse=True)

# Approximate inference compute (GPU-hours per million prompts) for
# closed-API models that have no public training-cost number. Used only
# when `full_train_gpu_hours == 0.0` so the estimator still produces a
# non-trivial energy number for OpenAI/Anthropic/Google/Cohere calls.
API_INFERENCE_GPU_HOURS_FALLBACK = 80.0

# Energy assumptions for a single A100 80GB GPU at typical utilization.
A100_KW = 0.4  # 400W average


# Detected pattern -> impact rank used for UI hinting.
PATTERN_IMPACT = {
    "from_pretrained": "high",
    "trainer.train": "high",
    "model.fit": "medium",
    "Trainer(": "high",
    "torch.compile": "low",
    "DataLoader": "low",
    "epochs=": "medium",
    "batch_size=": "low",
    "accelerator": "low",
    "wandb.init": "low",
}


@dataclass(frozen=True)
class DetectedPatternLite:
    line: int
    pattern: str
    impact: str


@dataclass(frozen=True)
class WorkloadPracticeLite:
    """Advisory training / infra signal — not folded into kWh math (v0 scope)."""

    id: str
    line: int
    label: str
    impact: str
    rationale: str


@dataclass
class EstimateResult:
    co2_grams_now: float
    co2_grams_optimal: float
    gpu_hours: float
    kwh_estimated: float
    confidence: str
    detected_patterns: List[DetectedPatternLite]
    workload_practices: List[WorkloadPracticeLite] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate(
    code: str,
    *,
    current_gco2_kwh: float,
    optimal_gco2_kwh: float,
) -> EstimateResult:
    """Run rules-based estimator and combine with grid intensity numbers."""
    patterns = _detect_patterns(code)
    model_hits = _detect_models(code)
    # Worst-case scaling: if a script has multiple `epochs=` literals
    # (e.g. a quick-test loop and a real training loop) we charge the
    # largest one. Same idea for `batch_size`: smaller batches → more
    # wall time per epoch, so the smallest value drives the cost.
    epochs_all = _detect_int_all(code, r"epochs\s*=\s*(\d+)")
    batch_all = _detect_int_all(code, r"batch_size\s*=\s*(\d+)")
    epochs = max(epochs_all) if epochs_all else 1
    batch_size = min(batch_all) if batch_all else 32

    if model_hits:
        # Take the largest detected model as the dominant cost driver.
        params_b, full_train_gpu_hours, _ = max(
            (MODEL_CATALOG[m] for m in model_hits), key=lambda x: x[0]
        )
        confidence = "high" if len(model_hits) == 1 else "medium"
    else:
        sklearn_hits = _detect_sklearn_calls(code)
        if sklearn_hits:
            # Classical ML: use a CPU-equivalent GPU-hours budget that
            # scales with `n_estimators` (when present) and the number of
            # detected fit calls. These numbers are illustrative — they
            # let the user see the relative cost of, say, a 2000-tree
            # RandomForest vs a LogisticRegression. Compared to deep
            # learning the absolute footprint is small, but it isn't 0.
            n_estimators = _detect_int(code, r"n_estimators\s*=\s*(\d+)") or 100
            base_hours_per_call = max(0.05, min(8.0, n_estimators / 200.0))
            full_train_gpu_hours = base_hours_per_call * len(sklearn_hits)
            params_b = 0.001  # token-sized cost — visible but small
            confidence = "medium"
            for line_no, name in sklearn_hits:
                key = (line_no, f"sklearn:{name}")
                if key not in {(p.line, p.pattern) for p in patterns}:
                    patterns.append(
                        DetectedPatternLite(
                            line=line_no,
                            pattern=f"sklearn:{name}",
                            impact="medium",
                        )
                    )
        else:
            # Heuristic fallback when no model is matched.
            params_b, full_train_gpu_hours = 0.1, 5.0
            confidence = "low"

    # Heuristic: if code uses `from_pretrained` only (inference / fine-tune),
    # assume ~5% of full pre-training compute. With Trainer/model.fit we scale
    # by epochs as a rough multiplier.
    is_full_train = any(p.pattern in {"trainer.train", "Trainer(", "model.fit"} for p in patterns)
    if full_train_gpu_hours <= 0:
        # Closed-API models have no public pre-training cost. Charge a fixed
        # inference-style budget so we still produce a meaningful CO2 number.
        gpu_hours = API_INFERENCE_GPU_HOURS_FALLBACK * (1.0 if not is_full_train else max(1.0, epochs))
    else:
        fraction = 0.05 if not is_full_train else min(1.0, 0.1 * epochs)
        gpu_hours = full_train_gpu_hours * fraction
    gpu_hours = round(gpu_hours, 3)
    # Batch-size effect (smaller batches → more wall time per epoch, modest).
    gpu_hours = round(gpu_hours * (32.0 / max(batch_size, 1)) ** 0.25, 3)

    kwh = round(gpu_hours * A100_KW, 3)
    co2_now = round(kwh * current_gco2_kwh, 1)
    co2_optimal = round(kwh * optimal_gco2_kwh, 1)

    workload = _detect_workload_practices(code)

    return EstimateResult(
        co2_grams_now=co2_now,
        co2_grams_optimal=co2_optimal,
        gpu_hours=gpu_hours,
        kwh_estimated=kwh,
        confidence=confidence,
        detected_patterns=patterns,
        workload_practices=workload,
    )


# ---------------------------------------------------------------------------
# Workload / infra practices (high-scope advisory layer)
# ---------------------------------------------------------------------------

# (id, regex, label, impact, rationale) — first match per id wins.
_WORKLOAD_RULES: List[Tuple[str, re.Pattern, str, str, str]] = [
    (
        "fsdp",
        re.compile(r"\b(?:FullyShardedDataParallel|FSDP)\b"),
        "FSDP / fully-sharded",
        "high",
        "Shards optimizer and weights across GPUs — cuts per-device memory so you can "
        "train larger models without proportional power on one card (orchestration overhead dominates on tiny jobs).",
    ),
    (
        "ddp",
        re.compile(r"\bDistributedDataParallel\b"),
        "DistributedDataParallel",
        "high",
        "Data-parallel scaling improves wall-clock; total cluster power rises but work finishes sooner — watch stragglers and idle GPUs.",
    ),
    (
        "flash_attn",
        re.compile(r"\bflash_attn|FlashAttention|flash_attention_2\b", re.I),
        "FlashAttention-style kernels",
        "medium",
        "Fused attention cuts HBM traffic — often a large win on long-sequence Transformers for the same quality step.",
    ),
    (
        "autocast",
        re.compile(r"\b(?:torch\.)?autocast\s*\("),
        "torch.autocast",
        "high",
        "Automatic mixed precision lowers memory traffic and usually increases throughput; validate loss scaling / numerics for your task.",
    ),
    (
        "grad_scaler",
        re.compile(r"\bGradScaler\s*\("),
        "GradScaler (AMP)",
        "medium",
        "Classic AMP pairing with autocast for stable underflow handling in low-precision matmuls.",
    ),
    (
        "torch_compile",
        re.compile(r"\b(?:torch\.)?compile\s*\("),
        "torch.compile",
        "medium",
        "Graph capture and fusion can shrink steady-state step time after warm-up — measure on your real batch shapes.",
    ),
    (
        "grad_checkpoint",
        re.compile(
            r"gradient_checkpointing|enable_gradient_checkpointing|gradient_checkpointing_enable",
            re.I,
        ),
        "Gradient checkpointing",
        "high",
        "Recomputes activations to save memory — longer steps but can unlock bigger models or batches on the same GPU budget.",
    ),
    (
        "quantization",
        re.compile(r"load_in_4bit|load_in_8bit|BitsAndBytesConfig|\bbnb\b", re.I),
        "bitsandbytes / load_in_4bit|8bit",
        "high",
        "Low-bit weights shrink memory and data movement; re-check accuracy and latency on your eval suite.",
    ),
    (
        "dataparallel",
        re.compile(r"\bDataParallel\s*\("),
        "nn.DataParallel",
        "low",
        "Single-process multi-GPU is often inefficient; prefer DistributedDataParallel for better scaling and power proportionality.",
    ),
    (
        "matmul_precision",
        re.compile(r"set_float32_matmul_precision\s*\("),
        "set_float32_matmul_precision",
        "low",
        "TensorCore-friendly matmul settings trade ultra-conservative FP32 for throughput on Hopper/Ampere-class GPUs.",
    ),
]


def _detect_workload_practices(code: str) -> List[WorkloadPracticeLite]:
    seen: set[str] = set()
    out: List[WorkloadPracticeLite] = []
    for idx, raw in enumerate(code.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for pid, pattern, label, impact, rationale in _WORKLOAD_RULES:
            if pid in seen:
                continue
            if pattern.search(line):
                seen.add(pid)
                out.append(
                    WorkloadPracticeLite(
                        id=pid,
                        line=idx,
                        label=label,
                        impact=impact,
                        rationale=rationale,
                    )
                )
    return out


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _detect_models(code: str) -> List[str]:
    """Detect catalog-known models *actually used* in the script.

    Reuses the same usage-aware extractor as `app.services.rag` so that
    the estimator agrees with `suggest_greener` about what was loaded
    (kwargs like ``model='gpt-4'``, assignments like
    ``MODEL_ID = "..."``, and known calls like ``from_pretrained(...)``,
    ``pipeline(...)``, ``ChatOpenAI(...)`` etc.).

    Returned list is **deduplicated** by catalog key so that loading the
    same model multiple times (e.g. ``AutoTokenizer`` + ``AutoModel`` of
    the same id, or repeated ``from_pretrained`` calls in a notebook)
    counts as a single hit and stays at ``confidence='high'``.

    When the extractor saw a model use but no catalog key matches the
    full id (typical for f-strings whose variable component we couldn't
    statically resolve, e.g. ``f"meta-llama/Llama-{size}"``), we fall
    back to the **largest** catalog entry whose key is contained in the
    *constant prefix* of the extracted id. This is a worst-case estimate
    for the family — better than the generic 0.1 B placeholder.
    """
    # Lazy import to avoid module-load order coupling. `rag` does not
    # import `carbon_estimator`, so this is safe.
    from app.services.rag import (  # noqa: WPS437
        _BEDROCK_VENDOR_PREFIXES,
        _extract_model_hits,
    )

    found: List[str] = []
    seen: set[str] = set()
    unresolved_prefixes: List[str] = []

    for _line, _snippet, model_id in _extract_model_hits(code):
        mid = model_id.lower().split(":", 1)[0]
        for vendor in _BEDROCK_VENDOR_PREFIXES:
            if mid.startswith(vendor):
                mid = mid[len(vendor):]
                break
        bare = mid.split("/", 1)[-1]
        bare_norm = bare.replace("_", "-")
        mid_norm = mid.replace("_", "-")
        matched = False
        for key in _CATALOG_KEYS_ORDERED:
            if (
                key in mid
                or key in bare
                or key in mid_norm
                or key in bare_norm
            ):
                if key not in seen:
                    seen.add(key)
                    found.append(key)
                matched = True
                break
        if not matched:
            # Family fallback uses the *bare* normalised name so the
            # prefix's first 4 chars line up with catalog keys (which
            # never include an `org/` prefix).
            unresolved_prefixes.append(bare_norm)

    if not found and unresolved_prefixes:
        # Family fallback: the biggest catalog entry whose key starts the
        # same way as the extracted prefix. Picks the worst case.
        best_key: Optional[str] = None
        best_params = -1.0
        for prefix in unresolved_prefixes:
            for key, (params_b, _hours, _family) in MODEL_CATALOG.items():
                # Use 4-char overlap to avoid `bert-` matching `bertha-` etc.
                if len(prefix) < 4:
                    continue
                if prefix.startswith(key[:4]) or key.startswith(prefix[:4]):
                    if params_b > best_params:
                        best_params = params_b
                        best_key = key
        if best_key is not None:
            found.append(best_key)

    return found


# ---------------------------------------------------------------------------
# Classical-ML (sklearn / XGBoost / LightGBM) detection
# ---------------------------------------------------------------------------

_SKLEARN_CALL_RE = re.compile(
    r"\b(?:RandomForest(?:Classifier|Regressor)|GradientBoosting(?:Classifier|Regressor)|"
    r"HistGradientBoosting(?:Classifier|Regressor)|"
    r"XGB(?:Classifier|Regressor|RFClassifier|RFRegressor)|"
    r"LGBM(?:Classifier|Regressor)|CatBoost(?:Classifier|Regressor)|"
    r"LogisticRegression|LinearRegression|Ridge|Lasso|ElasticNet|"
    r"SVC|SVR|LinearSVC|LinearSVR|"
    r"KNeighbors(?:Classifier|Regressor)|"
    r"DecisionTree(?:Classifier|Regressor)|"
    r"MLPClassifier|MLPRegressor|"
    r"AdaBoost(?:Classifier|Regressor)|"
    r"ExtraTrees(?:Classifier|Regressor)|"
    r"BaggingClassifier|BaggingRegressor|"
    r"KMeans|DBSCAN|GaussianMixture)\s*\(",
)


def _detect_sklearn_calls(code: str) -> List[Tuple[int, str]]:
    """Return [(line_no, callable_name), ...] for every classical-ML
    constructor or `lightgbm.train(...)` invocation."""
    out: List[Tuple[int, str]] = []
    for idx, raw in enumerate(code.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for m in _SKLEARN_CALL_RE.finditer(line):
            # Drop the trailing `(` that the regex captured for boundary.
            name = m.group(0).rstrip("(").strip()
            out.append((idx, name))
    return out


def _detect_patterns(code: str) -> List[DetectedPatternLite]:
    patterns: List[DetectedPatternLite] = []
    seen: set[Tuple[int, str]] = set()
    for idx, raw_line in enumerate(code.splitlines(), start=1):
        line = raw_line.strip()
        for needle, impact in PATTERN_IMPACT.items():
            if needle in line:
                key = (idx, needle)
                if key in seen:
                    continue
                seen.add(key)
                patterns.append(DetectedPatternLite(line=idx, pattern=needle, impact=impact))
    return patterns


def _detect_int(code: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, code)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _detect_int_all(code: str, pattern: str) -> List[int]:
    """Return every integer captured by `pattern` (1st group), in order."""
    out: List[int] = []
    for m in re.finditer(pattern, code):
        try:
            out.append(int(m.group(1)))
        except (TypeError, ValueError):
            continue
    return out
