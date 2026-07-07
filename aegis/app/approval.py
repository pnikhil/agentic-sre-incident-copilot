from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from ..domain import policies
from ..domain.schemas import (
    ApprovalRequest,
    DryRunResult,
    Mode,
    RemediationProposal,
)
from ..ports.approval_store import ApprovalStorePort
from ..ports.remediation_executor import RemediationExecutorPort


class ApprovalService:
    """Creates a payload-bound, expiring approval request in dry-run mode.

    The hashes are generated right from Milestone 1. The enforcement of the
    match, expiry, and single-use rules will land in Milestone 5.
    """

    def __init__(self, executor: RemediationExecutorPort, store: ApprovalStorePort):
        self.executor = executor
        self.store = store

    def request(
        self,
        *,
        incident_id: str,
        proposal: RemediationProposal,
        mode: Mode,
        ttl_minutes: int = 10,
    ) -> tuple[ApprovalRequest, DryRunResult]:
        dry = self.executor.dry_run(action=proposal.action, payload=proposal.payload)
        now = datetime.now(timezone.utc)
        approval = ApprovalRequest(
            approval_id="appr_" + uuid.uuid4().hex[:8],
            incident_id=incident_id,
            action_type=proposal.action,
            payload_hash=policies.sha256_of(proposal.payload),
            dry_run_hash=dry.dry_run_hash,
            mode=mode,
            created_at=now,
            expires_at=now + timedelta(minutes=ttl_minutes),
            proposed_diff=dry.plan,
        )
        self.store.create(approval)
        return approval, dry
