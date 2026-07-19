from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from skillrevise.core.metrics import trace_outcome_score
from skillrevise.core.models import ExecutionTrace, HarnessResult, PairedEvaluation, TaskSpec


METRIC_KEYS = (
    "success_rate",
    "outcome_score",
    "success_gain",
    "efficiency_gain",
    "transfer_gain",
    "interference_cost",
    "overall_score",
    "tokens",
    "tool_calls",
    "steps",
    "latency_seconds",
)


def summarize_results(results: Sequence[HarnessResult]) -> dict[str, Any]:
    """Build compact aggregate tables from harness results.

    The returned structure is JSON-friendly and intentionally close to the paper tables:
    no-skill baseline, initial direct-skill performance, selected skill performance,
    revision delta, transfer signal, and failure taxonomy counts.
    """

    initial_evals = [result.iterations[0].evaluation for result in results if result.iterations]
    selected_evals = [result.selected_evaluation for result in results]
    no_skill_evals = [result.iterations[0].evaluation for result in results if result.iterations]

    failure_counts: Counter[str] = Counter()
    initial_failure_counts: Counter[str] = Counter()
    for result in results:
        for iteration in result.iterations:
            failure_counts.update(label.value for label in iteration.diagnosis.labels)
        if result.iterations:
            initial_failure_counts.update(label.value for label in result.iterations[0].diagnosis.labels)

    version_counts = Counter(result.selected_skill.version for result in results)
    accepted = sum(int(_skill_is_accepted(result)) for result in results)
    family_rows = _summarize_by_family(results)

    return {
        "num_tasks": len(results),
        "main_table": {
            "no_skill": _aggregate_no_skill(no_skill_evals),
            "initial_skill": _aggregate_evaluations(initial_evals),
            "selected_skill": _aggregate_evaluations(selected_evals),
            "revision_delta": _delta(_aggregate_evaluations(selected_evals), _aggregate_evaluations(initial_evals)),
        },
        "transfer_table": {
            "initial_skill": _aggregate_transfer(initial_evals),
            "selected_skill": _aggregate_transfer(selected_evals),
        },
        "failure_taxonomy_table": {
            "initial": dict(sorted(initial_failure_counts.items())),
            "all_iterations": dict(sorted(failure_counts.items())),
        },
        "selection_table": {
            "selected_versions": dict(sorted(version_counts.items())),
            "changed_by_revision": sum(
                int(result.selected_skill.version != result.initial_skill.version) for result in results
            ),
            "accepted_skills": accepted,
            "rejected_skills": len(results) - accepted,
            "acceptance_rate": round(accepted / len(results), 6) if results else 0.0,
        },
        "family_table": family_rows,
        "per_task": [_task_row(result) for result in results],
    }


def summarize_baseline_runs(items: Sequence[tuple[TaskSpec, ExecutionTrace]]) -> dict[str, Any]:
    traces = [trace for _, trace in items]
    return {
        "num_tasks": len(items),
        "baseline_table": _aggregate_traces(traces),
        "per_task": [
            {
                "task_id": task.task_id,
                "family": task.family,
                "success": trace.success,
                "status": trace.status,
                "outcome_score": _round_optional(trace_outcome_score(trace)),
                "latency_seconds": trace.latency_seconds,
                "tokens": trace.tokens,
                "tool_calls": trace.tool_calls,
                "steps": trace.steps,
                "outcome_summary": trace.outcome_summary,
            }
            for task, trace in items
        ],
    }


def _aggregate_no_skill(evaluations: Sequence[PairedEvaluation]) -> dict[str, float]:
    traces = [evaluation.no_skill for evaluation in evaluations]
    return _aggregate_traces(traces)


def _aggregate_traces(traces: Sequence[ExecutionTrace]) -> dict[str, float]:
    if not traces:
        return _empty_metrics()
    return {
        "success_rate": _mean(float(trace.success) for trace in traces),
        "outcome_score": _mean(_score_or_zero(trace) for trace in traces),
        "success_gain": 0.0,
        "efficiency_gain": 0.0,
        "transfer_gain": 0.0,
        "interference_cost": 0.0,
        "overall_score": 0.0,
        "tokens": _mean(trace.tokens for trace in traces),
        "tool_calls": _mean(trace.tool_calls for trace in traces),
        "steps": _mean(trace.steps for trace in traces),
        "latency_seconds": _mean(trace.latency_seconds for trace in traces),
    }


