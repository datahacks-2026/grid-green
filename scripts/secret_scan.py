#!/usr/bin/env python3
"""Lightweight pre-commit secret scanner for staged files."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


PATTERNS = [
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    # Provider-specific tokens
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                 # OpenAI / generic
    re.compile(r"AKIA[0-9A-Z]{16}"),                    # AWS access key
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),               # Google / Gemini API key
    re.compile(r"dapi[a-f0-9]{32}"),                    # Databricks PAT
    re.compile(r"wandb_v1_[A-Za-z0-9]{20,}"),           # Weights & Biases
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),        # Slack
    re.compile(r"hf_[A-Za-z0-9]{30,}"),                 # HuggingFace
    # Generic KEY=VALUE assignments (quoted OR unquoted — .env files use unquoted)
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|passwd|private[_-]?key|access[_-]?key)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_\-=.]{16,}[\"']?"
    ),
]

ALLOW_HINTS = (
    "<your_",
    "example",
    "sample",
    "placeholder",
    "dummy",
    "changeme",
)


def scan_file(path: pathlib.Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for lineno, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if any(h in low for h in ALLOW_HINTS):
            continue
        # Skip code that passes config/settings objects — not literal secrets.
        if re.search(r"(settings\.|os\.environ|getenv\(|environ\.get)", line):
            continue
        if any(p.search(line) for p in PATTERNS):
            findings.append((lineno, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    blocked = False
    for raw in args.files:
        path = pathlib.Path(raw)
        if not path.is_file():
            continue
        findings = scan_file(path)
        if not findings:
            continue
        blocked = True
        print(f"[secret-scan] potential secret(s) in {path}:")
        for lineno, snippet in findings[:5]:
            preview = snippet[:140]
            print(f"  line {lineno}: {preview}")
        if len(findings) > 5:
            print(f"  ... and {len(findings) - 5} more")

    if blocked:
        print(
            "\nCommit blocked by secret-scan. "
            "Remove secrets or replace with placeholders."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
