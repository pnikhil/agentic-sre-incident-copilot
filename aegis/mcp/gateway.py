"""The in-process MCP tool gateway.

The agents call diagnostic tools only through this gateway. It validates the
inputs against the typed schemas, dispatches to the tool implementation, and
records a ToolCallRecord, stamped with the incident_id, for every single call.

These tools are also served over MCP by aegis.mcp.server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from ..domain.schemas import ToolCallRecord
from .schemas import (
    FetchMetricsInput,
    GetDeploymentsInput,
    QueryLogsInput,
    SearchRunbooksInput,
)
from .tools import DiagnosticTools


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MCPToolGateway:
    def __init__(self, tools: DiagnosticTools):
        self.tools = tools
        self._registry = {
            "fetch_metrics": (FetchMetricsInput, tools.fetch_metrics),
            "query_logs": (QueryLogsInput, tools.query_logs),
            "get_recent_deployments": (GetDeploymentsInput, tools.get_recent_deployments),
            "search_runbooks": (SearchRunbooksInput, tools.search_runbooks),
        }

    def list_tools(self) -> list[str]:
        return list(self._registry)

    def call(
        self, name: str, args: dict[str, Any], *, incident_id: str
    ) -> tuple[BaseModel, ToolCallRecord]:
        if name not in self._registry:
            raise KeyError(f"unknown tool: {name}")
        schema, fn = self._registry[name]
        inp = schema(**args)
        started = _now()
        t0 = perf_counter()
        ok = True
        try:
            result = fn(inp)
        except Exception:
            ok = False
            raise
        finally:
            record = ToolCallRecord(
                id="tc_" + uuid.uuid4().hex[:6],
                incident_id=incident_id,
                tool=name,
                args=inp.model_dump(),
                ok=ok,
                started_at=started,
                duration_ms=int((perf_counter() - t0) * 1000),
            )
        return result, record
