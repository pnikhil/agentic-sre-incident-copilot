from __future__ import annotations

from ..domain.schemas import (
    Alert,
    Diagnosis,
    EvidenceStack,
    RunbookDoc,
    RunbookMatch,
)
from ..ports.llm import LLMPort
from ..ports.runbook_store import RunbookStorePort


class DiagnosisAgent:
    """Retrieves the applicable runbook, evaluates whether it applies, and then diagnoses."""

    def __init__(self, llm: LLMPort, runbooks: RunbookStorePort):
        self.llm = llm
        self.runbooks = runbooks

    def retrieve_runbook(self, alert: Alert, evidence: EvidenceStack) -> RunbookDoc | None:
        query_terms = [alert.service, alert.condition]
        query_terms += [e.summary for e in evidence.items]
        query_terms += ["rollback", "deployment", "error", "rate", "5xx", "revision"]
        hits = self.runbooks.search(" ".join(query_terms), limit=3)
        if not hits or hits[0].score <= 0:
            return None
        return self.runbooks.get(hits[0].runbook_id)

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
