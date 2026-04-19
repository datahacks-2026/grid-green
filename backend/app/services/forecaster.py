"""48h grid carbon-intensity forecaster.

Tiered implementation per `a.md` §8.3 and §6 (graceful degradation):

1. **Prophet (preferred)** — if `prophet` is importable, fit a per-region
   Prophet model on the last 30 days of hourly history and predict 48h.
   Models are cached per region for `GRID_CACHE_TTL_S` seconds so the
   request path stays fast.
2. **Seasonal-naive fallback** — if Prophet is unavailable or fails, use
   the hour-of-day mean over the last 7 days. Same return shape; demo
   never breaks.

Both paths read history through `storage.fetch_recent`, which itself
falls back from Snowflake → SQLite. No path in here knows which storage
backend is live.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from app.config import get_settings
from app.services import storage
from app.services.cache import TTLCache
from app.services.eia_client import fetch_region
from app.services.regions import REGION_META

logger = logging.getLogger(__name__)

_settings = get_settings()
_forecast_cache = TTLCache(ttl_s=_settings.grid_cache_ttl_s)
_prophet_usable: bool = True


# ---------------------------------------------------------------------------
# History bootstrap
# ---------------------------------------------------------------------------

def _ensure_history(region: str) -> List[Tuple[datetime, float]]:
    rows = storage.fetch_recent(region, limit=24 * 30)
    if rows:
        return rows
    points = fetch_region(region, days=30)
    storage.insert_eia_rows(
        [(p.ts_utc.isoformat(), region, "carbon_intensity", p.value) for p in points]
    )
    return [(p.ts_utc, p.value) for p in points]


def latest_intensity(region: str) -> Tuple[datetime, float]:
    rows = _ensure_history(region)
    return rows[-1]


def trend(region: str, lookback_hours: int = 6) -> str:
    rows = _ensure_history(region)
    tail = rows[-lookback_hours:]
    if len(tail) < 2:
        return "flat"
    delta = tail[-1][1] - tail[0][1]
    pct = delta / max(tail[0][1], 1.0)
    if pct > 0.03:
        return "rising"
    if pct < -0.03:
        return "falling"
    return "flat"


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def forecast_48h(region: str) -> List[Tuple[datetime, float]]:
    """Return 48 hourly forecast points starting at the next full hour."""
    cached = _forecast_cache.get(region)
    if cached is not None:
        return cached

    rows = _ensure_history(region)
    points = _prophet_forecast(rows) if _prophet_available() else None
    if points is None:
        points = _seasonal_naive(region, rows)

    _forecast_cache.set(region, points)
    return points


def _prophet_available() -> bool:
    global _prophet_usable
    if not _prophet_usable:
        return False
    try:
        import prophet  # noqa: F401
        return True
    except Exception:
        _prophet_usable = False
        return False


def _prophet_forecast(rows: List[Tuple[datetime, float]]) -> List[Tuple[datetime, float]] | None:
    global _prophet_usable
    if len(rows) < 48:
        return None
    try:
        import pandas as pd
        from prophet import Prophet

        df = pd.DataFrame(
            {"ds": [r[0].replace(tzinfo=None) for r in rows], "y": [r[1] for r in rows]}
        )
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            interval_width=0.8,
        )
        # Suppress cmdstanpy's noisy stdout during fit.
        import logging as _logging
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)
        model.fit(df)

        last_ts = rows[-1][0]
        future_start = (last_ts + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        future = pd.DataFrame(
            {"ds": [future_start + timedelta(hours=i) for i in range(48)]}
        )
        forecast = model.predict(future)
        return [
            (
                future_start.replace(tzinfo=timezone.utc) + timedelta(hours=i),
                float(max(5.0, forecast["yhat"].iloc[i])),
            )
            for i in range(48)
        ]
    except Exception as exc:  # noqa: BLE001
        _prophet_usable = False
        logger.warning("Prophet forecast failed (%s); using seasonal-naive", exc)
        return None


def _seasonal_naive(
    region: str, rows: List[Tuple[datetime, float]]
) -> List[Tuple[datetime, float]]:
    if not rows:
        meta = REGION_META[region]
        base = meta.typical_gco2_kwh
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return [(start + timedelta(hours=i), base) for i in range(48)]

    by_hour: dict[int, list[float]] = {h: [] for h in range(24)}
    cutoff = rows[-1][0] - timedelta(days=7)
    for ts, value in rows:
        if ts >= cutoff:
            by_hour[ts.hour].append(value)
    hour_means = {
        h: (sum(v) / len(v)) if v else REGION_META[region].typical_gco2_kwh
        for h, v in by_hour.items()
    }

    last_ts = rows[-1][0]
    start = (last_ts + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return [
        (
            start + timedelta(hours=i),
            round(hour_means[(start + timedelta(hours=i)).hour], 2),
        )
        for i in range(48)
    ]


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

def find_clean_window(
    region: str,
    hours_needed: int = 4,
    max_delay_hours: int = 48,
) -> Tuple[datetime, float, float, float, List[Tuple[datetime, float]]]:
    """Return (optimal_start, expected_gco2_kwh, current_gco2_kwh,
    co2_savings_pct, forecast_48h)."""
    forecast = forecast_48h(region)[: max(max_delay_hours, hours_needed)]
    _, current = latest_intensity(region)

    if len(forecast) < hours_needed:
        avg = sum(v for _, v in forecast) / max(len(forecast), 1)
        return forecast[0][0], round(avg, 2), current, 0.0, forecast

    best_start_idx = 0
    best_avg = float("inf")
    for i in range(0, len(forecast) - hours_needed + 1):
        window = forecast[i : i + hours_needed]
        avg = sum(v for _, v in window) / hours_needed
        if avg < best_avg:
            best_avg = avg
            best_start_idx = i

    optimal_start = forecast[best_start_idx][0]
    expected = round(best_avg, 2)
    savings = round(max(0.0, (current - expected) / current * 100.0), 1) if current else 0.0
    return optimal_start, expected, current, savings, forecast


def invalidate_cache(region: str | None = None) -> None:
    """Manual cache flush hook (used by ingest scripts after a fresh load)."""
    if region is None:
        _forecast_cache.clear()
    else:
        _forecast_cache._store.pop(region, None)  # type: ignore[attr-defined]
