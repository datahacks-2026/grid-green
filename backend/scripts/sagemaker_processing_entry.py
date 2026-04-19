"""Runs *inside* the SageMaker Processing container.

It is intentionally tiny: proves AWS SageMaker executed your code in the
cloud, reads the bundled HF corpus JSON, prints a short summary, and
writes a small report to `/opt/ml/processing/output/summary.json` which
SageMaker then uploads to the configured S3 output prefix.

You do not import this module from FastAPI — it is only invoked remotely.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> None:
    in_dir = Path("/opt/ml/processing/input/data")
    out_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/processing/output"))

    json_files = sorted(in_dir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No *.json files found under {in_dir}")
    corpus_path = json_files[0]

    data = json.loads(corpus_path.read_text())
    entries = data.get("entries", [])
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "n_entries": len(entries),
        "first_from": entries[0]["from"] if entries else None,
        "first_to": entries[0]["to"] if entries else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"ok": True, **summary}, indent=2))


if __name__ == "__main__":
    main()
