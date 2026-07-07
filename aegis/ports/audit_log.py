from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import IncidentTimelineEvent


class AuditLogPort(ABC):
    """An append-only audit sink for the timeline events."""

    @abstractmethod
    def append(self, event: IncidentTimelineEvent) -> None:
        ...
