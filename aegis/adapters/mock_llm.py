from __future__ import annotations

from datetime import datetime

from ..domain import policies
from ..domain.schemas import (
    Alert,
    CriticOpinion,
    Diagnosis,
    DiagnosisStatus,
    EvidenceStack,
    RemediationProposal,
    RunbookDoc,
)
from ..ports.llm import LLMPort


class MockLLM(LLMPort):
    """A deterministic, offline reasoning stub.

    It does genuine evidence-first correlation, so that the full pipeline gets
    exercised without any network or model dependency. The same can be swapped
    for a Vertex Gemini adapter later.
    """

    def diagnose(
        self, *, alert: Alert, evidence: EvidenceStack, runbook: RunbookDoc | None
    ) -> Diagnosis:
        metric = evidence.by_kind("error_rate_metric")
        deploy = evidence.by_kind("recent_deployment")
        logs = evidence.by_kind("application_error_logs")

        # Evidence-first. We attribute a root cause only when the error spike
        # correlates with a recent deployment, that is, the errors began just
        # after a deploy that lies within the incident window.
        if metric and deploy and self._deploy_correlates(metric, deploy):
            cited = [e.id for e in (metric, deploy, logs) if e is not None]
            revision = deploy.data.get("revision")
            return Diagnosis(
                status=DiagnosisStatus.CONFIRMED,
                root_cause="bad_deploy",
                confidence=0.86,
                cited_evidence_ids=cited,
                rationale=(
                    f"The error rate rose sharply just after revision {revision} was "
                    "deployed, and the previous revision was healthy, so the new "
                    "deployment is the likely root cause."
                ),
            )

        if metric and deploy:
            return Diagnosis(
                status=DiagnosisStatus.INCONCLUSIVE,
                confidence=0.4,
                rationale=(
                    "The error spike does not correlate with any recent deployment. "
                    "The latest deploy lies well outside the incident window, so a "
                    "confident root cause cannot be established."
                ),
            )

        return Diagnosis(
            status=DiagnosisStatus.INCONCLUSIVE,
            confidence=0.3,
            rationale="There is insufficient or conflicting evidence to attribute a root cause.",
        )

    def critique(
        self,
        *,
        alert: Alert,
        diagnosis: Diagnosis,
        proposal: RemediationProposal,
        evidence: EvidenceStack,
        runbook: RunbookDoc | None,
    ) -> CriticOpinion:
        if diagnosis.status != DiagnosisStatus.CONFIRMED:
            return CriticOpinion(
                safe=False,
                rationale="Diagnosis is inconclusive; escalate rather than act.",
            )
        body = runbook.body if runbook else ""
        if not policies.quote_is_grounded(proposal.runbook_evidence.evidence_quote, body):
            return CriticOpinion(
                safe=False,
                rationale="Proposed action is not grounded in the runbook.",
            )
        return CriticOpinion(
            safe=True,
            rationale=(
                "Evidence supports the diagnosis; the action is grounded, reversible, "
                "and within the runbook's allowed actions."
            ),
        )

    @staticmethod
    def _parse_ts(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _deploy_correlates(self, metric, deploy, window_minutes: int = 60) -> bool:
        first_bad = self._parse_ts(metric.data.get("first_bad_ts"))
        deployed_at = self._parse_ts(deploy.data.get("deployed_at"))
        if first_bad is None or deployed_at is None:
            return False
        delta_seconds = (first_bad - deployed_at).total_seconds()
        return 0 <= delta_seconds <= window_minutes * 60
