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
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Static knowledge — small, hand-curated. Phase 5 replaces with HF lookups.
# ---------------------------------------------------------------------------

# Keys are model id patterns (lowercased substring match).
# Values: (parameters_in_billions, training_gpu_hours_full, family).
MODEL_CATALOG: Dict[str, Tuple[float, float, str]] = {
    # LLM families
    "flan-t5-xxl":     (11.0, 7000.0, "t5"),
    "flan-t5-xl":      (3.0,  2200.0, "t5"),
    "flan-t5-large":   (0.78,  600.0, "t5"),
    "flan-t5-base":    (0.25,  150.0, "t5"),
    "flan-t5-small":   (0.08,   60.0, "t5"),
    "llama-3-70b":     (70.0, 64000.0, "llama"),
    "llama-3-8b":      (8.0,  6500.0, "llama"),
    "llama-2-70b":     (70.0, 60000.0, "llama"),
    "llama-2-13b":     (13.0, 10000.0, "llama"),
    "llama-2-7b":      (7.0,  5000.0, "llama"),
    "mistral-7b":      (7.0,  4500.0, "mistral"),
    "mixtral-8x7b":    (47.0, 24000.0, "mistral"),
    # Vision / encoders
    "bert-large":      (0.34,  300.0, "bert"),
    "bert-base":       (0.11,  120.0, "bert"),
    "distilbert":      (0.066,  60.0, "bert"),
    "vit-large":       (0.30,  280.0, "vit"),
    "vit-base":        (0.086, 100.0, "vit"),
    "resnet50":        (0.025,  20.0, "cnn"),
    "resnet18":        (0.011,   8.0, "cnn"),
    # Diffusion / generative
    "stable-diffusion-xl": (3.5, 6250.0, "diffusion"),
    "stable-diffusion":    (0.86, 1500.0, "diffusion"),
}

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


@dataclass
class EstimateResult:
    co2_grams_now: float
    co2_grams_optimal: float
    gpu_hours: float
    kwh_estimated: float
    confidence: str
    detected_patterns: List[DetectedPatternLite]


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
    epochs = _detect_int(code, r"epochs\s*=\s*(\d+)") or 1
    batch_size = _detect_int(code, r"batch_size\s*=\s*(\d+)") or 32

    if model_hits:
        # Take the largest detected model as the dominant cost driver.
        params_b, full_train_gpu_hours, _ = max(
            (MODEL_CATALOG[m] for m in model_hits), key=lambda x: x[0]
        )
        confidence = "high" if len(model_hits) == 1 else "medium"
    else:
        # Heuristic fallback when no model is matched.
        params_b, full_train_gpu_hours = 0.1, 5.0
        confidence = "low"

    # Heuristic: if code uses `from_pretrained` only (inference / fine-tune),
    # assume ~5% of full pre-training compute. With Trainer/model.fit we scale
    # by epochs as a rough multiplier.
    is_full_train = any(p.pattern in {"trainer.train", "Trainer(", "model.fit"} for p in patterns)
    fraction = 0.05 if not is_full_train else min(1.0, 0.1 * epochs)
    gpu_hours = round(full_train_gpu_hours * fraction, 3)
    # Batch-size effect (smaller batches → more wall time per epoch, modest).
    gpu_hours = round(gpu_hours * (32.0 / max(batch_size, 1)) ** 0.25, 3)

    kwh = round(gpu_hours * A100_KW, 3)
    co2_now = round(kwh * current_gco2_kwh, 1)
    co2_optimal = round(kwh * optimal_gco2_kwh, 1)

    return EstimateResult(
        co2_grams_now=co2_now,
        co2_grams_optimal=co2_optimal,
        gpu_hours=gpu_hours,
        kwh_estimated=kwh,
        confidence=confidence,
        detected_patterns=patterns,
    )


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

_FROM_PRETRAINED_RE = re.compile(
    r"""from_pretrained\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)


def _detect_models(code: str) -> List[str]:
    found: List[str] = []
    for match in _FROM_PRETRAINED_RE.finditer(code):
        model_id = match.group(1).lower()
        for key in MODEL_CATALOG:
            if key in model_id:
                found.append(key)
                break
    return found


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
