from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import ApprovalRequest


class ApprovalStorePort(ABC):
    """Stores the approval requests. An in-memory store is used for now, and a durable store will come later."""

    @abstractmethod
    def create(self, approval: ApprovalRequest) -> None:
        ...

    @abstractmethod
    def get(self, approval_id: str) -> ApprovalRequest | None:
        ...
