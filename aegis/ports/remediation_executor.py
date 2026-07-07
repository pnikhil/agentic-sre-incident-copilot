from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..domain.schemas import DryRunResult


class RemediationExecutorPort(ABC):
    """Executes the remediation. Milestone 1 exposes only the dry-run path, using a fake executor."""

    @abstractmethod
    def dry_run(self, *, action: str, payload: dict[str, Any]) -> DryRunResult:
        ...
