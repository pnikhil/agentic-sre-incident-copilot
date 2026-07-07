"""Milestone 2: a fault emitted by the demo app must be diagnosable by Milestone 1."""

from aegis.adapters.fake_executor import FakeExecutor
from aegis.adapters.file_audit_log import FileAuditLog
from aegis.adapters.local_fixture_telemetry import LocalFixtureTelemetry
from aegis.adapters.local_runbook_store import LocalRunbookStore
from aegis.adapters.memory_approval_store import MemoryApprovalStore
from aegis.adapters.mock_llm import MockLLM
from aegis.app.workflow import Workflow
from aegis.cli import DATA
from aegis.domain.schemas import Alert, DiagnosisStatus, Mode, Verdict
from demoapp.emit import write_scenario
from demoapp.faults import Fault


def _workflow(tmp_path):
    return Workflow(
        telemetry=LocalFixtureTelemetry(tmp_path),
        runbooks=LocalRunbookStore(DATA / "runbooks"),
        llm=MockLLM(),
        executor=FakeExecutor(),
        approvals_store=MemoryApprovalStore(),
        audit=FileAuditLog(tmp_path / "artifacts" / "audit.jsonl"),
        artifacts_dir=tmp_path / "artifacts",
        mode=Mode.DRY_RUN,
    )


def test_emitted_bad_deploy_is_diagnosable(tmp_path):
    out = write_scenario(Fault.BAD_DEPLOY, scenarios_dir=tmp_path / "scenarios", name="gen")
    alert = Alert.model_validate_json((out / "alert.json").read_text())

    inc = _workflow(tmp_path).run(alert=alert, scenario="gen")

    assert inc.diagnosis is not None
    assert inc.diagnosis.status == DiagnosisStatus.CONFIRMED
    assert inc.diagnosis.root_cause == "bad_deploy"
    assert inc.proposal is not None
    assert inc.proposal.action == "rollback_service"
    assert inc.proposal.runbook_evidence.grounded is True
    assert inc.policy_check is not None and inc.policy_check.verdict == Verdict.PASS
    assert inc.approval is not None


def test_emitted_latency_spike_escalates(tmp_path):
    # The Milestone 1 triage only reads http_5xx_rate, which stays below the
    # threshold here, so there is no error_rate_metric evidence and Aegis
    # escalates rather than acting.
    out = write_scenario(Fault.LATENCY_SPIKE, scenarios_dir=tmp_path / "scenarios", name="gen_lat")
    alert = Alert.model_validate_json((out / "alert.json").read_text())

    inc = _workflow(tmp_path).run(alert=alert, scenario="gen_lat")

    assert inc.diagnosis is not None
    assert inc.diagnosis.status == DiagnosisStatus.INCONCLUSIVE
    assert inc.proposal is None
    assert inc.approval is None
