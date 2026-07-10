from __future__ import annotations

from ..domain import policies
from ..domain.schemas import (
    Alert,
    Diagnosis,
    EvidenceStack,
    RemediationProposal,
    RollbackTarget,
    RunbookDoc,
    RunbookEvidence,
    ServiceRef,
)

# Expected rollback quote. Always verify groundedness against the source.
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

        # The core stays provider-neutral. The platform and the resource_id are
        # left for the executor adapter to resolve later.
        target = ServiceRef(
            service=alert.service,
            environment=alert.labels.get("env", "unknown"),
        )
        rollback_target = RollbackTarget(
            strategy="previous_stable_revision",
            to_revision=previous_stable,
            from_revision=current_revision,
        )

        quote = _ROLLBACK_QUOTE
        if not policies.quote_is_grounded(quote, runbook.body):
            quote = _first_sentence(runbook.body)
        grounded = policies.quote_is_grounded(quote, runbook.body)

        payload = {
            "action_type": action,
            "target": target.model_dump(),
            "rollback_target": rollback_target.model_dump(),
        }

        return RemediationProposal(
            action=action,
            target=target,
            rollback_target=rollback_target,
            rollback_plan=(
                f"Re-deploy {previous_stable} (the previous healthy revision) for "
                f"{alert.service}. This is fully reversible."
            ),
            cited_evidence_ids=diagnosis.cited_evidence_ids,
            runbook_evidence=RunbookEvidence(
                source_runbook=runbook.id, evidence_quote=quote, grounded=grounded
            ),
            payload=payload,
        )
