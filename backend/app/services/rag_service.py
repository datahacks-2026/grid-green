"""Greener-model lookup.

Phase 2: hardcoded lookup table so the slice is demoable standalone.
Phase 5: replace `lookup_alternative` body with a real Snowflake Cortex
similarity search. The function signature stays the same so the route
code (and Person A's MCP tool registration) doesn't change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ModelMatch:
    line: int
    original_snippet: str
    alternative_snippet: str
    carbon_saved_pct: int
    performance_retained_pct: int
    citation: str


_MODEL_PATTERN = re.compile(
    r"""(?P<call>(?:AutoModel(?:ForCausalLM|ForSeq2SeqLM)?|"""
    r"""AutoTokenizer|pipeline|SentenceTransformer)"""
    r"""[A-Za-z_]*\.from_pretrained\(\s*['"](?P<name>[^'"]+)['"]\s*\))""",
    re.MULTILINE,
)


_LOOKUP = {
    "google/flan-t5-xxl": {
        "alternative": "google/flan-t5-large",
        "carbon_saved_pct": 85,
        "performance_retained_pct": 94,
        "citation": "Chung et al., 2022 — Scaling Instruction-Finetuned Language Models.",
    },
    "google/flan-t5-xl": {
        "alternative": "google/flan-t5-large",
        "carbon_saved_pct": 60,
        "performance_retained_pct": 96,
        "citation": "Chung et al., 2022.",
    },
    "meta-llama/Llama-2-70b-hf": {
        "alternative": "meta-llama/Llama-2-13b-hf",
        "carbon_saved_pct": 78,
        "performance_retained_pct": 89,
        "citation": "Touvron et al., 2023 — Llama 2.",
    },
    "bert-large-uncased": {
        "alternative": "distilbert-base-uncased",
        "carbon_saved_pct": 60,
        "performance_retained_pct": 97,
        "citation": "Sanh et al., 2019 — DistilBERT.",
    },
    "openai/whisper-large-v3": {
        "alternative": "openai/whisper-small",
        "carbon_saved_pct": 80,
        "performance_retained_pct": 90,
        "citation": "Radford et al., 2022 — Robust Speech Recognition.",
    },
}


def detect_models(code: str) -> List[ModelMatch]:
    """Scan source for `*.from_pretrained('name')` calls and join with the table."""
    matches: List[ModelMatch] = []
    for line_no, line in enumerate(code.splitlines(), start=1):
        for m in _MODEL_PATTERN.finditer(line):
            name = m.group("name")
            entry = _lookup_alternative(name)
            if entry is None:
                continue
            matches.append(
                ModelMatch(
                    line=line_no,
                    original_snippet=m.group("call"),
                    alternative_snippet=m.group("call").replace(
                        f"'{name}'", f"'{entry['alternative']}'"
                    ).replace(f'"{name}"', f"\"{entry['alternative']}\""),
                    carbon_saved_pct=entry["carbon_saved_pct"],
                    performance_retained_pct=entry["performance_retained_pct"],
                    citation=entry["citation"],
                )
            )
    return matches


def _lookup_alternative(model_name: str) -> Optional[dict]:
    """Phase 2 stub. In Phase 5, replace with Snowflake Cortex VECTOR similarity:

        SELECT alt_model, carbon_saved_pct, performance_retained_pct, citation
        FROM model_alternatives
        ORDER BY VECTOR_COSINE_SIMILARITY(
            embedding,
            SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', :model_name)
        ) DESC
        LIMIT 1;
    """
    return _LOOKUP.get(model_name.lower()) or _LOOKUP.get(model_name)