def _aggregate_evaluations(evaluations: Sequence[PairedEvaluation]) -> dict[str, float]:
    if not evaluations:
        return _empty_metrics()
    return {
        "success_rate": _mean(float(evaluation.with_skill.success) for evaluation in evaluations),
        "outcome_score": _mean(_score_or_zero(evaluation.with_skill) for evaluation in evaluations),
        "success_gain": _mean(evaluation.utility.success_gain for evaluation in evaluations),
        "efficiency_gain": _mean(evaluation.utility.efficiency_gain for evaluation in evaluations),
        "transfer_gain": _mean(evaluation.utility.transfer_gain for evaluation in evaluations),
        "interference_cost": _mean(evaluation.utility.interference_cost for evaluation in evaluations),
        "overall_score": _mean(evaluation.utility.overall_score for evaluation in evaluations),
        "tokens": _mean(evaluation.with_skill.tokens for evaluation in evaluations),
        "tool_calls": _mean(evaluation.with_skill.tool_calls for evaluation in evaluations),
        "steps": _mean(evaluation.with_skill.steps for evaluation in evaluations),
        "latency_seconds": _mean(evaluation.with_skill.latency_seconds for evaluation in evaluations),
    }


def _aggregate_transfer(evaluations: Sequence[PairedEvaluation]) -> dict[str, float]:
    if not evaluations:
        return {"num_evaluated": 0.0, "avg_transfer_gain": 0.0, "avg_interference_rate": 0.0}
    evaluated = [item for item in evaluations if item.transfer_summary]
    if not evaluated:
        return {"num_evaluated": 0.0, "avg_transfer_gain": 0.0, "avg_interference_rate": 0.0}
    return {
        "num_evaluated": float(len(evaluated)),
        "avg_transfer_gain": _mean(item.transfer_summary.get("transfer_gain", 0.0) for item in evaluated),
        "avg_interference_rate": _mean(item.transfer_summary.get("interference_rate", 0.0) for item in evaluated),
    }


def _summarize_by_family(results: Sequence[HarnessResult]) -> list[dict[str, float | str]]:
    grouped: dict[str, list[HarnessResult]] = defaultdict(list)
    for result in results:
        grouped[result.task.family].append(result)

    rows: list[dict[str, float | str]] = []
    for family, items in sorted(grouped.items()):
        selected = _aggregate_evaluations([item.selected_evaluation for item in items])
        initial = _aggregate_evaluations([item.iterations[0].evaluation for item in items if item.iterations])
        rows.append(
            {
                "family": family,
                "num_tasks": float(len(items)),
                "initial_overall_score": initial["overall_score"],
                "selected_overall_score": selected["overall_score"],
                "selected_success_rate": selected["success_rate"],
                "selected_transfer_gain": selected["transfer_gain"],
            }
        )
    return rows


def _task_row(result: HarnessResult) -> dict[str, Any]:
    initial_eval = result.iterations[0].evaluation
    selected_eval = result.selected_evaluation
    return {
        "task_id": result.task.task_id,
        "family": result.task.family,
        "initial_version": result.initial_skill.version,
        "selected_version": result.selected_skill.version,
        "skill_accepted": _skill_is_accepted(result),
        "no_skill_success": initial_eval.no_skill.success,
        "initial_success": initial_eval.with_skill.success,
        "selected_success": selected_eval.with_skill.success,
        "no_skill_outcome_score": _round_optional(trace_outcome_score(initial_eval.no_skill)),
        "initial_outcome_score": _round_optional(trace_outcome_score(initial_eval.with_skill)),
        "selected_outcome_score": _round_optional(trace_outcome_score(selected_eval.with_skill)),
        "initial_overall_score": round(initial_eval.utility.overall_score, 6),
        "selected_overall_score": round(selected_eval.utility.overall_score, 6),
        "initial_failure_labels": [label.value for label in result.iterations[0].diagnosis.labels],
        "selected_transfer_gain": round(selected_eval.utility.transfer_gain, 6),
    }


def _delta(current: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    return {key: round(current.get(key, 0.0) - baseline.get(key, 0.0), 6) for key in METRIC_KEYS}


def _empty_metrics() -> dict[str, float]:
    return {key: 0.0 for key in METRIC_KEYS}


def _score_or_zero(trace) -> float:
    score = trace_outcome_score(trace)
    return 0.0 if score is None else score


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _skill_is_accepted(result: HarnessResult) -> bool:
    return result.selected_evaluation.utility.overall_score > 0.0


def _mean(values) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 6)
