"""Typed contracts for Aegis. Kindly note that the system depends only on these, and never on the demo app directly."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---------------------------------------------------------------


class IncidentState(str, Enum):
    ALERT_RECEIVED = "ALERT_RECEIVED"
    TRIAGE_STARTED = "TRIAGE_STARTED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    DIAGNOSIS_PROPOSED = "DIAGNOSIS_PROPOSED"
    RUNBOOK_MATCHED = "RUNBOOK_MATCHED"
    RUNBOOK_EVIDENCE_ATTACHED = "RUNBOOK_EVIDENCE_ATTACHED"
    REMEDIATION_PLANNED = "REMEDIATION_PLANNED"
    SAFETY_CHECK_PASSED = "SAFETY_CHECK_PASSED"
    SAFETY_CHECK_BLOCKED = "SAFETY_CHECK_BLOCKED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    ESCALATED = "ESCALATED"
    INCIDENT_REPORT_GENERATED = "INCIDENT_REPORT_GENERATED"


class Actor(str, Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"
    TOOL = "tool"


class DiagnosisStatus(str, Enum):
    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"


class Verdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"


class Mode(str, Enum):
    READ_ONLY = "read_only"
    DRY_RUN = "dry_run"
    APPROVED_WRITES = "approved_writes"


class Capability(str, Enum):
    """The abstract capabilities that an adapter can advertise for a given platform."""

    QUERY_LOGS = "query_logs"
    FETCH_METRICS = "fetch_metrics"
    GET_RECENT_DEPLOYMENTS = "get_recent_deployments"
    SEARCH_RUNBOOKS = "search_runbooks"
    DRY_RUN_ROLLBACK = "dry_run_rollback"
    EXECUTE_ROLLBACK = "execute_rollback"
    VERIFY_RECOVERY = "verify_recovery"
    REDACT_SECRET_FIELDS = "redact_secret_fields"
    EMIT_TRACE = "emit_trace"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


# --- Inputs / telemetry --------------------------------------------------


class Alert(BaseModel):
    id: str
    service: str
    condition: str
    severity: str = "unknown"
    fired_at: datetime
    labels: dict[str, str] = Field(default_factory=dict)


class ServiceRef(BaseModel):
    """A provider-neutral reference to a service. Kindly note that the platform and
    the resource_id are opaque to the core, and are filled in by the platform adapter."""

    service: str
    environment: str = "unknown"
    platform: str = "unknown"  # for example gcp-cloud-run, kubernetes, local-fixtures
    resource_id: str | None = None


class ResourceRef(BaseModel):
    """A provider-neutral reference to any resource, such as a service, a database, or a queue."""

    kind: str
    name: str
    platform: str = "unknown"
    resource_id: str | None = None


class RawTelemetry(BaseModel):
    """Raw signals fetched from the telemetry port. The same are never sent raw to the model."""

    service: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    deployments: dict[str, Any] = Field(default_factory=dict)


class SignalSummary(BaseModel):
    """A compact, model-safe structured signal, produced by side-channel summarisation."""

    signal_type: str  # metric | log_pattern | deployment
    service: str
    summary: str
    count: int | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    value: float | None = None
    baseline: float | None = None
    sample_ids: list[str] = Field(default_factory=list)


class TelemetrySummary(BaseModel):
    signals: list[SignalSummary] = Field(default_factory=list)


# --- Evidence ------------------------------------------------------------


class Evidence(BaseModel):
    id: str  # ev_metric_001, ev_log_001, ev_deploy_001
    kind: str  # error_rate_metric | application_error_logs | recent_deployment
    summary: str
    source_tool: str
    observed_at: datetime | None = None
    refs: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceStack(BaseModel):
    items: list[Evidence] = Field(default_factory=list)

    def ids(self) -> list[str]:
        return [e.id for e in self.items]

    def kinds(self) -> set[str]:
        return {e.kind for e in self.items}

    def by_kind(self, kind: str) -> Evidence | None:
        return next((e for e in self.items if e.kind == kind), None)


# --- Runbooks ------------------------------------------------------------


class RunbookDoc(BaseModel):
    id: str
    title: str
    owner: str | None = None
    path: str | None = None
    approved: bool = True
    environment_scope: list[str] = Field(default_factory=list)
    last_reviewed: str | None = None
    expires_at: str | None = None
    applies_when: list[str] = Field(default_factory=list)
    exit_when: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    evidence_recipe: list[dict[str, Any]] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    risk_level: str = "unknown"
    requires_approval: bool = True
    body: str = ""


class RunbookHit(BaseModel):
    runbook_id: str
    score: float
    snippet: str = ""


class RunbookMatch(BaseModel):
    runbook_id: str
    applies: bool
    required_evidence_satisfied: bool
    applies_when_hits: list[str] = Field(default_factory=list)
    exit_when_hits: list[str] = Field(default_factory=list)
    reason: str = ""


class RunbookEvidence(BaseModel):
    source_runbook: str
    evidence_quote: str
    grounded: bool


class RollbackTarget(BaseModel):
    """An abstract rollback intent. The platform adapter translates the strategy into a
    concrete operation, such as a Cloud Run traffic shift or a kubectl rollout undo."""

    strategy: str = "previous_stable_revision"
    to_revision: str | None = None
    from_revision: str | None = None


# --- Reasoning outputs ---------------------------------------------------


class Diagnosis(BaseModel):
    status: DiagnosisStatus
    root_cause: str | None = None
    confidence: float = 0.0
    cited_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class RemediationProposal(BaseModel):
    action: str
    target: ServiceRef
    rollback_target: RollbackTarget
    rollback_plan: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
    runbook_evidence: RunbookEvidence
    payload: dict[str, Any] = Field(default_factory=dict)


class CriticOpinion(BaseModel):
    safe: bool
    rationale: str
    suggested_revision: str | None = None


class PolicyCheckResult(BaseModel):
    verdict: Verdict
    reasons: list[str] = Field(default_factory=list)
    cited_policy: str | None = None
    revision_round: int = 0


# --- Approval / execution ------------------------------------------------


class DryRunResult(BaseModel):
    plan: str
    dry_run_hash: str


class ApprovalRequest(BaseModel):
    approval_id: str
    incident_id: str
    action_type: str
    payload_hash: str
    dry_run_hash: str
    mode: Mode
    status: ApprovalStatus = ApprovalStatus.PENDING
    single_use: bool = True
    created_at: datetime
    expires_at: datetime
    proposed_diff: str = ""


class RecoveryVerification(BaseModel):
    verified: bool
    note: str = ""
    signals: list[SignalSummary] = Field(default_factory=list)


# --- Observability / results ---------------------------------------------


class ToolCallRecord(BaseModel):
    id: str
    incident_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    started_at: datetime
    duration_ms: int = 0


class IncidentTimelineEvent(BaseModel):
    incident_id: str
    ts: datetime
    actor: Actor
    type: str
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    span_id: str | None = None


class E2EResult(BaseModel):
    scenario: str
    runbook: str | None = None
    diagnosis: str = "inconclusive"
    action: str | None = None
    safety_gate: str = "N/A"
    result: str = ""
    mttr_proposal_s: float = 0.0


class EvaluationResult(BaseModel):
    scenario: str
    root_cause_correct: int = 0
    required_evidence_found: float = 0.0
    correct_action_selected: int = 0
    unsafe_action_blocked: int = 0
    groundedness_verified: int = 0
    notes: str = ""


class Incident(BaseModel):
    incident_id: str
    created_at: datetime
    alert: Alert
    scenario: str | None = None
    state: IncidentState = IncidentState.ALERT_RECEIVED
    mode: Mode = Mode.DRY_RUN
    telemetry: TelemetrySummary | None = None
    evidence: EvidenceStack = Field(default_factory=EvidenceStack)
    diagnosis: Diagnosis | None = None
    runbook_id: str | None = None
    runbook_match: RunbookMatch | None = None
    proposal: RemediationProposal | None = None
    policy_check: PolicyCheckResult | None = None
    approval: ApprovalRequest | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    timeline: list[IncidentTimelineEvent] = Field(default_factory=list)
    e2e_result: E2EResult | None = None
