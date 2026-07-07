"""CLI for the demo app: emit a telemetry snapshot, or serve the live checkout-api."""

from __future__ import annotations

import argparse
from pathlib import Path

from .emit import write_scenario
from .faults import Fault

ROOT = Path(__file__).resolve().parents[1]  # Aegis/
DATA = ROOT / "data"


def cmd_emit(args: argparse.Namespace) -> None:
    out = write_scenario(Fault(args.fault), scenarios_dir=DATA / "scenarios", name=args.scenario)
    print(f"Wrote {args.fault} telemetry to {out}")
    print(f"Now kindly run: python -m aegis.cli run --scenario {args.scenario}")


def cmd_serve(args: argparse.Namespace) -> None:
    from .app import create_app

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit('uvicorn is not installed. Kindly run: pip install -e ".[demo]"') from exc

    app = create_app(DATA / "scenarios")
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aegis-demo", description="checkout-api demo app for Aegis")
    sub = parser.add_subparsers(dest="cmd", required=True)

    emit_p = sub.add_parser("emit", help="Emit a telemetry snapshot for a fault into data/scenarios")
    emit_p.add_argument("--fault", default="bad_deploy", choices=[f.value for f in Fault])
    emit_p.add_argument("--scenario", default="generated_bad_deploy")
    emit_p.set_defaults(func=cmd_emit)

    serve_p = sub.add_parser("serve", help="Run the live checkout-api (needs the [demo] extra)")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
