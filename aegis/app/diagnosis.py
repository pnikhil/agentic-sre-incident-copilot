from __future__ import annotations

from ..domain.schemas import (
    Alert,
    Diagnosis,
    EvidenceStack,
    RunbookDoc,
    RunbookMatch,
)
from ..ports.llm import LLMPort


class DiagnosisAgent:
    """Evaluates whether a runbook applies to the collected evidence, and then
    diagnoses the root cause. Kindly note that the runbook retrieval itself is
    done by the workflow through the MCP gateway."""

    def __init__(self, llm: LLMPort):
        self.llm = llm

    def match(self, runbook: RunbookDoc, evidence: EvidenceStack) -> RunbookMatch:
        satisfied = set(runbook.required_evidence).issubset(evidence.kinds())
        metric = evidence.by_kind("error_rate_metric")
        deploy = evidence.by_kind("recent_deployment")

        applies_hits: list[str] = []
        exit_hits: list[str] = []
        if metric and deploy:
            first_bad = metric.data.get("first_bad_ts")
            deployed_at = deploy.data.get("deployed_at")
            if first_bad and deployed_at and str(first_bad) >= str(deployed_at):
                applies_hits.append("error_rate increased after recent deployment")
            else:
                exit_hits.append("errors started before deployment")

        applies = satisfied and bool(applies_hits) and not exit_hits
        reason = (
            "required evidence present; errors began after the latest deploy"
            if applies
            else "applicability conditions not met"
        )
        return RunbookMatch(
            runbook_id=runbook.id,
            applies=applies,
            required_evidence_satisfied=satisfied,
            applies_when_hits=applies_hits,
            exit_when_hits=exit_hits,
            reason=reason,
        )

    def diagnose(
        self, alert: Alert, evidence: EvidenceStack, runbook: RunbookDoc | None
    ) -> Diagnosis:
        return self.llm.diagnose(alert=alert, evidence=evidence, runbook=runbook)
