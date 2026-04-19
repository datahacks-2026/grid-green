"""Scripps Heat Map ingest + read (a.md §8.4, §8.12).

Loads a CSV slice of the UCSD campus mobile-weather-station data and
exposes a tiny aggregate API. The point of this module is to satisfy the
**Scripps prize** dataset requirement with a clean integration story —
the aggregate is shown alongside the EIA grid intensity in the UI as
*context*, never as the primary carbon signal.

The CSV at `backend/data/sample_heatmap.csv` is a **synthetic stand-in**
so the demo path works even if the real Scripps data hasn't been
downloaded yet. To use the real Scripps mobile-weather data, replace
that file with one that has the same columns
(`ts_utc, station_id, temperature_c, relative_humidity`) and restart
the backend — `load_csv()` is content-agnostic, no code change needed.

Until the real CSV is dropped in place, the project should NOT claim
the Scripps $1,500 prize: the endpoint works, but the data is
synthetic. README §3 + the Devpost submission must reflect that.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


DEFAULT_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "sample_heatmap.csv"


@dataclass
class HeatPoint:
    ts_utc: datetime
    station_id: str
    temperature_c: float
    relative_humidity: float


@dataclass
class HeatSummary:
    n_points: int
    n_stations: int
    earliest: datetime | None
    latest: datetime | None
    mean_temperature_c: float | None
    mean_relative_humidity: float | None


def load_csv(path: Path | None = None) -> List[HeatPoint]:
    csv_path = path or DEFAULT_CSV
    if not csv_path.exists():
        logger.warning("heatmap CSV missing at %s; returning empty", csv_path)
        return []
    rows: List[HeatPoint] = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                ts = datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                rows.append(
                    HeatPoint(
                        ts_utc=ts,
                        station_id=r["station_id"],
                        temperature_c=float(r["temperature_c"]),
                        relative_humidity=float(r["relative_humidity"]),
                    )
                )
            except (KeyError, ValueError) as exc:  # noqa: PERF203
                logger.debug("skipping bad heatmap row: %s", exc)
    return rows


def summarize(points: List[HeatPoint]) -> HeatSummary:
    if not points:
        return HeatSummary(
            n_points=0,
            n_stations=0,
            earliest=None,
            latest=None,
            mean_temperature_c=None,
            mean_relative_humidity=None,
        )
    temps = [p.temperature_c for p in points]
    rhs = [p.relative_humidity for p in points]
    return HeatSummary(
        n_points=len(points),
        n_stations=len({p.station_id for p in points}),
        earliest=min(p.ts_utc for p in points),
        latest=max(p.ts_utc for p in points),
        mean_temperature_c=sum(temps) / len(temps),
        mean_relative_humidity=sum(rhs) / len(rhs),
    )
