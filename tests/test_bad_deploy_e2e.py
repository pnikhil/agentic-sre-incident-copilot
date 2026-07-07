"""End-to-end test for the Milestone 1 first demo contract, on the bad_deploy scenario."""

from aegis.cli import build_workflow, load_alert
from aegis.domain.schemas import DiagnosisStatus, Mode, Verdict


def test_bad_deploy_first_demo_contract():
    wf = build_workflow(Mode.DRY_RUN)
    alert = load_alert("bad_deploy")

    inc = wf.run(alert=alert, scenario="bad_deploy")

    # 1-2. incident + evidence (side-channel)
    assert inc.incident_id.startswith("inc_")
    assert {"error_rate_metric", "recent_deployment", "application_error_logs"} <= inc.evidence.kinds()

    # 3-5. grounded diagnosis citing evidence, applicable runbook, grounded proposal
    assert inc.diagnosis is not None
    assert inc.diagnosis.status == DiagnosisStatus.CONFIRMED
    assert inc.diagnosis.root_cause == "bad_deploy"
    assert inc.diagnosis.cited_evidence_ids
    assert inc.runbook_id == "checkout-bad-deploy-rollback"
    assert inc.runbook_match is not None and inc.runbook_match.applies
    assert inc.proposal is not None
    assert inc.proposal.action == "rollback_service"
    assert inc.proposal.runbook_evidence.grounded is True

    # 6. bounded critic passed
    assert inc.policy_check is not None
    assert inc.policy_check.verdict == Verdict.PASS

    # 7. dry-run approval with hashes
    assert inc.approval is not None
    assert inc.approval.mode == Mode.DRY_RUN
    assert inc.approval.payload_hash.startswith("sha256:")
    assert inc.approval.dry_run_hash.startswith("sha256:")

    # 8. timeline + E2E row
    assert inc.timeline
    assert inc.e2e_result is not None
    assert inc.e2e_result.action == "rollback_service"
    assert inc.e2e_result.safety_gate == "Pass"


def test_inconclusive_is_success_when_no_deploy():
    """Restraint check. With no correlating deploy evidence, Aegis must not make up a cause."""
    from aegis.domain.schemas import EvidenceStack, Evidence
    from aegis.adapters.mock_llm import MockLLM

    alert = load_alert("bad_deploy")
    llm = MockLLM()
    # Only a metric spike is present, with no deployment evidence, so it should be inconclusive.
    evidence = EvidenceStack(
        items=[Evidence(id="ev_metric_001", kind="error_rate_metric",
                        summary="spike", source_tool="fetch_metrics")]
    )
    diagnosis = llm.diagnose(alert=alert, evidence=evidence, runbook=None)
    assert diagnosis.status == DiagnosisStatus.INCONCLUSIVE
