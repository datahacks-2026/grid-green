"""Region metadata for the five supported balancing authorities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


SUPPORTED_REGIONS: List[str] = ["CISO", "ERCO", "PJM", "MISO", "NYIS"]


@dataclass(frozen=True)
class RegionMeta:
    code: str
    name: str
    timezone: str
    # Rough mean carbon intensity in gCO2/kWh used as fallback.
    typical_gco2_kwh: float


REGION_META: Dict[str, RegionMeta] = {
    "CISO": RegionMeta("CISO", "California ISO", "America/Los_Angeles", 250.0),
    "ERCO": RegionMeta("ERCO", "ERCOT (Texas)", "America/Chicago", 380.0),
    "PJM": RegionMeta("PJM", "PJM Interconnection", "America/New_York", 380.0),
    "MISO": RegionMeta("MISO", "Midcontinent ISO", "America/Chicago", 430.0),
    "NYIS": RegionMeta("NYIS", "New York ISO", "America/New_York", 230.0),
}


def is_supported(code: str) -> bool:
    return code in REGION_META
