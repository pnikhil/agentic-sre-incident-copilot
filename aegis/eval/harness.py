"""The evaluation harness. It runs the golden scenarios through the workflow, grades
each one deterministically, and aggregates the metrics."""

from __future__ import annotations

from time import perf_counter

from pydantic import BaseModel, Field

from ..cli import DATA, build_workflow, load_alert
from ..domain.schemas import EvaluationResult, Mode
from .grader import GroundTruth, grade

# Keep generated_* scenarios out so evals stay deterministic.
GOLDEN_SCENARIOS = ["bad_deploy", "ambiguous_telemetry", "latency_spike"]


class EvaluationReport(BaseModel):
    total: int
    passed: int
    diagnosis_accuracy: float
    correct_action_rate: float
    groundedness_rate: float
    safe_refusal_rate: float
    required_evidence_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    results: list[EvaluationResult] = Field(default_factory=list)


def load_ground_truth(scenario: str) -> GroundTruth:
    path = DATA / "scenarios" / scenario / "ground_truth.json"
    return GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate(scenarios: list[str] | None = None) -> EvaluationReport:
    scenarios = scenarios or GOLDEN_SCENARIOS
    results: list[EvaluationResult] = []
    for scenario in scenarios:
        workflow = build_workflow(Mode.DRY_RUN)
        alert = load_alert(scenario)
        started = perf_counter()
        incident = workflow.run(alert=alert, scenario=scenario)
        latency_ms = int((perf_counter() - started) * 1000)
        results.append(grade(incident, load_ground_truth(scenario), latency_ms=latency_ms))
    return _aggregate(results)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


def _aggregate(results: list[EvaluationResult]) -> EvaluationReport:
    return EvaluationReport(
        total=len(results),
        passed=sum(r.passed for r in results),
        diagnosis_accuracy=_mean([r.root_cause_correct for r in results]),
        correct_action_rate=_mean([r.correct_action_selected for r in results]),
        groundedness_rate=_mean([r.groundedness_verified for r in results]),
        safe_refusal_rate=_mean([r.unsafe_action_blocked for r in results]),
        required_evidence_rate=_mean([r.required_evidence_found for r in results]),
        latency_p50_ms=_percentile([r.latency_ms for r in results], 50),
        latency_p95_ms=_percentile([r.latency_ms for r in results], 95),
        results=results,
    )


def format_report(report: EvaluationReport) -> str:
    lines = [
        "| Scenario | RootCause | Evidence | Action | Safe | Grounded | Tools | Latency(ms) | Pass |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report.results:
        lines.append(
            f"| {r.scenario} | {r.root_cause_correct} | {r.required_evidence_found} | "
            f"{r.correct_action_selected} | {r.unsafe_action_blocked} | "
            f"{r.groundedness_verified} | {r.tool_calls} | {r.latency_ms} | "
            f"{'PASS' if r.passed else 'FAIL'} |"
        )
    lines += [
        "",
        f"passed:                 {report.passed}/{report.total}",
        f"diagnosis_accuracy:     {report.diagnosis_accuracy}",
        f"correct_action_rate:    {report.correct_action_rate}",
        f"groundedness_rate:      {report.groundedness_rate}",
        f"safe_refusal_rate:      {report.safe_refusal_rate}",
        f"required_evidence_rate: {report.required_evidence_rate}",
        f"latency p50 / p95 (ms): {report.latency_p50_ms} / {report.latency_p95_ms}",
    ]
    return "\n".join(lines)
