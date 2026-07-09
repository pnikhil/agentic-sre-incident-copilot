from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..domain.schemas import (
    Actor,
    Alert,
    DiagnosisStatus,
    E2EResult,
    Incident,
    IncidentState,
    IncidentTimelineEvent,
    Mode,
    RunbookDoc,
    Verdict,
)
from ..mcp.gateway import MCPToolGateway
from ..ports.approval_store import ApprovalStorePort
from ..ports.audit_log import AuditLogPort
from ..ports.llm import LLMPort
from ..ports.remediation_executor import RemediationExecutorPort
from .approval import ApprovalService
from .critic import CriticAgent
from .diagnosis import DiagnosisAgent
from .planning import RemediationPlanner
from .triage import TriageAgent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GraphState(TypedDict, total=False):
    incident: Incident
    runbook: RunbookDoc | None
    result: str
    safety_gate: str
    revision_rounds: int
    critic_outcome: str


class Workflow:
    """Orchestrates the incident state machine as a LangGraph multi-agent graph, and
    saves a trace-replay bundle. Kindly note that the agents are reused as graph nodes,
    so the reasoning stays the same, only the orchestration is now an explicit graph
    with proper escalation edges."""

    def __init__(
        self,
        *,
        gateway: MCPToolGateway,
        llm: LLMPort,
        executor: RemediationExecutorPort,
        approvals_store: ApprovalStorePort,
        audit: AuditLogPort,
        artifacts_dir: Path,
        mode: Mode = Mode.DRY_RUN,
        max_tool_calls: int = 10,
        max_reasoning_iterations: int = 6,
        per_tool_timeout_s: int = 10,
        max_revision_rounds: int = 1,
    ):
        self.gateway = gateway
        self.triage = TriageAgent()
        self.diagnoser = DiagnosisAgent(llm)
        self.planner = RemediationPlanner()
        self.critic = CriticAgent(llm)
        self.approver = ApprovalService(executor, approvals_store)
        self.audit = audit
        self.artifacts_dir = Path(artifacts_dir)
        self.mode = mode
        # Reasoning and tool budgets (controlled ReAct, not free-roaming).
        self.max_tool_calls = max_tool_calls
        self.max_reasoning_iterations = max_reasoning_iterations
        self.per_tool_timeout_s = per_tool_timeout_s
        self.max_revision_rounds = max_revision_rounds
        self._graph = self._build_graph()

    def _build_graph(self):
        """Builds the LangGraph graph. Kindly note the escalation edges that route
        straight to the end whenever the agent must not act."""
        graph = StateGraph(GraphState)
        graph.add_node("retrieve", self._node_retrieve)
        graph.add_node("triage", self._node_triage)
        graph.add_node("diagnose", self._node_diagnose)
        graph.add_node("runbook", self._node_runbook)
        graph.add_node("plan", self._node_plan)
        graph.add_node("critic", self._node_critic)
        graph.add_node("approve", self._node_approve)
        graph.set_entry_point("retrieve")
        graph.add_conditional_edges("retrieve", self._route_after_retrieve,
                                    {"escalate": END, "triage": "triage"})
        graph.add_conditional_edges("triage", self._route_after_triage,
                                    {"escalate": END, "diagnose": "diagnose"})
        graph.add_conditional_edges("diagnose", self._route_after_diagnose,
                                    {"escalate": END, "runbook": "runbook"})
        graph.add_conditional_edges("runbook", self._route_after_runbook,
                                    {"escalate": END, "plan": "plan"})
        graph.add_edge("plan", "critic")
        graph.add_conditional_edges("critic", self._route_after_critic,
                                    {"approve": "approve", "replan": "plan", "blocked": END})
        graph.add_edge("approve", END)
        return graph.compile()

    def _emit(self, incident, actor, type_, summary="", evidence_ids=None, state=None):
        if state is not None:
            incident.state = state
        event = IncidentTimelineEvent(
            incident_id=incident.incident_id, ts=_now(), actor=actor, type=type_,
            summary=summary, evidence_ids=evidence_ids or [],
        )
        incident.timeline.append(event)
        self.audit.append(event)

    def run(self, *, alert: Alert, scenario: str) -> Incident:
        started = _now()
        incident = Incident(
            incident_id="inc_" + uuid.uuid4().hex[:8],
            created_at=started,
            alert=alert,
            scenario=scenario,
            mode=self.mode,
        )
        self._emit(incident, Actor.SYSTEM, "incident.created",
                   f"alert {alert.id} on {alert.service}", state=IncidentState.ALERT_RECEIVED)

        final = self._graph.invoke({"incident": incident, "revision_rounds": 0})
        incident = final["incident"]
        result = final.get("result") or "Approval requested (dry-run)"
        safety_gate = final.get("safety_gate") or "Pass"
        return self._finalize(incident, started, safety_gate=safety_gate, result=result)

    # --- graph nodes (each reuses an agent and appends timeline events) ---

    def _node_retrieve(self, state: GraphState) -> dict:
        incident = state["incident"]
        query = " ".join([incident.alert.service, incident.alert.condition,
                          *incident.alert.labels.values()])
        result, record = self.gateway.call(
            "search_runbooks", {"query": query, "limit": 3},
            incident_id=incident.incident_id,
        )
        incident.tool_calls.append(record)
        self._emit(incident, Actor.TOOL, f"tool.{record.tool}", str(record.args))
        runbook = result.hits[0] if result.hits else None
        updates: dict = {"incident": incident, "runbook": runbook}
        if runbook is None:
            self._emit(incident, Actor.AGENT, "escalated", "no applicable runbook found",
                       state=IncidentState.ESCALATED)
            updates["result"] = "Escalated (no runbook)"
            updates["safety_gate"] = "Blocked"
        else:
            self._emit(incident, Actor.AGENT, "runbook.retrieved", f"candidate {runbook.id}")
        return updates

    def _route_after_retrieve(self, state: GraphState) -> str:
        return "triage" if state.get("runbook") is not None else "escalate"

    def _node_triage(self, state: GraphState) -> dict:
        incident = state["incident"]
        runbook = state.get("runbook")
        recipe = runbook.evidence_recipe if runbook else None
        self._emit(incident, Actor.AGENT, "triage.started",
                   f"following evidence_recipe from {runbook.id}" if runbook else "",
                   state=IncidentState.TRIAGE_STARTED)
        telemetry, evidence, tool_calls = self.triage.run(
            incident.incident_id, self.gateway,
            scenario=incident.scenario, service=incident.alert.service, recipe=recipe,
        )
        incident.telemetry = telemetry
        incident.evidence = evidence
        incident.tool_calls.extend(tool_calls)
        for tc in tool_calls:
            self._emit(incident, Actor.TOOL, f"tool.{tc.tool}", str(tc.args))
        total_calls = len(incident.tool_calls)
        self._emit(incident, Actor.AGENT, "budget.checked",
                   f"tool_calls={total_calls}/{self.max_tool_calls}, wasted=0")
        self._emit(incident, Actor.AGENT, "evidence.collected",
                   f"{len(evidence.items)} evidence items", evidence.ids(),
                   state=IncidentState.EVIDENCE_COLLECTED)
        updates: dict = {"incident": incident}
        if total_calls > self.max_tool_calls:
            self._emit(incident, Actor.AGENT, "escalated",
                       f"tool-call budget exceeded ({total_calls} > {self.max_tool_calls})",
                       state=IncidentState.ESCALATED)
            updates["result"] = "Escalated (budget exceeded)"
            updates["safety_gate"] = "Blocked"
        return updates

    def _route_after_triage(self, state: GraphState) -> str:
        return "escalate" if state.get("result") else "diagnose"

    def _node_diagnose(self, state: GraphState) -> dict:
        incident = state["incident"]
        runbook = state.get("runbook")
        diagnosis = self.diagnoser.diagnose(incident.alert, incident.evidence, runbook)
        incident.diagnosis = diagnosis
        self._emit(incident, Actor.AGENT, "diagnosis.proposed",
                   f"{diagnosis.status.value}: {diagnosis.root_cause}",
                   diagnosis.cited_evidence_ids, state=IncidentState.DIAGNOSIS_PROPOSED)
        updates: dict = {"incident": incident}
        if diagnosis.status != DiagnosisStatus.CONFIRMED or not diagnosis.cited_evidence_ids:
            self._emit(incident, Actor.AGENT, "escalated",
                       "inconclusive diagnosis; escalating for human triage",
                       state=IncidentState.ESCALATED)
            updates["result"] = "Escalated (inconclusive)"
            updates["safety_gate"] = "N/A"
        return updates

    def _route_after_diagnose(self, state: GraphState) -> str:
        diag = state["incident"].diagnosis
        if diag and diag.status == DiagnosisStatus.CONFIRMED and diag.cited_evidence_ids:
            return "runbook"
        return "escalate"

    def _node_runbook(self, state: GraphState) -> dict:
        incident = state["incident"]
        runbook = state["runbook"]
        incident.runbook_id = runbook.id
        match = self.diagnoser.match(runbook, incident.evidence)
        incident.runbook_match = match
        self._emit(incident, Actor.AGENT, "runbook.matched",
                   f"{runbook.id} applies={match.applies}", state=IncidentState.RUNBOOK_MATCHED)
        if not match.applies:
            self._emit(incident, Actor.AGENT, "escalated",
                       f"runbook does not apply: {match.reason}", state=IncidentState.ESCALATED)
            return {"incident": incident, "result": "Escalated (runbook N/A)",
                    "safety_gate": "Blocked"}
        return {"incident": incident}

    def _route_after_runbook(self, state: GraphState) -> str:
        incident = state["incident"]
        if incident.runbook_match and not incident.runbook_match.applies:
            return "escalate"
        return "plan"

    def _node_plan(self, state: GraphState) -> dict:
        incident = state["incident"]
        runbook = state["runbook"]
        proposal = self.planner.plan(alert=incident.alert, diagnosis=incident.diagnosis,
                                     evidence=incident.evidence, runbook=runbook)
        incident.proposal = proposal
        self._emit(incident, Actor.AGENT, "runbook.evidence.attached",
                   f"grounded={proposal.runbook_evidence.grounded}",
                   state=IncidentState.RUNBOOK_EVIDENCE_ATTACHED)
        self._emit(incident, Actor.AGENT, "remediation.planned",
                   f"{proposal.action} -> {proposal.rollback_target.strategy}",
                   proposal.cited_evidence_ids, state=IncidentState.REMEDIATION_PLANNED)
        return {"incident": incident}

    def _node_critic(self, state: GraphState) -> dict:
        incident = state["incident"]
        runbook = state["runbook"]
        rounds = state.get("revision_rounds", 0)
        policy = self.critic.review(alert=incident.alert, diagnosis=incident.diagnosis,
                                    proposal=incident.proposal, evidence=incident.evidence,
                                    runbook=runbook, runbook_match=incident.runbook_match,
                                    round_=rounds)
        incident.policy_check = policy
        if policy.verdict == Verdict.PASS:
            self._emit(incident, Actor.AGENT, "safety_check.passed", policy.cited_policy or "",
                       state=IncidentState.SAFETY_CHECK_PASSED)
            return {"incident": incident, "critic_outcome": "pass"}
        if rounds < self.max_revision_rounds:
            self._emit(incident, Actor.AGENT, "critic.revision_requested",
                       f"round {rounds + 1}: " + "; ".join(policy.reasons))
            return {"incident": incident, "critic_outcome": "replan",
                    "revision_rounds": rounds + 1}
        self._emit(incident, Actor.AGENT, "safety_check.blocked", "; ".join(policy.reasons),
                   state=IncidentState.SAFETY_CHECK_BLOCKED)
        return {"incident": incident, "critic_outcome": "blocked",
                "result": "Blocked by safety policy", "safety_gate": "Blocked"}

    def _route_after_critic(self, state: GraphState) -> str:
        outcome = state.get("critic_outcome", "blocked")
        if outcome == "pass":
            return "approve"
        if outcome == "replan":
            return "replan"
        return "blocked"

    def _node_approve(self, state: GraphState) -> dict:
        incident = state["incident"]
        approval, _dry = self.approver.request(
            incident_id=incident.incident_id, proposal=incident.proposal, mode=self.mode
        )
        incident.approval = approval
        self._emit(incident, Actor.SYSTEM, "approval.requested",
                   f"{approval.approval_id} mode={approval.mode.value} "
                   f"payload_hash={approval.payload_hash[:23]}...",
                   state=IncidentState.APPROVAL_REQUESTED)
        return {"incident": incident, "result": "Approval requested (dry-run)",
                "safety_gate": "Pass"}

    def _finalize(self, incident, started, *, safety_gate, result) -> Incident:
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
        self._emit(incident, Actor.SYSTEM, "incident_report.generated", result,
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
