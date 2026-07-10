"""The approval guard and the remediation runner.

The guard enforces that a write is authorised, that is, the approval is bound to
the exact payload and dry-run plan, has not expired, has not been used already,
and the policy has passed. The runner then performs the guarded write and
verifies the recovery. Kindly note that the same runner is reused by the
LangGraph workflow and by the web approval panel.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain import policies
from ..domain.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    Incident,
    PolicyCheckResult,
    RecoveryVerification,
    RemediationExecution,
    RemediationProposal,
    Verdict,
)
from ..mcp.gateway import MCPToolGateway
from ..ports.remediation_executor import RemediationExecutorPort


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalGuard:
    def __init__(self, executor: RemediationExecutorPort):
        self.executor = executor

    def enforce(
        self,
        *,
        proposal: RemediationProposal,
        approval: ApprovalRequest,
        policy: PolicyCheckResult | None,
    ) -> tuple[bool, str]:
        if policy is None or policy.verdict != Verdict.PASS:
            return False, "policy did not pass"
        if approval.status != ApprovalStatus.APPROVED:
            return False, f"approval is not approved (status={approval.status.value})"
        if _now() >= approval.expires_at:
            return False, "approval has expired"
        if approval.payload_hash != policies.sha256_of(proposal.payload):
            return False, "the payload changed after approval"
        dry = self.executor.dry_run(action=proposal.action, payload=proposal.payload)
        if approval.dry_run_hash != dry.dry_run_hash:
            return False, "the dry-run plan changed after approval"
        return True, "ok"


class RemediationRunner:
    def __init__(self, executor: RemediationExecutorPort, gateway: MCPToolGateway):
        self.executor = executor
        self.gateway = gateway
        self.guard = ApprovalGuard(executor)

    def execute(
        self,
        *,
        incident: Incident,
        proposal: RemediationProposal,
        approval: ApprovalRequest,
        policy: PolicyCheckResult | None,
    ) -> tuple[RemediationExecution | None, str]:
        ok, reason = self.guard.enforce(proposal=proposal, approval=approval, policy=policy)
        if not ok:
            return None, reason
        execution = self.executor.execute(
            action=proposal.action, target=proposal.target.service, payload=proposal.payload
        )
        approval.status = ApprovalStatus.CONSUMED
        return execution, "executed"

    def verify(self, *, incident: Incident, proposal: RemediationProposal) -> RecoveryVerification:
        # The recovery check re-reads the deployments through the MCP gateway, and
        # confirms that the revision we rolled back to was previously healthy.
        result, record = self.gateway.call(
            "get_recent_deployments",
            {"scenario": incident.scenario, "service": incident.alert.service},
            incident_id=incident.incident_id,
        )
        incident.tool_calls.append(record)
        target = proposal.rollback_target.to_revision
        deployment = next(
            (d for d in result.deployments if d.get("revision") == target), None
        )
        healthy = bool(deployment and str(deployment.get("status")).lower() == "healthy")
        note = (
            f"rolled back to {target}, which was previously healthy"
            if healthy
            else f"could not confirm that {target} is healthy"
        )
        return RecoveryVerification(verified=healthy, note=note)
