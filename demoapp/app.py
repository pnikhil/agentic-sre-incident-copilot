"""A tiny checkout-api that can inject faults, meant for the live demo.

FastAPI is optional. Install it with:
    pip install -e ".[demo]"
"""

from __future__ import annotations

import time
from pathlib import Path

from .emit import write_scenario
from .faults import Fault

try:
    from fastapi import FastAPI, HTTPException

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised only without the demo extra
    _HAS_FASTAPI = False


class _State:
    def __init__(self) -> None:
        self.fault = Fault.NONE
        self.revision = "checkout-api-00042"


def create_app(scenarios_dir: Path):
    """Build the FastAPI app. Raises if the demo extra is not installed."""
    if not _HAS_FASTAPI:
        raise RuntimeError('FastAPI is not installed. Please run: pip install -e ".[demo]"')

    app = FastAPI(title="checkout-api (demo)")
    state = _State()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "revision": state.revision, "fault": state.fault.value}

    @app.get("/checkout")
    def checkout():
        if state.fault == Fault.BAD_DEPLOY:
            raise HTTPException(status_code=500, detail="NullPointerException in CheckoutHandler.process")
        if state.fault == Fault.LATENCY_SPIKE:
            time.sleep(0.8)
            return {"status": "ok", "slow": True}
        return {"status": "ok"}

    @app.get("/faults")
    def get_faults():
        return {"active": state.fault.value, "available": [f.value for f in Fault]}

    @app.post("/faults/{name}")
    def set_fault(name: str):
        try:
            state.fault = Fault(name)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"unknown fault '{name}'")
        return {"active": state.fault.value}

    @app.post("/telemetry/emit")
    def emit(scenario: str = "generated_live"):
        out = write_scenario(state.fault, scenarios_dir=scenarios_dir, name=scenario)
        return {"written": str(out), "fault": state.fault.value, "scenario": scenario}

    return app
