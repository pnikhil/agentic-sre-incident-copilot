from __future__ import annotations

from pathlib import Path

from ..domain.schemas import IncidentTimelineEvent
from ..ports.audit_log import AuditLogPort


class FileAuditLog(AuditLogPort):
    """An append-only JSONL audit sink, with one line per timeline event."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: IncidentTimelineEvent) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
