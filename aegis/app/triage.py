from __future__ import annotations

from collections import Counter

from ..domain.schemas import (
    Evidence,
    EvidenceStack,
    SignalSummary,
    TelemetrySummary,
    ToolCallRecord,
)
from ..mcp.gateway import MCPToolGateway


class TriageAgent:
    """Side-channel summarisation. It calls the diagnostic tools through the MCP
    gateway, and parses the raw tool output into compact signals and evidence
    outside the model. The model only ever sees the structured summaries, and
    never the raw logs."""

    _DEFAULT_TOOLS = ["fetch_metrics", "query_logs", "get_recent_deployments"]

    def run(
        self,
        incident_id: str,
        gateway: MCPToolGateway,
        *,
        scenario: str,
        service: str,
        recipe: list[dict] | None = None,
    ) -> tuple[TelemetrySummary, EvidenceStack, list[ToolCallRecord]]:
        signals: list[SignalSummary] = []
        evidence: list[Evidence] = []
        tool_calls: list[ToolCallRecord] = []

        # Runbook evidence_recipe decides the tools. No recipe means use defaults.
        tools = [str(step.get("tool")) for step in recipe] if recipe else list(self._DEFAULT_TOOLS)
        done: set[str] = set()
        args = {"scenario": scenario, "service": service}
        for tool in tools:
            if tool in done:
                continue
            done.add(tool)
            if tool == "fetch_metrics":
                result, record = gateway.call("fetch_metrics", args, incident_id=incident_id)
                tool_calls.append(record)
                self._summarize_metrics(service, result.series, signals, evidence)
            elif tool == "query_logs":
                result, record = gateway.call("query_logs", args, incident_id=incident_id)
                tool_calls.append(record)
                self._summarize_logs(service, result.entries, signals, evidence)
            elif tool == "get_recent_deployments":
                result, record = gateway.call("get_recent_deployments", args, incident_id=incident_id)
                tool_calls.append(record)
                self._summarize_deployments(service, result.deployments, signals, evidence)

        return TelemetrySummary(signals=signals), EvidenceStack(items=evidence), tool_calls

    @staticmethod
    def _summarize_metrics(service, series, signals, evidence) -> None:
        metric = next((s for s in series if s.get("name") == "http_5xx_rate"), None)
        if not metric or not metric.get("points"):
            return
        baseline = float(metric.get("baseline", 0.0))
        points = metric["points"]
        peak = max(points, key=lambda p: p["value"])
        threshold = max(baseline * 3, 0.02)
        first_bad = next((p for p in points if p["value"] > threshold), None)
        signals.append(
            SignalSummary(
                signal_type="metric", service=service,
                summary=f"http_5xx_rate peaked at {peak['value']:.1%} (baseline {baseline:.1%})",
                value=peak["value"], baseline=baseline,
                first_seen=first_bad["ts"] if first_bad else None, last_seen=peak["ts"],
            )
        )
        if peak["value"] > threshold:
            evidence.append(
                Evidence(
                    id="ev_metric_001", kind="error_rate_metric",
                    summary=f"http_5xx_rate peaked at {peak['value']:.1%} (baseline {baseline:.1%})",
                    source_tool="fetch_metrics",
                    observed_at=first_bad["ts"] if first_bad else peak["ts"],
                    data={
                        "peak": peak["value"], "baseline": baseline,
                        "first_bad_ts": first_bad["ts"] if first_bad else None,
                    },
                )
            )

    @staticmethod
    def _summarize_logs(service, entries, signals, evidence) -> None:
        errors = [log for log in (entries or []) if str(log.get("level", "")).upper() == "ERROR"]
        if not errors:
            return
        pattern, count = Counter(log.get("msg", "") for log in errors).most_common(1)[0]
        sample_ids = [f"log_{i:03d}" for i in range(1, min(len(errors), 5) + 1)]
        first_seen = min(log["ts"] for log in errors)
        last_seen = max(log["ts"] for log in errors)
        signals.append(
            SignalSummary(
                signal_type="log_pattern", service=service, summary=pattern,
                count=count, first_seen=first_seen, last_seen=last_seen, sample_ids=sample_ids,
            )
        )
        evidence.append(
            Evidence(
                id="ev_log_001", kind="application_error_logs",
                summary=f"{count}x '{pattern}'", source_tool="query_logs",
                observed_at=first_seen, refs=sample_ids,
                data={"pattern": pattern, "count": count},
            )
        )

    @staticmethod
    def _summarize_deployments(service, deployments, signals, evidence) -> None:
        if not deployments:
            return
        latest = sorted(deployments, key=lambda d: d["deployed_at"])[-1]
        signals.append(
            SignalSummary(
                signal_type="deployment", service=service,
                summary=f"revision {latest['revision']} deployed at {latest['deployed_at']}",
                last_seen=latest["deployed_at"],
            )
        )
        evidence.append(
            Evidence(
                id="ev_deploy_001", kind="recent_deployment",
                summary=f"revision {latest['revision']} deployed at {latest['deployed_at']}",
                source_tool="get_recent_deployments", observed_at=latest["deployed_at"],
                data={
                    "revision": latest["revision"],
                    "previous_stable": latest.get("previous_stable"),
                    "deployed_at": latest["deployed_at"],
                },
            )
        )
