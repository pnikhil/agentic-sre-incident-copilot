from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..domain.schemas import (
    Actor,
    Alert,
    DiagnosisStatus,
    E2EResult,
    Incident,
    IncidentState,
    IncidentTimelineEvent,
    Mode,
    Verdict,
)
from ..ports.approval_store import ApprovalStorePort
from ..ports.audit_log import AuditLogPort
from ..ports.llm import LLMPort
from ..ports.remediation_executor import RemediationExecutorPort
from ..ports.runbook_store import RunbookStorePort
from ..ports.telemetry import TelemetryPort
from .approval import ApprovalService
from .critic import CriticAgent
from .diagnosis import DiagnosisAgent
from .planning import RemediationPlanner
from .triage import TriageAgent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Workflow:
    """Orchestrates the incident state machine and saves a trace-replay bundle."""

    def __init__(
        self,
        *,
        telemetry: TelemetryPort,
        runbooks: RunbookStorePort,
        llm: LLMPort,
        executor: RemediationExecutorPort,
        approvals_store: ApprovalStorePort,
        audit: AuditLogPort,
        artifacts_dir: Path,
        mode: Mode = Mode.DRY_RUN,
    ):
        self.telemetry = telemetry
        self.triage = TriageAgent()
        self.diagnoser = DiagnosisAgent(llm, runbooks)
        self.planner = RemediationPlanner()
        self.critic = CriticAgent(llm)
        self.approver = ApprovalService(executor, approvals_store)
        self.audit = audit
        self.artifacts_dir = Path(artifacts_dir)
        self.mode = mode

    def run(self, *, alert: Alert, scenario: str) -> Incident:
        started = _now()
        incident = Incident(
            incident_id="inc_" + uuid.uuid4().hex[:8],
            created_at=started,
            alert=alert,
            scenario=scenario,
            mode=self.mode,
        )

        def emit(actor, type_, summary="", evidence_ids=None, state=None):
            if state is not None:
                incident.state = state
            event = IncidentTimelineEvent(
                incident_id=incident.incident_id,
                ts=_now(),
                actor=actor,
                type=type_,
                summary=summary,
                evidence_ids=evidence_ids or [],
            )
            incident.timeline.append(event)
            self.audit.append(event)

        emit(Actor.SYSTEM, "incident.created", f"alert {alert.id} on {alert.service}",
             state=IncidentState.ALERT_RECEIVED)

        # --- Triage / evidence (side-channel) ---
        emit(Actor.AGENT, "triage.started", state=IncidentState.TRIAGE_STARTED)
        raw = self.telemetry.fetch(scenario=scenario, service=alert.service)
        telemetry, evidence, tool_calls = self.triage.run(incident.incident_id, raw)
        incident.telemetry = telemetry
        incident.evidence = evidence
        incident.tool_calls = tool_calls
        for tc in tool_calls:
            emit(Actor.TOOL, f"tool.{tc.tool}", str(tc.args))
        emit(Actor.AGENT, "evidence.collected", f"{len(evidence.items)} evidence items",
             evidence.ids(), state=IncidentState.EVIDENCE_COLLECTED)

        # --- Retrieve runbook + diagnose ---
        runbook = self.diagnoser.retrieve_runbook(alert, evidence)
        diagnosis = self.diagnoser.diagnose(alert, evidence, runbook)
        incident.diagnosis = diagnosis
        emit(Actor.AGENT, "diagnosis.proposed",
             f"{diagnosis.status.value}: {diagnosis.root_cause}",
             diagnosis.cited_evidence_ids, state=IncidentState.DIAGNOSIS_PROPOSED)

        # Invariant: with no cited evidence, we go inconclusive and then escalate.
        if diagnosis.status != DiagnosisStatus.CONFIRMED or not diagnosis.cited_evidence_ids:
            emit(Actor.AGENT, "escalated",
                 "inconclusive diagnosis; escalating for human triage",
                 state=IncidentState.ESCALATED)
            return self._finalize(incident, started, safety_gate="N/A",
                                  result="Escalated (inconclusive)", emit=emit)

        if runbook is None:
            emit(Actor.AGENT, "escalated", "no applicable runbook found",
                 state=IncidentState.ESCALATED)
            return self._finalize(incident, started, safety_gate="Blocked",
                                  result="Escalated (no runbook)", emit=emit)

        incident.runbook_id = runbook.id
        match = self.diagnoser.match(runbook, evidence)
        incident.runbook_match = match
        emit(Actor.AGENT, "runbook.matched", f"{runbook.id} applies={match.applies}",
             state=IncidentState.RUNBOOK_MATCHED)
        if not match.applies:
            emit(Actor.AGENT, "escalated", f"runbook does not apply: {match.reason}",
                 state=IncidentState.ESCALATED)
            return self._finalize(incident, started, safety_gate="Blocked",
                                  result="Escalated (runbook N/A)", emit=emit)

        # --- Plan remediation ---
        proposal = self.planner.plan(alert=alert, diagnosis=diagnosis,
                                     evidence=evidence, runbook=runbook)
        incident.proposal = proposal
        emit(Actor.AGENT, "runbook.evidence.attached",
             f"grounded={proposal.runbook_evidence.grounded}",
             state=IncidentState.RUNBOOK_EVIDENCE_ATTACHED)
        emit(Actor.AGENT, "remediation.planned",
             f"{proposal.action} -> {proposal.rollback_target.strategy}",
             proposal.cited_evidence_ids, state=IncidentState.REMEDIATION_PLANNED)

        # --- Critic / policy (bounded, single pass) ---
        policy = self.critic.review(alert=alert, diagnosis=diagnosis, proposal=proposal,
                                    evidence=evidence, runbook=runbook, runbook_match=match)
        incident.policy_check = policy
        if policy.verdict == Verdict.BLOCK:
            emit(Actor.AGENT, "safety_check.blocked", "; ".join(policy.reasons),
                 state=IncidentState.SAFETY_CHECK_BLOCKED)
            return self._finalize(incident, started, safety_gate="Blocked",
                                  result="Blocked by safety policy", emit=emit)
        emit(Actor.AGENT, "safety_check.passed", policy.cited_policy or "",
             state=IncidentState.SAFETY_CHECK_PASSED)

        # --- Approval (dry-run; hashes generated) ---
        approval, _dry = self.approver.request(
            incident_id=incident.incident_id, proposal=proposal, mode=self.mode
        )
        incident.approval = approval
        emit(Actor.SYSTEM, "approval.requested",
             f"{approval.approval_id} mode={approval.mode.value} "
             f"payload_hash={approval.payload_hash[:23]}...",
             state=IncidentState.APPROVAL_REQUESTED)

        return self._finalize(incident, started, safety_gate="Pass",
                              result="Approval requested (dry-run)", emit=emit)

    def _finalize(self, incident, started, *, safety_gate, result, emit) -> Incident:
        elapsed = (_now() - started).total_seconds()
        diag = incident.diagnosis
        incident.e2e_result = E2EResult(
            scenario=incident.scenario or "?",
            runbook=incident.runbook_id,
            diagnosis=(diag.root_cause if diag and diag.status == DiagnosisStatus.CONFIRMED
                       else "inconclusive"),
            action=(incident.proposal.action if incident.proposal else None),
            safety_gate=safety_gate,
            result=result,
            mttr_proposal_s=round(elapsed, 3),
        )
        emit(Actor.SYSTEM, "incident_report.generated", result,
             state=IncidentState.INCIDENT_REPORT_GENERATED)
        self._write_artifacts(incident)
        return incident

    def _write_artifacts(self, incident: Incident) -> None:
        out = self.artifacts_dir / incident.incident_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "incident.json").write_text(incident.model_dump_json(indent=2), encoding="utf-8")
        (out / "evidence.json").write_text(incident.evidence.model_dump_json(indent=2), encoding="utf-8")
        (out / "timeline.jsonl").write_text(
            "\n".join(e.model_dump_json() for e in incident.timeline), encoding="utf-8"
        )
        if incident.diagnosis:
            (out / "diagnosis.json").write_text(incident.diagnosis.model_dump_json(indent=2), encoding="utf-8")
        if incident.proposal:
            (out / "remediation_proposal.json").write_text(
                incident.proposal.model_dump_json(indent=2), encoding="utf-8"
            )
        if incident.policy_check:
            (out / "policy_check.json").write_text(
                incident.policy_check.model_dump_json(indent=2), encoding="utf-8"
            )
        if incident.approval:
            (out / "approval_request.json").write_text(
                incident.approval.model_dump_json(indent=2), encoding="utf-8"
            )
        if incident.e2e_result:
            (out / "e2e_result.json").write_text(
                incident.e2e_result.model_dump_json(indent=2), encoding="utf-8"
            )
