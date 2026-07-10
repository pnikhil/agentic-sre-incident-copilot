from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..domain.schemas import DryRunResult, RemediationExecution


class RemediationExecutorPort(ABC):
    """Executes the remediation. The dry-run path produces a plan and its hash, and
    the guarded execute path performs the (fake) reversible write."""

    @abstractmethod
    def dry_run(self, *, action: str, payload: dict[str, Any]) -> DryRunResult:
        ...

    @abstractmethod
    def execute(self, *, action: str, target: str, payload: dict[str, Any]) -> RemediationExecution:
        ...
