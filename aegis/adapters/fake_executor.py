from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain import policies
from ..domain.schemas import DryRunResult, RemediationExecution
from ..ports.remediation_executor import RemediationExecutorPort


class FakeExecutor(RemediationExecutorPort):
    """This never mutates anything. The dry-run produces a deterministic plan along
    with its hash, and execute simulates a reversible rollback for the local demo."""

    def dry_run(self, *, action: str, payload: dict[str, Any]) -> DryRunResult:
        target = payload.get("target", {})
        rollback = payload.get("rollback_target", {})
        plan = (
            f"[DRY-RUN] would execute '{action}'\n"
            f"  service  : {target.get('service')} ({target.get('environment')})\n"
            f"  strategy : {rollback.get('strategy')} -> {rollback.get('to_revision')}\n"
            "No infrastructure will be mutated (dry-run mode)."
        )
        return DryRunResult(plan=plan, dry_run_hash=policies.sha256_of(plan))

    def execute(self, *, action: str, target: str, payload: dict[str, Any]) -> RemediationExecution:
        rollback = payload.get("rollback_target", {})
        to_revision = rollback.get("to_revision")
        # Kindly note that nothing is really mutated. We only record what a real
        # executor would have done, so the demo stays safe and reversible.
        return RemediationExecution(
            action=action,
            target=target,
            params=rollback,
            ok=True,
            executor="fake",
            note=f"[FAKE] rolled {target} back to {to_revision}, no real mutation",
            executed_at=datetime.now(timezone.utc),
        )
