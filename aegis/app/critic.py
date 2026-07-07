from __future__ import annotations

from ..domain import policies
from ..domain.schemas import (
    Alert,
    Diagnosis,
    EvidenceStack,
    PolicyCheckResult,
    RemediationProposal,
    RunbookDoc,
    RunbookMatch,
    Verdict,
)
from ..ports.llm import LLMPort

_CITED_POLICY = "priority-order: policy > approval > evidence > runbook > memory > model"


class CriticAgent:
    """An independent, bounded safety review. It combines the hard domain
    invariants with an independent model opinion. It is a single pass, and if
    the matter is still contested, the workflow escalates."""

    def __init__(self, llm: LLMPort):
        self.llm = llm

    def review(
        self,
        *,
        alert: Alert,
        diagnosis: Diagnosis,
        proposal: RemediationProposal,
        evidence: EvidenceStack,
        runbook: RunbookDoc | None,
        runbook_match: RunbookMatch | None,
        round_: int = 0,
    ) -> PolicyCheckResult:
        reasons: list[str] = []

        usable, why = policies.runbook_usable(runbook)
        if not usable:
            reasons.append(f"runbook unusable: {why}")
        if not policies.has_cited_evidence(diagnosis):
            reasons.append("no cited evidence for diagnosis")
        if runbook_match is not None and not runbook_match.applies:
            reasons.append("runbook does not apply to this incident")
        if not policies.action_allowed(proposal.action, runbook):
            reasons.append(f"action '{proposal.action}' not in runbook allowed_actions")
        if not proposal.runbook_evidence.grounded:
            reasons.append("remediation not grounded in runbook")

        opinion = self.llm.critique(
            alert=alert,
            diagnosis=diagnosis,
            proposal=proposal,
            evidence=evidence,
            runbook=runbook,
        )
        if not opinion.safe:
            reasons.append(f"critic: {opinion.rationale}")

        verdict = Verdict.PASS if not reasons else Verdict.BLOCK
        return PolicyCheckResult(
            verdict=verdict,
            reasons=reasons or [opinion.rationale],
            cited_policy=_CITED_POLICY,
            revision_round=round_,
        )
