from __future__ import annotations

import json
from pathlib import Path

from ..domain.schemas import RawTelemetry
from ..ports.telemetry import TelemetryPort


class LocalFixtureTelemetry(TelemetryPort):
    """Reads the deterministic scenario fixtures kept under data/scenarios/<scenario>/."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def fetch(self, *, scenario: str, service: str) -> RawTelemetry:
        base = self.data_dir / "scenarios" / scenario
        metrics = json.loads((base / "metrics.json").read_text(encoding="utf-8"))
        deployments = json.loads((base / "deployments.json").read_text(encoding="utf-8"))
        logs_text = (base / "logs.jsonl").read_text(encoding="utf-8")
        logs = [json.loads(line) for line in logs_text.splitlines() if line.strip()]
        return RawTelemetry(
            service=service, metrics=metrics, logs=logs, deployments=deployments
        )
