from __future__ import annotations

from collections.abc import Sequence

from skillrevise.method.authoring import SkillAuthor
from skillrevise.method.diagnosis import Diagnoser
from skillrevise.core.metrics import trace_outcome_score
from skillrevise.core.models import ExecutionTrace, HarnessIteration, HarnessResult, PairedEvaluation, RepairPrinciple, Skill, TaskSpec
from skillrevise.method.principles import PrincipleAbsorber
from skillrevise.method.revision import RevisionEngine
from skillrevise.core.runner import PairedRunner


class HarnessLoop:
    def __init__(
        self,
        *,
        author: SkillAuthor,
        runner: PairedRunner,
        diagnoser: Diagnoser,
        reviser: RevisionEngine,
        max_revisions: int = 1,
        principle_absorber: PrincipleAbsorber | None = None,
        continue_after_non_improving_revision: bool = False,
        require_diagnosis_for_revision: bool = True,
    ) -> None:
        self.author = author
        self.runner = runner
        self.diagnoser = diagnoser
        self.reviser = reviser
        self.max_revisions = max_revisions
        self.principle_absorber = principle_absorber
        self.absorbed_principles: list[RepairPrinciple] = []
        self.continue_after_non_improving_revision = continue_after_non_improving_revision
        self.require_diagnosis_for_revision = require_diagnosis_for_revision

    def run_task(self, task: TaskSpec, *, heldout_tasks: Sequence[TaskSpec] | None = None) -> HarnessResult:
        initial_skill = self.author.author(task)
        iterations: list[HarnessIteration] = []

        current_skill = initial_skill
        current_eval = self.runner.evaluate(task, current_skill, transfer_tasks=heldout_tasks)
        best_skill = current_skill
        best_eval = current_eval

        for iteration_index in range(self.max_revisions + 1):
            diagnosis = self.diagnoser.diagnose(task, current_skill, current_eval)
            revision = None

            if iteration_index < self.max_revisions and self._should_revise(current_eval, diagnosis):
                revision = self.reviser.revise(task, current_skill, diagnosis)

            iterations.append(
                HarnessIteration(
                    iteration_index=iteration_index,
                    skill=current_skill,
                    evaluation=current_eval,
                    diagnosis=diagnosis,
                    revision=revision,
                )
            )

            if revision is None:
                break

            candidate_eval = self.runner.evaluate(task, revision.revised_skill, transfer_tasks=heldout_tasks)
            if self._is_better(candidate_eval, best_eval):
                best_skill = revision.revised_skill
                best_eval = candidate_eval

            if self._is_better(candidate_eval, current_eval):
                current_skill = revision.revised_skill
                current_eval = candidate_eval
            elif self.continue_after_non_improving_revision and iteration_index + 1 < self.max_revisions:
                current_skill = revision.revised_skill
                current_eval = candidate_eval
            else:
                iterations.append(
                    HarnessIteration(
                        iteration_index=iteration_index + 1,
                        skill=revision.revised_skill,
                        evaluation=candidate_eval,
                        diagnosis=self.diagnoser.diagnose(task, revision.revised_skill, candidate_eval),
                        revision=None,
                    )
                )
                break

        result = HarnessResult(
            task=task,
            initial_skill=initial_skill,
            iterations=iterations,
            selected_skill=best_skill,
            selected_evaluation=best_eval,
        )
        self._absorb_episode_if_enabled(result)
        return result

    def _is_better(self, candidate: PairedEvaluation, incumbent: PairedEvaluation) -> bool:
        if candidate.utility.overall_score != incumbent.utility.overall_score:
            return candidate.utility.overall_score > incumbent.utility.overall_score
        if candidate.with_skill.success != incumbent.with_skill.success:
            return candidate.with_skill.success and not incumbent.with_skill.success
        candidate_has_valid_trace = self._has_selectable_with_skill_trace(candidate)
        incumbent_has_valid_trace = self._has_selectable_with_skill_trace(incumbent)
        if candidate_has_valid_trace != incumbent_has_valid_trace:
            return candidate_has_valid_trace
        return self._efficiency_key(candidate.with_skill) < self._efficiency_key(incumbent.with_skill)

    def _efficiency_key(self, trace: ExecutionTrace) -> tuple[int, int, int, int]:
        token_count = self._positive_int_or_none(trace.tokens)
        tool_calls = self._nonnegative_int(trace.tool_calls)
        steps = self._nonnegative_int(trace.steps)
        if token_count is not None:
            return (0, token_count, tool_calls, steps)
        return (1, tool_calls, steps, 0)

    def _positive_int_or_none(self, value: int | float | None) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _nonnegative_int(self, value: int | float | None) -> int:
        if isinstance(value, bool) or value is None:
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _has_selectable_with_skill_trace(self, evaluation: PairedEvaluation) -> bool:
        trace = evaluation.with_skill
        if self._trace_timed_out(trace):
            return False
        if trace_outcome_score(trace) is None:
            return False
        if not trace.events and trace.tool_calls == 0:
            return False
        return True

    def _trace_timed_out(self, trace: ExecutionTrace) -> bool:
        return bool(trace.metadata.get("timed_out")) or trace.status == "timeout"

    def _is_valid_for_revision(self, evaluation: PairedEvaluation) -> bool:
        if not any("no valid benchmark reward" in note for note in evaluation.utility.notes):
            return True
        trace = evaluation.with_skill
        if self._trace_timed_out(trace):
            return False
        return bool(trace.events) or trace.tool_calls > 0 or trace.steps > 0

    def _should_revise(self, evaluation: PairedEvaluation, diagnosis) -> bool:
        if self.require_diagnosis_for_revision and not diagnosis.labels:
            return False
        if not self._is_valid_for_revision(evaluation):
            return False
        reward = evaluation.with_skill.metadata.get("reward")
        if evaluation.with_skill.success and isinstance(reward, (int, float)) and reward >= 1.0:
            return False
        return bool(diagnosis.labels) or not self.require_diagnosis_for_revision

    def _absorb_episode_if_enabled(self, result: HarnessResult) -> None:
        if self.principle_absorber is None:
            return
        absorbed = self.principle_absorber.absorb_episode(result)
        if absorbed is not None:
            self.absorbed_principles.append(absorbed)
