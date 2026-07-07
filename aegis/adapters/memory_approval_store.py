from __future__ import annotations

from ..domain.schemas import ApprovalRequest
from ..ports.approval_store import ApprovalStorePort


class MemoryApprovalStore(ApprovalStorePort):
    """An in-memory approval store, used for the local runs."""

    def __init__(self) -> None:
        self._store: dict[str, ApprovalRequest] = {}

    def create(self, approval: ApprovalRequest) -> None:
        self._store[approval.approval_id] = approval

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._store.get(approval_id)
