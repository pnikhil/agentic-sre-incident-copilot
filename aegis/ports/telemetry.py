from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import RawTelemetry


class TelemetryPort(ABC):
    """Fetches the raw telemetry. Local fixtures are used for now, and Cloud Logging or Monitoring will come later."""

    @abstractmethod
    def fetch(self, *, scenario: str, service: str) -> RawTelemetry:
        ...
