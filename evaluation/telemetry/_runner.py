"""Shared CodeCarbon execution helper for runnable evaluation workloads."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

# Repo root on path when workloads are executed as scripts.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def run_with_codecarbon(project_name: str, fn: Callable[[], None]) -> float:
    """Execute ``fn`` under CodeCarbon; return emissions in kg CO2."""
    try:
        from codecarbon import EmissionsTracker
    except ImportError:
        return _cpu_proxy_emissions(fn)

    out_dir = _REPO_ROOT / "evaluation" / "telemetry" / ".codecarbon_runs" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        tracker = EmissionsTracker(
            project_name=project_name,
            output_dir=str(out_dir),
            measure_power_secs=1,
            save_to_file=True,
        )
        tracker.start()
        fn()
        emissions_kg = tracker.stop()
        if emissions_kg is None:
            return 0.0
        return float(emissions_kg)
    except (OSError, PermissionError, SystemError):
        return _cpu_proxy_emissions(fn)


def _cpu_proxy_emissions(fn: Callable[[], None]) -> float:
    """Fallback when CodeCarbon is not installed (CI without extras)."""
    t0 = time.perf_counter()
    fn()
    elapsed_h = (time.perf_counter() - t0) / 3600.0
    # 100 W CPU draw, 250 gCO2/kWh (rough CISO average).
    kwh = elapsed_h * 0.1
    return kwh * 0.25
