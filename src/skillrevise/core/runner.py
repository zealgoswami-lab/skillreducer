from __future__ import annotations

from collections.abc import Sequence
import os
from typing import Any

from skillrevise.core.agents import AgentAdapter
from skillrevise.core.env import get_env
from skillrevise.core.metrics import UtilityWeights, compute_utility, trace_outcome_score
from skillrevise.core.models import ExecutionTrace, PairedEvaluation, Skill, TaskSpec


class PairedRunner:
    def __init__(
        self,
        adapter: AgentAdapter,
        *,
        weights: UtilityWeights | None = None,
        baseline_traces: dict[str, ExecutionTrace] | None = None,
        max_evaluation_attempts: int | None = None,
    ) -> None:
        self.adapter = adapter
        self.weights = weights or UtilityWeights()
        self._baseline_cache: dict[str, ExecutionTrace] = dict(baseline_traces or {})
        if max_evaluation_attempts is None:
            max_evaluation_attempts = _env_int("SKILL_REVISE_EVALUATION_RETRY_ATTEMPTS", 3)
        self.max_evaluation_attempts = max(1, int(max_evaluation_attempts))

    def evaluate(
        self,
        task: TaskSpec,
        skill: Skill,
        *,
        transfer_tasks: Sequence[TaskSpec] | None = None,
    ) -> PairedEvaluation:
        baseline = self._baseline_cache.get(task.task_id)
        if baseline is None:
            baseline = self._run_with_retries(task, None)
            self._baseline_cache[task.task_id] = baseline
        no_skill = baseline
        with_skill = self._run_with_retries(task, skill)

        transfer_gain = 0.0
        pair_is_valid = trace_outcome_score(no_skill) is not None and trace_outcome_score(with_skill) is not None
        interference_rate = 1.0 if pair_is_valid and no_skill.success and not with_skill.success else 0.0
        transfer_summary: dict[str, float] = {}
        if transfer_tasks:
            transfer_gain, transfer_interference = self.evaluate_family(skill, transfer_tasks)
            interference_rate = max(interference_rate, transfer_interference)
            transfer_summary = {
                "num_tasks": float(len(transfer_tasks)),
                "transfer_gain": transfer_gain,
                "interference_rate": transfer_interference,
            }

        utility = compute_utility(
            no_skill,
            with_skill,
            transfer_gain=transfer_gain,
            interference_cost=interference_rate,
            weights=self.weights,
        )
        return PairedEvaluation(
            task=task,
            skill=skill,
            no_skill=no_skill,
            with_skill=with_skill,
            utility=utility,
            transfer_summary=transfer_summary,
        )

    def evaluate_family(self, skill: Skill, tasks: Sequence[TaskSpec]) -> tuple[float, float]:
        if not tasks:
            return 0.0, 0.0
        success_gains: list[float] = []
        interference = 0
        for task in tasks:
            baseline = self._baseline_cache.get(task.task_id)
            if baseline is None:
                baseline = self._run_with_retries(task, None)
                self._baseline_cache[task.task_id] = baseline
            no_skill = baseline
            with_skill = self._run_with_retries(task, skill)
            no_skill_score = trace_outcome_score(no_skill)
            with_skill_score = trace_outcome_score(with_skill)
            if no_skill_score is None or with_skill_score is None:
                continue
            success_gains.append(with_skill_score - no_skill_score)
            if no_skill.success and not with_skill.success:
                interference += 1
        if not success_gains:
            return 0.0, 0.0
        avg_transfer = sum(success_gains) / len(success_gains)
        interference_rate = interference / len(success_gains)
        return avg_transfer, interference_rate

    def _run_with_retries(self, task: TaskSpec, skill: Skill | None) -> ExecutionTrace:
        previous_attempts: list[dict[str, Any]] = []
        for attempt in range(1, self.max_evaluation_attempts + 1):
            trace = self.adapter.run(task, skill)
            retry_reasons = self._evaluation_retry_reasons(trace)
            trace.metadata["evaluation_attempt"] = attempt
            trace.metadata["evaluation_retry_attempts"] = attempt
            trace.metadata["evaluation_retry_max_attempts"] = self.max_evaluation_attempts
            if previous_attempts:
                trace.metadata["evaluation_previous_attempts"] = previous_attempts
            if not retry_reasons:
                if previous_attempts:
                    trace.metadata["evaluation_retry_recovered"] = True
                return trace
            trace.metadata["evaluation_retry_reasons"] = retry_reasons
            if attempt >= self.max_evaluation_attempts:
                trace.metadata["evaluation_retry_exhausted"] = True
                self._mark_retry_exhausted(trace)
                return trace
            previous_attempts.append(self._summarize_retry_attempt(trace, attempt, retry_reasons))
        raise AssertionError("unreachable")

    def _evaluation_retry_reasons(self, trace: ExecutionTrace) -> list[str]:
        reasons: list[str] = []
        if self._trace_timed_out(trace):
            reasons.append("timed_out")
        if trace_outcome_score(trace) is None:
            reasons.append("missing_reward")
        if not trace.events and trace.tool_calls == 0:
            reasons.append("empty_trace")
        return reasons

    def _summarize_retry_attempt(
        self,
        trace: ExecutionTrace,
        attempt: int,
        retry_reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "attempt": attempt,
            "status": trace.status,
            "success": trace.success,
            "timed_out": self._trace_timed_out(trace),
            "reward": trace.metadata.get("reward"),
            "tokens": trace.tokens,
            "tool_calls": trace.tool_calls,
            "steps": trace.steps,
            "events": len(trace.events),
            "retry_reasons": list(retry_reasons),
        }

    def _trace_timed_out(self, trace: ExecutionTrace) -> bool:
        return bool(trace.metadata.get("timed_out")) or trace.status == "timeout"

    def _mark_retry_exhausted(self, trace: ExecutionTrace) -> None:
        trace.success = False
        if trace.status == "success":
            trace.status = "failed"
        trace.metadata["evaluation_forced_failed_after_retries"] = True


def _env_int(name: str, default: int) -> int:
    raw = get_env(os.environ, name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default
