from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import RunbookDoc, RunbookHit


class RunbookStorePort(ABC):
    """Runbook retrieval. Local keyword search is used for now, and pgvector or Vertex Vector Search will come later."""

    @abstractmethod
    def search(self, query: str, *, limit: int = 5) -> list[RunbookHit]:
        ...

    @abstractmethod
    def get(self, runbook_id: str) -> RunbookDoc | None:
        ...
