from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ..domain.schemas import (
    Evidence,
    EvidenceStack,
    RawTelemetry,
    SignalSummary,
    TelemetrySummary,
    ToolCallRecord,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TriageAgent:
    """Side-channel summarisation. It parses the raw telemetry into compact
    signals and evidence outside the model. The model only ever sees the
    structured summaries, and never the raw logs."""

    def run(
        self, incident_id: str, raw: RawTelemetry
    ) -> tuple[TelemetrySummary, EvidenceStack, list[ToolCallRecord]]:
        signals: list[SignalSummary] = []
        evidence: list[Evidence] = []
        tool_calls: list[ToolCallRecord] = []

        self._summarize_metrics(incident_id, raw, signals, evidence, tool_calls)
        self._summarize_logs(incident_id, raw, signals, evidence, tool_calls)
        self._summarize_deployments(incident_id, raw, signals, evidence, tool_calls)

        return TelemetrySummary(signals=signals), EvidenceStack(items=evidence), tool_calls

    @staticmethod
    def _summarize_metrics(incident_id, raw, signals, evidence, tool_calls) -> None:
        series = raw.metrics.get("series") or []
        metric = next((s for s in series if s.get("name") == "http_5xx_rate"), None)
        tool_calls.append(
            ToolCallRecord(
                id="tc_001", incident_id=incident_id, tool="fetch_metrics",
                args={"signal": "http_5xx_rate"}, started_at=_now(),
            )
        )
        if not metric or not metric.get("points"):
            return
        baseline = float(metric.get("baseline", 0.0))
        points = metric["points"]
        peak = max(points, key=lambda p: p["value"])
        threshold = max(baseline * 3, 0.02)
        first_bad = next((p for p in points if p["value"] > threshold), None)
        signals.append(
            SignalSummary(
                signal_type="metric", service=raw.service,
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
    def _summarize_logs(incident_id, raw, signals, evidence, tool_calls) -> None:
        tool_calls.append(
            ToolCallRecord(
                id="tc_002", incident_id=incident_id, tool="query_logs",
                args={"query": "ERROR OR 5xx OR exception"}, started_at=_now(),
            )
        )
        errors = [log for log in (raw.logs or []) if str(log.get("level", "")).upper() == "ERROR"]
        if not errors:
            return
        pattern, count = Counter(log.get("msg", "") for log in errors).most_common(1)[0]
        sample_ids = [f"log_{i:03d}" for i in range(1, min(len(errors), 5) + 1)]
        first_seen = min(log["ts"] for log in errors)
        last_seen = max(log["ts"] for log in errors)
        signals.append(
            SignalSummary(
                signal_type="log_pattern", service=raw.service, summary=pattern,
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
    def _summarize_deployments(incident_id, raw, signals, evidence, tool_calls) -> None:
        tool_calls.append(
            ToolCallRecord(
                id="tc_003", incident_id=incident_id, tool="get_recent_deployments",
                args={"window": "2h"}, started_at=_now(),
            )
        )
        deployments = raw.deployments.get("deployments") or []
        if not deployments:
            return
        latest = sorted(deployments, key=lambda d: d["deployed_at"])[-1]
        signals.append(
            SignalSummary(
                signal_type="deployment", service=raw.service,
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
