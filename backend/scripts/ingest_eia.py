"""One-shot EIA → storage ingest for the five supported regions.

Run from `backend/`:
    python -m scripts.ingest_eia              # all supported regions, last 30d
    python -m scripts.ingest_eia --days 7
    python -m scripts.ingest_eia --region CISO --days 14

If `EIA_API_KEY` is not set in `.env`, a deterministic mock series is written
so the rest of the stack works offline.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

# Allow running as `python scripts/ingest_eia.py` from backend/ too.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services import storage  # noqa: E402
from app.services.eia_client import fetch_region  # noqa: E402
from app.services.regions import SUPPORTED_REGIONS  # noqa: E402

logger = logging.getLogger("ingest_eia")


def ingest(region: str, days: int) -> int:
    points = fetch_region(region, days=days)
    rows = [
        (p.ts_utc.isoformat(), region, "carbon_intensity", p.value)
        for p in points
    ]
    n = storage.insert_eia_rows(rows)
    logger.info("region=%s days=%s points=%d", region, days, n)
    return n


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest EIA hourly data.")
    parser.add_argument("--region", choices=SUPPORTED_REGIONS, default=None)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Silence httpx's per-request URL log — it leaks the API key in the query string.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    targets = [args.region] if args.region else SUPPORTED_REGIONS
    total = 0
    for r in targets:
        total += ingest(r, args.days)
    logger.info("done. total_rows=%d", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
