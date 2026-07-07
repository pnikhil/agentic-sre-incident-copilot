"""Writes a telemetry snapshot to a scenario folder that Milestone 1 can consume."""

from __future__ import annotations

import json
from pathlib import Path

from .faults import Fault, generate


def write_scenario(fault: Fault, *, scenarios_dir: Path, name: str) -> Path:
    """Generate telemetry for ``fault`` and write the scenario files under
    ``scenarios_dir/name/``. Returns the scenario directory path."""
    snapshot = generate(fault)
    out = Path(scenarios_dir) / name
    out.mkdir(parents=True, exist_ok=True)

    (out / "alert.json").write_text(json.dumps(snapshot["alert"], indent=2), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(snapshot["metrics"], indent=2), encoding="utf-8")
    (out / "deployments.json").write_text(json.dumps(snapshot["deployments"], indent=2), encoding="utf-8")
    (out / "ground_truth.json").write_text(json.dumps(snapshot["ground_truth"], indent=2), encoding="utf-8")
    (out / "logs.jsonl").write_text(
        "\n".join(json.dumps(line) for line in snapshot["logs"]), encoding="utf-8"
    )
    return out
