"""Milestone 6: the deterministic evaluation harness over the golden scenarios."""

from aegis.eval.harness import GOLDEN_SCENARIOS, evaluate
from aegis.eval.grader import GroundTruth, grade
from aegis.cli import build_workflow, load_alert
from aegis.domain.schemas import Mode


def test_golden_scenarios_all_pass():
    report = evaluate()

    assert report.total == len(GOLDEN_SCENARIOS)
    assert report.passed == report.total
    assert report.diagnosis_accuracy == 1.0
    assert report.correct_action_rate == 1.0
    assert report.groundedness_rate == 1.0
    assert report.safe_refusal_rate == 1.0
    assert report.required_evidence_rate == 1.0
    assert report.latency_p95_ms >= 0


def test_grader_flags_a_wrong_diagnosis():
    """A deliberately wrong ground truth must make the grader fail the scenario."""
    wf = build_workflow(Mode.DRY_RUN)
    inc = wf.run(alert=load_alert("bad_deploy"), scenario="bad_deploy")

    wrong = GroundTruth(root_cause="inconclusive", expected_action="escalate")
    result = grade(inc, wrong, latency_ms=5)

    # bad_deploy is actually confirmed and acted upon, so an "inconclusive"
    # ground truth must be graded as a failure.
    assert result.root_cause_correct == 0
    assert result.passed is False
