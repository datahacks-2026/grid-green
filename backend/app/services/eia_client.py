"""EIA Open Data client + offline mock generator.

Goal: a function `fetch_region(region)` that returns
[(ts_utc, value_gco2_kwh), ...] for the last N days, regardless of whether
an EIA key is configured. When `EIA_API_KEY` is missing, a deterministic
synthetic series is generated so the demo path keeps working end-to-end.

The exact EIA series choice is documented in `backend/scripts/ingest_eia.py`.
For the hackathon we treat a CO2-emissions-rate-style series as the primary
"carbon intensity" signal. If you swap to an indirect proxy (mix-derived),
update this docstring + Devpost.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import httpx

from app.config import get_settings
from app.services.regions import REGION_META, is_supported

logger = logging.getLogger(__name__)


EIA_BASE = "https://api.eia.gov/v2"
EIA_TIMEOUT_S = 60.0          # EIA endpoints can be slow under load
EIA_CHUNK_DAYS = 7             # smaller windows = far fewer 504s
EIA_RETRIES = 2                # per chunk
EIA_BACKOFF_S = 2.0


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:4] + "…" + key[-3:]


@dataclass(frozen=True)
class EiaPoint:
    ts_utc: datetime
    value: float


def fetch_region(region: str, days: int = 30) -> List[EiaPoint]:
    """Return hourly carbon-intensity-like values (gCO2/kWh) for `region`.

    Strategy:
    - If `EIA_API_KEY` is set, fetch in `EIA_CHUNK_DAYS`-day windows with
      retry+backoff. Even if some windows fail, partial coverage is better
      than a full mock series — we backfill the gap from the mock generator
      so the forecaster always sees a complete continuous timeline.
    - If the key is missing OR every chunk fails, return a deterministic
      synthetic series so the demo path keeps working.
    """
    if not is_supported(region):
        raise ValueError(f"Unsupported region: {region}")

    settings = get_settings()
    if not settings.eia_api_key:
        return _mock_series(region, days)

    try:
        live = _fetch_from_api(region, days, settings.eia_api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "EIA fetch failed for %s (key=%s): %s — using mock series",
            region, _mask_key(settings.eia_api_key), exc,
        )
        return _mock_series(region, days)

    if not live:
        logger.warning("EIA returned 0 points for %s — using mock series", region)
        return _mock_series(region, days)

    # Backfill any holes (network gaps) from the deterministic mock series so
    # downstream consumers always see a continuous hourly timeline.
    return _merge_with_mock(region, days, live)


def _fetch_from_api(region: str, days: int, api_key: str) -> List[EiaPoint]:
    """Fetch generation-by-fuel in small windows and derive intensity.

    EIA's `fuel-type-data` endpoint can 504 / time out for 30-day pulls per
    region. Splitting into 7-day chunks with 2 retries kills almost all of
    those failures and lets us return partial data when one chunk is dead.
    """
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)

    rows: list = []
    failures = 0
    cursor = start
    with httpx.Client(timeout=EIA_TIMEOUT_S) as client:
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=EIA_CHUNK_DAYS), end)
            chunk_rows = _fetch_chunk(client, region, api_key, cursor, chunk_end)
            if chunk_rows is None:
                failures += 1
            else:
                rows.extend(chunk_rows)
            cursor = chunk_end

    if not rows:
        raise RuntimeError(f"all EIA chunks failed (failures={failures})")
    if failures:
        logger.info("EIA %s: %d chunks failed, %d rows recovered", region, failures, len(rows))

    return _derive_intensity(rows, region)


def _fetch_chunk(
    client: httpx.Client,
    region: str,
    api_key: str,
    start: datetime,
    end: datetime,
) -> list | None:
    url = f"{EIA_BASE}/electricity/rto/fuel-type-data/data/"
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": region,
        "start": start.strftime("%Y-%m-%dT%H"),
        "end": end.strftime("%Y-%m-%dT%H"),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }

    for attempt in range(1, EIA_RETRIES + 2):
        try:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json().get("response", {}).get("data", []) or []
        except Exception as exc:  # noqa: BLE001
            if attempt > EIA_RETRIES:
                logger.warning(
                    "EIA chunk %s %s→%s failed after %d attempts: %s",
                    region, start.date(), end.date(), attempt, exc,
                )
                return None
            sleep_s = EIA_BACKOFF_S * attempt
            logger.info(
                "EIA chunk %s %s→%s attempt %d failed (%s); retrying in %.1fs",
                region, start.date(), end.date(), attempt, exc, sleep_s,
            )
            time.sleep(sleep_s)
    return None


def _merge_with_mock(region: str, days: int, live: List[EiaPoint]) -> List[EiaPoint]:
    """Use live data where present; fill gaps with deterministic mock points."""
    by_ts = {p.ts_utc: p for p in live}
    mock = _mock_series(region, days)
    merged = [by_ts.get(p.ts_utc, p) for p in mock]
    return merged


# Approximate emission factors (gCO2 per kWh) by fuel type for derivation.
# Sources: IPCC AR5 / EIA published averages. Used as a hackathon proxy only.
EMISSION_FACTORS = {
    "COL": 1000.0,   # coal
    "NG": 450.0,     # natural gas
    "OIL": 800.0,    # petroleum
    "NUC": 12.0,     # nuclear
    "WAT": 24.0,     # hydro
    "WND": 11.0,     # wind
    "SUN": 45.0,     # solar
    "GEO": 38.0,     # geothermal
    "BIO": 230.0,    # biomass
    "OTH": 500.0,    # other
}


def _derive_intensity(rows: list, region: str) -> List[EiaPoint]:
    """Group rows by hour, compute generation-weighted gCO2/kWh."""
    by_hour: dict[str, dict[str, float]] = {}
    for row in rows:
        period = row.get("period")
        fuel = row.get("fueltype") or row.get("type") or "OTH"
        try:
            value = float(row.get("value", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not period:
            continue
        bucket = by_hour.setdefault(period, {})
        bucket[fuel] = bucket.get(fuel, 0.0) + value

    points: List[EiaPoint] = []
    for period, fuels in by_hour.items():
        total = sum(v for v in fuels.values() if v > 0)
        if total <= 0:
            continue
        weighted = sum(
            (v if v > 0 else 0.0) * EMISSION_FACTORS.get(fuel, EMISSION_FACTORS["OTH"])
            for fuel, v in fuels.items()
        )
        intensity = weighted / total
        try:
            ts = datetime.fromisoformat(period)
        except ValueError:
            try:
                ts = datetime.strptime(period, "%Y-%m-%dT%H")
            except ValueError:
                continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        points.append(EiaPoint(ts_utc=ts, value=round(intensity, 2)))

    points.sort(key=lambda p: p.ts_utc)
    if not points:
        raise RuntimeError("Failed to derive intensity from EIA rows")
    return points


def _mock_series(region: str, days: int) -> List[EiaPoint]:
    """Deterministic synthetic series so the demo works without EIA access."""
    meta = REGION_META[region]
    base = meta.typical_gco2_kwh
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)

    points: List[EiaPoint] = []
    cursor = start
    while cursor <= end:
        hour = cursor.hour
        # Diurnal pattern: cleaner overnight (renewables / lower demand),
        # higher in late afternoon. Amplitude scales with base.
        diurnal = math.sin((hour - 14) / 24.0 * 2 * math.pi)
        weekly = math.sin(cursor.timetuple().tm_yday / 7.0 * 2 * math.pi) * 0.05
        value = base * (1.0 + 0.35 * diurnal + weekly)
        # Small region-specific jitter (deterministic).
        jitter = (hash((region, cursor.isoformat())) % 100 - 50) / 1000.0
        value *= 1.0 + jitter
        points.append(EiaPoint(ts_utc=cursor, value=round(max(value, 5.0), 2)))
        cursor += timedelta(hours=1)
    return points
