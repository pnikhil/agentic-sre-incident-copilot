from __future__ import annotations

import argparse
from pathlib import Path

from .app.workflow import Workflow
from .domain.schemas import Alert, Incident, Mode
from .platform import build_adapters, load_profile

ROOT = Path(__file__).resolve().parents[1]  # Aegis/
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"


def build_workflow(mode: Mode = Mode.DRY_RUN, profile_name: str = "local-fixtures") -> Workflow:
    """The composition root. It loads a platform profile and wires the matching adapters.

    Kindly note that only the local-fixtures profile is implemented as of now. The
    gcp-cloud-run profile is declarative, and its adapters will come in the later
    milestones (the GCP reference deployment).
    """
    profile = load_profile(profile_name)
    adapters = build_adapters(profile, data_dir=DATA, artifacts_dir=ARTIFACTS)
    return Workflow(
        telemetry=adapters.telemetry,
        runbooks=adapters.runbooks,
        llm=adapters.llm,
        executor=adapters.executor,
        approvals_store=adapters.approvals,
        audit=adapters.audit,
        artifacts_dir=ARTIFACTS,
        mode=mode,
    )


def load_alert(scenario: str) -> Alert:
    return Alert.model_validate_json(
        (DATA / "scenarios" / scenario / "alert.json").read_text(encoding="utf-8")
    )


def _print_report(inc: Incident) -> None:
    line = "-" * 72
    print(line)
    print(f"AEGIS incident {inc.incident_id}   state={inc.state.value}   mode={inc.mode.value}")
    print(line)

    print("\nEVIDENCE (side-channel summaries the model sees):")
    for e in inc.evidence.items:
        print(f"  [{e.id}] {e.kind}: {e.summary}")

    if inc.diagnosis:
        d = inc.diagnosis
        print(f"\nDIAGNOSIS: {d.status.value}, {d.root_cause}  (confidence {d.confidence:.0%})")
        print(f"  cites: {', '.join(d.cited_evidence_ids) or '(none)'}")
        print(f"  {d.rationale}")

    if inc.runbook_match:
        m = inc.runbook_match
        print(f"\nRUNBOOK: {m.runbook_id}  applies={m.applies}  ({m.reason})")

    if inc.proposal:
        p = inc.proposal
        print(f"\nPROPOSAL: {p.action}  target={p.target.service}/{p.target.environment}")
        print(f"  strategy={p.rollback_target.strategy}  to_revision={p.rollback_target.to_revision}")
        print(f"  grounded={p.runbook_evidence.grounded}  quote=\"{p.runbook_evidence.evidence_quote}\"")
        print(f"  rollback: {p.rollback_plan}")

    if inc.policy_check:
        pc = inc.policy_check
        print(f"\nSAFETY: {pc.verdict.value.upper()}")
        for r in pc.reasons:
            print(f"  - {r}")

    if inc.approval:
        a = inc.approval
        print(f"\nAPPROVAL: {a.approval_id}  mode={a.mode.value}  status={a.status.value}")
        print(f"  payload_hash: {a.payload_hash}")
        print(f"  dry_run_hash: {a.dry_run_hash}")
        print(f"  expires_at:   {a.expires_at.isoformat()}")

    print("\nTIMELINE:")
    for ev in inc.timeline:
        print(f"  {ev.ts.strftime('%H:%M:%S')}  {ev.actor.value:<7} {ev.type:<28} {ev.summary}")

    if inc.e2e_result:
        r = inc.e2e_result
        print("\nE2E RESULT:")
        print("  | Scenario | Runbook | Diagnosis | Action | Safety | Result | MTTR-Proposal |")
        print(
            f"  | {r.scenario} | {r.runbook} | {r.diagnosis} | {r.action} | "
            f"{r.safety_gate} | {r.result} | {r.mttr_proposal_s}s |"
        )

    print(f"\nArtifacts written to: {ARTIFACTS / inc.incident_id}")
    print(line)


def cmd_run(args: argparse.Namespace) -> None:
    wf = build_workflow(Mode(args.mode))
    alert = load_alert(args.scenario)
    incident = wf.run(alert=alert, scenario=args.scenario)
    _print_report(incident)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="Aegis, an agentic incident copilot (Milestone 1, CLI-first)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run the incident workflow on a scenario")
    run_p.add_argument("--scenario", default="bad_deploy", help="scenario folder under data/scenarios")
    run_p.add_argument("--mode", default="dry_run", choices=[m.value for m in Mode])
    run_p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
