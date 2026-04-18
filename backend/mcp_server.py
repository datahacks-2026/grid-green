"""GridGreen MCP server (Person A — a.md §8.9).

Exposes the same handlers that back the FastAPI HTTP routes as MCP tools
so Claude Desktop (or any MCP client) can call them locally over stdio.

Tools exposed (Person A's slice):

- `estimate_carbon`     — POST /api/estimate_carbon
- `check_grid`          — GET  /api/check_grid
- `find_clean_window`   — GET  /api/find_clean_window
- `suggest_greener`     — POST /api/suggest_greener  (RAG path; Person B
                          can wrap with Gemini NL on the client side)

Run as a subprocess (Claude Desktop will spawn this for you):

    cd backend
    python mcp_server.py

To register with Claude Desktop, drop this into the Claude config file
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

    {
      "mcpServers": {
        "gridgreen": {
          "command": "python",
          "args": ["/abs/path/to/backend/mcp_server.py"],
          "env": {
            "EIA_API_KEY": "…",
            "SQLITE_PATH": "/abs/path/to/backend/data/gridgreen.sqlite"
          }
        }
      }
    }

Then restart Claude Desktop. Person B's `/mcp` page shows this same
snippet to end users.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# Allow `python mcp_server.py` from backend/.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.services import carbon_estimator, forecaster, rag  # noqa: E402
from app.services.regions import is_supported  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("gridgreen-mcp")

mcp = FastMCP("gridgreen")


@mcp.tool()
def check_grid(region: str = "CISO") -> dict[str, Any]:
    """Current carbon intensity (gCO2/kWh) and trend for a US balancing authority.

    `region` must be one of: CISO, ERCO, PJM, MISO, NYIS.
    """
    if not is_supported(region):
        return {"error": f"Unsupported region: {region}"}
    ts, value = forecaster.latest_intensity(region)
    return {
        "region": region,
        "current_gco2_kwh": round(value, 2),
        "trend": forecaster.trend(region),
        "last_updated": ts.isoformat(),
    }


@mcp.tool()
def find_clean_window(
    region: str = "CISO",
    hours_needed: int = 4,
    max_delay_hours: int = 48,
) -> dict[str, Any]:
    """Find the cleanest `hours_needed`-hour window in the next `max_delay_hours`.

    Returns the optimal start time, expected gCO2/kWh in that window, the
    current gCO2/kWh for comparison, the % CO2 saved by waiting, and the
    full 48-hour forecast.
    """
    if not is_supported(region):
        return {"error": f"Unsupported region: {region}"}
    optimal_start, expected, current, savings, forecast = forecaster.find_clean_window(
        region=region,
        hours_needed=hours_needed,
        max_delay_hours=max_delay_hours,
    )
    return {
        "optimal_start": optimal_start.isoformat(),
        "expected_gco2_kwh": expected,
        "current_gco2_kwh": round(current, 2),
        "co2_savings_pct": savings,
        "forecast_48h": [
            {"hour": ts.isoformat(), "gco2_kwh": round(v, 2)} for ts, v in forecast
        ],
    }


@mcp.tool()
def estimate_carbon(code: str, region: str = "CISO") -> dict[str, Any]:
    """Estimate the CO2 footprint (grams) of running an ML training script.

    Combines a rules-based code analysis (model lookup + GPU/epoch
    multipliers) with the current and optimal grid carbon intensity for
    the given region.
    """
    if not is_supported(region):
        return {"error": f"Unsupported region: {region}"}
    _, current = forecaster.latest_intensity(region)
    _, optimal_expected, _, _, _ = forecaster.find_clean_window(
        region=region, hours_needed=4, max_delay_hours=48
    )
    result = carbon_estimator.estimate(
        code, current_gco2_kwh=current, optimal_gco2_kwh=optimal_expected
    )
    return {
        "co2_grams_now": result.co2_grams_now,
        "co2_grams_optimal": result.co2_grams_optimal,
        "gpu_hours": result.gpu_hours,
        "kwh_estimated": result.kwh_estimated,
        "confidence": result.confidence,
        "detected_patterns": [
            {"line": p.line, "pattern": p.pattern, "impact": p.impact}
            for p in result.detected_patterns
        ],
    }


@mcp.tool()
def suggest_greener(code: str) -> dict[str, Any]:
    """Suggest greener model alternatives for any HuggingFace models referenced in `code`.

    Uses a curated corpus of ~30 size/quality-paired models; returns up to
    three swap suggestions per detected model with carbon-savings %,
    performance-retained %, citation, and one-line reasoning.
    """
    suggestions = rag.suggest(code, top_k=3)
    return {
        "suggestions": [
            {
                "line": s.line,
                "original_snippet": s.original_snippet,
                "alternative_snippet": s.alternative_snippet,
                "carbon_saved_pct": s.carbon_saved_pct,
                "performance_retained_pct": s.performance_retained_pct,
                "citation": s.citation,
                "reasoning": s.reasoning,
            }
            for s in suggestions
        ]
    }


if __name__ == "__main__":
    logger.info("Starting GridGreen MCP server on stdio…")
    mcp.run()
