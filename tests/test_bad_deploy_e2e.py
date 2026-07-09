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
    assert inc.proposal.target.service == alert.service
    assert inc.proposal.rollback_target.strategy == "previous_stable_revision"

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

    # M4: the agents call tools only through the MCP gateway, and every tool call
    # is recorded and stamped with the incident_id.
    tool_names = {tc.tool for tc in inc.tool_calls}
    assert {"search_runbooks", "fetch_metrics", "query_logs",
            "get_recent_deployments"} <= tool_names
    assert all(tc.incident_id == inc.incident_id for tc in inc.tool_calls)


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


def test_ambiguous_telemetry_escalates():
    """The error spike has no correlating recent deploy, so Aegis must escalate and not act."""
    wf = build_workflow(Mode.DRY_RUN)
    alert = load_alert("ambiguous_telemetry")

    inc = wf.run(alert=alert, scenario="ambiguous_telemetry")

    assert inc.diagnosis is not None
    assert inc.diagnosis.status == DiagnosisStatus.INCONCLUSIVE
    # Restraint: no proposal, no approval, and the incident is escalated.
    assert inc.proposal is None
    assert inc.approval is None
    assert inc.e2e_result is not None
    assert inc.e2e_result.result == "Escalated (inconclusive)"
    assert inc.e2e_result.action is None
    assert any(ev.type == "escalated" for ev in inc.timeline)


def test_gcp_profile_is_declarative_only():
    """The GCP reference profile loads, but kindly note that its adapters are not
    implemented yet, whereas the local-fixtures profile builds cleanly."""
    import pytest

    from aegis.cli import ARTIFACTS, DATA
    from aegis.platform import build_adapters, load_profile

    gcp = load_profile("gcp-cloud-run")
    assert gcp.name == "gcp-cloud-run"
    assert gcp.llm_provider == "vertex_gemini"
    with pytest.raises(NotImplementedError):
        build_adapters(gcp, data_dir=DATA, artifacts_dir=ARTIFACTS)

    local = load_profile("local-fixtures")
    adapters = build_adapters(local, data_dir=DATA, artifacts_dir=ARTIFACTS)
    assert adapters.llm is not None
    assert adapters.telemetry is not None


def test_tfidf_store_ranks_rollback_over_latency():
    """The local vector store should rank the rollback runbook above the latency one."""
    from aegis.adapters.tfidf_runbook_store import TfidfRunbookStore
    from aegis.cli import DATA

    store = TfidfRunbookStore(DATA / "runbooks")
    hits = store.search("checkout-api http 5xx error rate after deployment", limit=2)
    assert hits[0].runbook_id == "checkout-bad-deploy-rollback"
    assert hits[0].score > 0


def test_triage_follows_recipe_subset():
    """When the recipe names only one tool, triage must collect only that evidence."""
    from aegis.adapters.local_fixture_telemetry import LocalFixtureTelemetry
    from aegis.adapters.tfidf_runbook_store import TfidfRunbookStore
    from aegis.app.triage import TriageAgent
    from aegis.cli import DATA
    from aegis.mcp.gateway import MCPToolGateway
    from aegis.mcp.tools import DiagnosticTools

    gateway = MCPToolGateway(
        DiagnosticTools(LocalFixtureTelemetry(DATA), TfidfRunbookStore(DATA / "runbooks"))
    )
    _telemetry, evidence, tool_calls = TriageAgent().run(
        "inc_test", gateway, scenario="bad_deploy", service="checkout-api",
        recipe=[{"tool": "fetch_metrics"}],
    )
    assert "error_rate_metric" in evidence.kinds()
    assert "recent_deployment" not in evidence.kinds()
    assert len(tool_calls) == 1
    assert tool_calls[0].tool == "fetch_metrics"
    assert tool_calls[0].incident_id == "inc_test"


def test_mcp_gateway_records_and_returns_typed_results():
    """The gateway must return typed results and a ToolCallRecord for each call."""
    from aegis.adapters.local_fixture_telemetry import LocalFixtureTelemetry
    from aegis.adapters.tfidf_runbook_store import TfidfRunbookStore
    from aegis.cli import DATA
    from aegis.mcp.gateway import MCPToolGateway
    from aegis.mcp.tools import DiagnosticTools

    gateway = MCPToolGateway(
        DiagnosticTools(LocalFixtureTelemetry(DATA), TfidfRunbookStore(DATA / "runbooks"))
    )
    assert set(gateway.list_tools()) == {
        "fetch_metrics", "query_logs", "get_recent_deployments", "search_runbooks"
    }
    result, record = gateway.call(
        "search_runbooks", {"query": "checkout-api 5xx after deployment", "limit": 2},
        incident_id="inc_gw",
    )
    assert result.hits and result.hits[0].id == "checkout-bad-deploy-rollback"
    assert record.tool == "search_runbooks"
    assert record.incident_id == "inc_gw"
    assert record.ok is True


def test_build_workflow_gcp_profile_not_implemented():
    """Through the real build_workflow entrypoint, the GCP profile is declarative only."""
    import pytest

    from aegis.domain.schemas import Mode

    with pytest.raises(NotImplementedError):
        build_workflow(Mode.DRY_RUN, profile_name="gcp-cloud-run")
