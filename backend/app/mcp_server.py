"""MCP server exposing GridGreen tools to Claude Desktop / Cursor / Claude Code.

Run standalone:   python -m app.mcp_server
Claude Desktop config — see /mcp page in the UI.

Person B owns the MCP wiring. Person A's tools are imported lazily so this
file works even if A's modules aren't merged yet — they show up as stubs
that say "not yet wired" until A pushes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.routes.suggest import suggest_greener
from app.schemas import SuggestRequest

logger = logging.getLogger(__name__)

mcp = FastMCP("gridgreen")


@mcp.tool()
def suggest_greener_tool(code: str) -> str:
    """Given ML training code, return greener model alternatives + reasoning."""
    resp = suggest_greener(SuggestRequest(code=code))
    return resp.model_dump_json(indent=2)


@mcp.tool()
def get_scorecard(session_id: str) -> str:
    """Return the cumulative carbon savings for a session."""
    from app.services import scorecard_store

    return scorecard_store.get(session_id).model_dump_json(indent=2)


# ---- Person A's tools — wired lazily so this file always imports cleanly. ----

def _safe_call(import_path: str, fn_name: str, payload: dict[str, Any]) -> str:
    try:
        module = __import__(import_path, fromlist=[fn_name])
        fn = getattr(module, fn_name)
        result = fn(**payload)
        if hasattr(result, "model_dump_json"):
            return result.model_dump_json(indent=2)
        return json.dumps(result, default=str, indent=2)
    except Exception as exc:
        logger.warning("Tool %s.%s not yet wired: %s", import_path, fn_name, exc)
        return json.dumps(
            {"status": "stub", "tool": fn_name, "reason": str(exc)}, indent=2
        )


@mcp.tool()
def estimate_carbon(code: str, region: str) -> str:
    """Person A: estimate CO2 grams now vs optimal for the given code."""
    return _safe_call(
        "app.routes.estimate", "estimate_carbon",
        {"req": {"code": code, "region": region}},
    )


@mcp.tool()
def check_grid(region: str) -> str:
    """Person A: current grid carbon intensity (gCO2/kWh) for region."""
    return _safe_call("app.routes.grid", "check_grid", {"region": region})


@mcp.tool()
def find_clean_window(region: str, hours_needed: int = 4, max_delay_hours: int = 48) -> str:
    """Person A: find the lowest-carbon window in the next N hours."""
    return _safe_call(
        "app.routes.grid", "find_clean_window",
        {
            "region": region,
            "hours_needed": hours_needed,
            "max_delay_hours": max_delay_hours,
        },
    )


if __name__ == "__main__":
    mcp.run()
