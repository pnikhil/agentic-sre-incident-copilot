"""The diagnostic tool implementations.

Kindly note that the same functions back both the in-process MCP gateway and
the FastMCP server, so the tool behaviour and schemas stay identical in both
paths. The tools read only, and never mutate anything.
"""

from __future__ import annotations

from ..ports.runbook_store import RunbookStorePort
from ..ports.telemetry import TelemetryPort
from .schemas import (
    DeploymentsResult,
    FetchMetricsInput,
    GetDeploymentsInput,
    LogsResult,
    MetricsResult,
    QueryLogsInput,
    RunbookSearchResult,
    SearchRunbooksInput,
)


class DiagnosticTools:
    def __init__(self, telemetry: TelemetryPort, runbooks: RunbookStorePort):
        self.telemetry = telemetry
        self.runbooks = runbooks

    def fetch_metrics(self, inp: FetchMetricsInput) -> MetricsResult:
        raw = self.telemetry.fetch(scenario=inp.scenario, service=inp.service)
        return MetricsResult(service=inp.service, series=list(raw.metrics.get("series") or []))

    def query_logs(self, inp: QueryLogsInput) -> LogsResult:
        raw = self.telemetry.fetch(scenario=inp.scenario, service=inp.service)
        return LogsResult(service=inp.service, entries=list(raw.logs or []))

    def get_recent_deployments(self, inp: GetDeploymentsInput) -> DeploymentsResult:
        raw = self.telemetry.fetch(scenario=inp.scenario, service=inp.service)
        deployments = list(raw.deployments.get("deployments") or [])
        return DeploymentsResult(service=inp.service, deployments=deployments)

    def search_runbooks(self, inp: SearchRunbooksInput) -> RunbookSearchResult:
        hits = self.runbooks.search(inp.query, limit=inp.limit)
        docs = [self.runbooks.get(hit.runbook_id) for hit in hits]
        return RunbookSearchResult(hits=[doc for doc in docs if doc is not None])
