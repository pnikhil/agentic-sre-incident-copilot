"""The platform profile layer.

A profile maps abstract providers (llm, telemetry, deployment, and so on) to
concrete adapters. Kindly note that only the local-fixtures profile is
implemented as of now. The gcp-cloud-run profile is declarative, and its
adapters will come in the later milestones, which form the GCP reference
deployment. The core stays platform-agnostic, and the platform is selected
here at the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .adapters.fake_executor import FakeExecutor
from .adapters.file_audit_log import FileAuditLog
from .adapters.local_fixture_telemetry import LocalFixtureTelemetry
from .adapters.local_runbook_store import LocalRunbookStore
from .adapters.memory_approval_store import MemoryApprovalStore
from .adapters.mock_llm import MockLLM
from .domain.schemas import Capability
from .ports.approval_store import ApprovalStorePort
from .ports.audit_log import AuditLogPort
from .ports.llm import LLMPort
from .ports.remediation_executor import RemediationExecutorPort
from .ports.runbook_store import RunbookStorePort
from .ports.telemetry import TelemetryPort

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"


class Profile(BaseModel):
    """The declarative mapping of abstract providers to adapter names."""

    name: str
    llm_provider: str
    telemetry_provider: str
    deployment_provider: str
    approval_provider: str = "memory"
    secret_provider: str = "env_file"
    vector_store: str = "local_markdown"
    tracing_exporter: str = "none"
    capabilities: list[Capability] = Field(default_factory=list)


# The capabilities that the Milestone 1 workflow needs from any chosen profile.
WORKFLOW_CAPABILITIES: list[Capability] = [
    Capability.QUERY_LOGS,
    Capability.FETCH_METRICS,
    Capability.GET_RECENT_DEPLOYMENTS,
    Capability.SEARCH_RUNBOOKS,
    Capability.DRY_RUN_ROLLBACK,
]


def check_capabilities(profile: Profile, required: list[Capability]) -> None:
    """Fails fast if the chosen profile does not advertise a needed capability.

    Kindly note that this runs before any adapter is wired, so a wrong profile is
    caught early with a clear message.
    """
    missing = [c for c in required if c not in profile.capabilities]
    if missing:
        raise ValueError(
            f"The profile '{profile.name}' is missing the required capabilities: "
            f"{[c.value for c in missing]}. Kindly pick a profile that supports them."
        )


@dataclass
class Adapters:
    """The concrete adapter set that a profile has been resolved into."""

    llm: LLMPort
    telemetry: TelemetryPort
    runbooks: RunbookStorePort
    executor: RemediationExecutorPort
    approvals: ApprovalStorePort
    audit: AuditLogPort


def load_profile(name: str) -> Profile:
    """Loads a profile by name from the profiles directory."""
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"profile not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile(**data)


def _not_implemented(provider: str, kind: str) -> None:
    raise NotImplementedError(
        f"The '{provider}' {kind} provider is not implemented yet. As of now only "
        "the local-fixtures profile is wired. The GCP reference adapters will come "
        "in the later milestones."
    )


def build_adapters(profile: Profile, *, data_dir: Path, artifacts_dir: Path) -> Adapters:
    """Resolves a profile into concrete adapters.

    Only the local providers are implemented at present. Kindly note that any
    other provider will raise NotImplementedError with a clear message, so that
    the seam is honest about what is ready and what is not.
    """
    check_capabilities(profile, WORKFLOW_CAPABILITIES)

    if profile.llm_provider == "mock":
        llm: LLMPort = MockLLM()
    else:
        _not_implemented(profile.llm_provider, "llm")

    if profile.telemetry_provider == "fixture":
        telemetry: TelemetryPort = LocalFixtureTelemetry(data_dir)
    else:
        _not_implemented(profile.telemetry_provider, "telemetry")

    if profile.vector_store == "local_markdown":
        runbooks: RunbookStorePort = LocalRunbookStore(data_dir / "runbooks")
    else:
        _not_implemented(profile.vector_store, "vector_store")

    if profile.deployment_provider in ("fake_executor", "fake"):
        executor: RemediationExecutorPort = FakeExecutor()
    else:
        _not_implemented(profile.deployment_provider, "deployment")

    if profile.approval_provider in ("memory", "local_file"):
        approvals: ApprovalStorePort = MemoryApprovalStore()
    else:
        _not_implemented(profile.approval_provider, "approval")

    audit: AuditLogPort = FileAuditLog(artifacts_dir / "audit.jsonl")

    return Adapters(
        llm=llm,
        telemetry=telemetry,
        runbooks=runbooks,
        executor=executor,
        approvals=approvals,
        audit=audit,
    )
