from __future__ import annotations

from typing import Any

from ..domain import policies
from ..domain.schemas import DryRunResult
from ..ports.remediation_executor import RemediationExecutorPort


class FakeExecutor(RemediationExecutorPort):
    """This never mutates anything. It only produces a deterministic dry-run plan along with its hash."""

    def dry_run(self, *, action: str, payload: dict[str, Any]) -> DryRunResult:
        plan = (
            f"[DRY-RUN] would execute '{action}'\n"
            f"  target : {payload.get('target')}\n"
            f"  params : {payload.get('params')}\n"
            "No infrastructure will be mutated (dry-run mode)."
        )
        return DryRunResult(plan=plan, dry_run_hash=policies.sha256_of(plan))
