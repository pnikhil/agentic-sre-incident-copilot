from __future__ import annotations

from ..domain import policies
from ..domain.schemas import (
    Alert,
    Diagnosis,
    EvidenceStack,
    RemediationProposal,
    RunbookDoc,
    RunbookEvidence,
)

# A quote we expect to find word-for-word in the rollback runbook. Kindly note
# that groundedness is always verified against the source, and never trusted.
_ROLLBACK_QUOTE = (
    "If error rate exceeds 5% within 10 minutes of a deployment, rollback to the "
    "previous stable revision."
)


def _first_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text.split(". ")[0].strip() + "."


class RemediationPlanner:
    """Proposes a reversible action, citing the evidence and a grounded runbook quote."""

    def plan(
        self,
        *,
        alert: Alert,
        diagnosis: Diagnosis,
        evidence: EvidenceStack,
        runbook: RunbookDoc,
    ) -> RemediationProposal:
        action = runbook.allowed_actions[0] if runbook.allowed_actions else "escalate"
        deploy = evidence.by_kind("recent_deployment")
        previous_stable = (deploy.data.get("previous_stable") if deploy else None) or "previous-stable"
        current_revision = deploy.data.get("revision") if deploy else None
        params = {"to_revision": previous_stable, "from_revision": current_revision}

        quote = _ROLLBACK_QUOTE
        if not policies.quote_is_grounded(quote, runbook.body):
            quote = _first_sentence(runbook.body)
        grounded = policies.quote_is_grounded(quote, runbook.body)

        payload = {"action": action, "target": alert.service, "params": params}

        return RemediationProposal(
            action=action,
            target=alert.service,
            params=params,
            rollback_plan=(
                f"Re-deploy {previous_stable} (previous healthy revision) for "
                f"{alert.service}; fully reversible."
            ),
            cited_evidence_ids=diagnosis.cited_evidence_ids,
            runbook_evidence=RunbookEvidence(
                source_runbook=runbook.id, evidence_quote=quote, grounded=grounded
            ),
            payload=payload,
        )
