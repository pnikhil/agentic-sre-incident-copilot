"""Minimal web approval panel for human-approved remediation.

Runs a scenario to approval, shows the dry-run plan and hashes, then lets a
human approve or reject. The full incident console comes later.

Run it with:  python -m aegis.web.panel   (needs the demo extra)
"""

from __future__ import annotations

from html import escape

try:
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, RedirectResponse
except ImportError as exc:  # pragma: no cover - only hit when the extra is missing
    raise SystemExit(
        'The web panel needs the demo extra. Please run: pip install -e ".[demo]"'
    ) from exc

from ..cli import build_workflow, load_alert
from ..domain.schemas import ApprovalStatus, Incident, Mode

# incident_id -> (workflow, incident). In-process registry is enough for local demo.
_INCIDENTS: dict[str, tuple] = {}

app = FastAPI(title="Aegis Approval Panel")


def _run_to_approval(scenario: str) -> Incident:
    workflow = build_workflow(Mode.DRY_RUN)
    incident = workflow.run(alert=load_alert(scenario), scenario=scenario)
    _INCIDENTS[incident.incident_id] = (workflow, incident)
    return incident


def _card(incident: Incident) -> str:
    approval = incident.approval
    proposal = incident.proposal
    diagnosis = incident.diagnosis.root_cause if incident.diagnosis else "inconclusive"
    lines = [
        f"<h3>{escape(incident.incident_id)} &middot; {escape(incident.scenario or '')}</h3>",
        f"<p><b>Diagnosis:</b> {escape(str(diagnosis))}</p>",
    ]
    if proposal is not None:
        lines.append(
            f"<p><b>Proposed:</b> {escape(proposal.action)} on "
            f"{escape(proposal.target.service)} &rarr; "
            f"{escape(str(proposal.rollback_target.to_revision))}</p>"
        )
    if approval is not None:
        lines.append(f"<pre>{escape(approval.proposed_diff)}</pre>")
        lines.append(f"<p><b>payload_hash:</b> {escape(approval.payload_hash)}</p>")
        if approval.status == ApprovalStatus.PENDING:
            lines.append(
                f'<form method="post" action="/approvals/{incident.incident_id}" '
                'style="display:inline">'
                '<button name="decision" value="approve">Approve</button> '
                '<button name="decision" value="reject">Reject</button>'
                "</form>"
            )
        else:
            lines.append(f"<p><b>Approval:</b> {escape(approval.status.value)}</p>")
    if incident.execution is not None:
        lines.append(f"<p><b>Execution:</b> {escape(incident.execution.note)}</p>")
    if incident.recovery is not None:
        lines.append(
            f"<p><b>Recovery:</b> verified={incident.recovery.verified} "
            f"&middot; {escape(incident.recovery.note)}</p>"
        )
    if incident.e2e_result is not None:
        lines.append(f"<p><b>Result:</b> {escape(incident.e2e_result.result)}</p>")
    return '<div style="border:1px solid #ccc;padding:12px;margin:12px 0">' + "".join(lines) + "</div>"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    cards = "".join(_card(inc) for _wf, inc in _INCIDENTS.values())
    return f"""<!doctype html>
<html><head><title>Aegis Approval Panel</title></head>
<body style="font-family:sans-serif;max-width:820px;margin:24px auto">
  <h1>Aegis Approval Panel</h1>
  <form method="post" action="/incidents">
    <label>Scenario:
      <select name="scenario">
        <option value="bad_deploy">bad_deploy</option>
        <option value="ambiguous_telemetry">ambiguous_telemetry</option>
      </select>
    </label>
    <button type="submit">Run to approval</button>
  </form>
    {cards or "<p>No incidents yet. Run one above.</p>"}
</body></html>"""


@app.post("/incidents")
def create_incident(scenario: str = Form("bad_deploy")):
    _run_to_approval(scenario)
    return RedirectResponse("/", status_code=303)


@app.post("/approvals/{incident_id}")
def decide(incident_id: str, decision: str = Form(...)):
    entry = _INCIDENTS.get(incident_id)
    if entry is not None:
        workflow, incident = entry
        workflow.resume_execution(incident, approved=(decision == "approve"))
    return RedirectResponse("/", status_code=303)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
