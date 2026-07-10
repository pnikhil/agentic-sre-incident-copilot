from __future__ import annotations

from ..domain.schemas import ApprovalRequest, ApprovalStatus, Incident, RemediationProposal
from ..ports.approver import ApprovalDecisionPort


class AutoApprover(ApprovalDecisionPort):
    """Approves or rejects automatically. Kindly note that this is meant for the
    tests and for a non-interactive demo, and never for a real production write."""

    def __init__(self, approve: bool = True):
        self.approve = approve

    def decide(self, *, approval, proposal, incident) -> ApprovalStatus:
        return ApprovalStatus.APPROVED if self.approve else ApprovalStatus.REJECTED


class DenyingApprover(ApprovalDecisionPort):
    """Leaves every request pending. This is the safe default, so that nothing is
    executed unless a human explicitly approves it."""

    def decide(self, *, approval, proposal, incident) -> ApprovalStatus:
        return ApprovalStatus.PENDING


class CliApprover(ApprovalDecisionPort):
    """Asks the human on the terminal. It shows the proposed dry-run plan and the
    approval hashes, and then reads a yes or no from standard input."""

    def decide(self, *, approval, proposal, incident) -> ApprovalStatus:
        print("\n--- HUMAN APPROVAL REQUIRED ---")
        print(f"  incident : {incident.incident_id}")
        print(f"  action   : {proposal.action} on {proposal.target.service}")
        print(f"  strategy : {proposal.rollback_target.strategy} "
              f"-> {proposal.rollback_target.to_revision}")
        print(f"  payload_hash: {approval.payload_hash}")
        print(f"  dry_run_hash: {approval.dry_run_hash}")
        print("  proposed plan:")
        for line in approval.proposed_diff.splitlines():
            print(f"    {line}")
        answer = input("Approve this rollback? [y/N]: ").strip().lower()
        return ApprovalStatus.APPROVED if answer in ("y", "yes") else ApprovalStatus.REJECTED
