"""A real MCP server exposing the Aegis diagnostic tools over stdio.

Run it with:  python -m aegis.mcp.server

Kindly note that this needs the mcp extra, so please install it first:
    pip install -e ".[mcp]"

This is the reusable module. Any MCP client (for example the MCP Inspector or a
desktop assistant) can connect and call the same diagnostic tools that the Aegis
agents use, which keeps the tool contract in one place.
"""

from __future__ import annotations

from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - only hit when the extra is missing
    raise SystemExit(
        'The MCP SDK is not installed. Kindly run: pip install -e ".[mcp]"'
    ) from exc

from ..adapters.local_fixture_telemetry import LocalFixtureTelemetry
from ..adapters.tfidf_runbook_store import TfidfRunbookStore
from .schemas import (
    FetchMetricsInput,
    GetDeploymentsInput,
    QueryLogsInput,
    SearchRunbooksInput,
)
from .tools import DiagnosticTools

_DATA = Path(__file__).resolve().parents[2] / "data"
_tools = DiagnosticTools(LocalFixtureTelemetry(_DATA), TfidfRunbookStore(_DATA / "runbooks"))

mcp = FastMCP("aegis-diagnostics")


@mcp.tool()
def fetch_metrics(scenario: str, service: str, signal: str = "http_5xx_rate",
                  window: str = "15m") -> dict:
    """Fetch a metric time series for a service."""
    return _tools.fetch_metrics(
        FetchMetricsInput(scenario=scenario, service=service, signal=signal, window=window)
    ).model_dump()


@mcp.tool()
def query_logs(scenario: str, service: str,
               query: str = "ERROR OR 5xx OR exception") -> dict:
    """Query the recent logs for a service."""
    return _tools.query_logs(
        QueryLogsInput(scenario=scenario, service=service, query=query)
    ).model_dump()


@mcp.tool()
def get_recent_deployments(scenario: str, service: str, window: str = "2h") -> dict:
    """List the recent deployments for a service."""
    return _tools.get_recent_deployments(
        GetDeploymentsInput(scenario=scenario, service=service, window=window)
    ).model_dump()


@mcp.tool()
def search_runbooks(query: str, limit: int = 3) -> list[dict]:
    """Search the runbook corpus and return the matching runbooks."""
    result = _tools.search_runbooks(SearchRunbooksInput(query=query, limit=limit))
    return [hit.model_dump() for hit in result.hits]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
