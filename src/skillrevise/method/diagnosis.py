from __future__ import annotations

import json
import re
from typing import Protocol

from skillrevise.method.authoring import SkillConstraintChecker
from skillrevise.llm import LLMClient
from skillrevise.core.models import (
    DiagnosisEvidence,
    DiagnosisReport,
    FailureType,
    PairedEvaluation,
    Skill,
    TaskSpec,
)

GENERIC_MARKERS = (
    "be careful",
    "think step by step",
    "follow best practices",
    "analyze carefully",
    "consider edge cases",
)
ABSOLUTE_MARKERS = ("always", "must", "directly", "without additional", "never")

VIOLATION_TO_FAILURE = {
    "unclear_trigger": FailureType.WRONG_ABSTRACTION_LEVEL,
    "missing_workflow_explicitness": FailureType.WRONG_ABSTRACTION_LEVEL,
    "missing_input_validation": FailureType.FALSE_CERTAINTY,
    "missing_environment_grounding": FailureType.ENVIRONMENT_MISMATCH,
    "missing_fallback_handling": FailureType.FALSE_CERTAINTY,
    "missing_strict_constraints": FailureType.FALSE_CERTAINTY,
    "over_specific_literals": FailureType.OVER_SPECIFICITY,
    "context_pollution_risk": FailureType.CONTEXT_POLLUTION,
    "over_general_guidance": FailureType.OVER_GENERALITY,
    "false_certainty": FailureType.FALSE_CERTAINTY,
}


class Diagnoser(Protocol):
    def diagnose(self, task: TaskSpec, skill: Skill, evaluation: PairedEvaluation) -> DiagnosisReport:
        """Return an execution-grounded diagnosis for a skill evaluation."""


class HeuristicDiagnoser:
    def __init__(self, checker: SkillConstraintChecker | None = None) -> None:
        self.checker = checker or SkillConstraintChecker()

    def diagnose(self, task: TaskSpec, skill: Skill, evaluation: PairedEvaluation) -> DiagnosisReport:
        text = skill.as_markdown().lower()
        labels: list[FailureType] = []
        evidence: list[DiagnosisEvidence] = []
        violations = self.checker.check(skill, task)

        for violation in violations:
            label = VIOLATION_TO_FAILURE.get(violation.code)
            if label is not None and label not in labels:
                labels.append(label)
            evidence.append(
                DiagnosisEvidence(
                    source="authoring_prior",
                    snippet=f"{violation.code} at {violation.location}",
                    reason=f"{violation.message} {violation.suggestion}",
                )
            )

        self._add_execution_failure_evidence(evaluation, labels, evidence)

        if self._looks_over_specific(text, evaluation):
            if FailureType.OVER_SPECIFICITY not in labels:
                labels.append(FailureType.OVER_SPECIFICITY)
            snippet = self._first_matching_line(skill, r"`[^`]+/[^`]+`|\b[a-zA-Z0-9_.-]+\.[a-z]{1,4}\b")
            evidence.append(
                DiagnosisEvidence(
                    source="skill",
                    snippet=snippet or skill.procedure[0],
                    reason="The draft uses file- or command-level literals that are unlikely to transfer.",
                )
            )

        if self._looks_over_general(text):
            if FailureType.OVER_GENERALITY not in labels:
                labels.append(FailureType.OVER_GENERALITY)
            evidence.append(
                DiagnosisEvidence(
                    source="skill",
                    snippet=self._first_matching_line(skill, "|".join(re.escape(marker) for marker in GENERIC_MARKERS))
                    or skill.purpose,
                    reason="The draft relies on broad advice without enough executable workflow structure.",
                )
            )

        if self._has_context_pollution(skill, evaluation):
            if FailureType.CONTEXT_POLLUTION not in labels:
                labels.append(FailureType.CONTEXT_POLLUTION)
            evidence.append(
                DiagnosisEvidence(
                    source="trace",
                    snippet=f"with_skill tokens={evaluation.with_skill.tokens}, no_skill tokens={evaluation.no_skill.tokens}",
                    reason="The skill increases context and execution cost without enough utility gain.",
                )
            )

        if self._has_environment_mismatch(evaluation):
            if FailureType.ENVIRONMENT_MISMATCH not in labels:
                labels.append(FailureType.ENVIRONMENT_MISMATCH)
            event = self._first_event(evaluation, "env_error")
            evidence.append(
                DiagnosisEvidence(
                    source="trace",
                    snippet=event.evidence or event.summary,
                    reason="The trajectory shows environment-level assumptions breaking during execution.",
                )
            )

        if self._has_false_certainty(text, evaluation):
            if FailureType.FALSE_CERTAINTY not in labels:
                labels.append(FailureType.FALSE_CERTAINTY)
            snippet = self._first_matching_line(skill, "|".join(re.escape(marker) for marker in ABSOLUTE_MARKERS))
            evidence.append(
                DiagnosisEvidence(
                    source="skill",
                    snippet=snippet or skill.constraints[0],
                    reason="The draft issues unconditional directions instead of validating before acting.",
                )
            )

        if not labels and evaluation.utility.overall_score <= 0:
            labels.append(FailureType.WRONG_ABSTRACTION_LEVEL)
            evidence.append(
                DiagnosisEvidence(
                    source="comparison",
                    snippet=(
                        f"same-task success gain={evaluation.utility.success_gain}, "
                        f"efficiency gain={evaluation.utility.efficiency_gain:.3f}"
                    ),
                    reason="The draft neither behaves like a reusable workflow nor a precise task-family heuristic.",
                )
            )

        if FailureType.OVER_SPECIFICITY in labels or FailureType.OVER_GENERALITY in labels:
            if FailureType.WRONG_ABSTRACTION_LEVEL not in labels:
                labels.append(FailureType.WRONG_ABSTRACTION_LEVEL)

        causal_judgment = self._build_causal_judgment(evaluation, labels)
        rewrite_targets = self._dedupe_targets(
            self._verifier_specific_rewrite_targets(evidence)
            + [self._rewrite_target(label) for label in labels]
        )
        summary = (
            "No blocking failure detected."
            if not labels
            else "Primary failure is driven by abstraction mismatch and can be revised structurally."
        )
        return DiagnosisReport(
            labels=labels,
            evidence=evidence,
            causal_judgment=causal_judgment,
            rewrite_targets=rewrite_targets,
            summary=summary,
        )

    def _add_execution_failure_evidence(
        self,
        evaluation: PairedEvaluation,
        labels: list[FailureType],
        evidence: list[DiagnosisEvidence],
    ) -> None:
        if evaluation.with_skill.success:
            return

        verifier_event = next((event for event in reversed(evaluation.with_skill.events) if event.kind == "verifier"), None)
        if verifier_event is not None:
            if FailureType.FALSE_CERTAINTY not in labels:
                labels.append(FailureType.FALSE_CERTAINTY)
            snippet = verifier_event.evidence or verifier_event.summary
            evidence.append(
                DiagnosisEvidence(
                    source="verifier",
                    snippet=_shorten(snippet, 900),
                    reason="The benchmark verifier exposed the concrete output/check mismatch that revision should address.",
                )
            )
            return

        outcome_summary = getattr(evaluation.with_skill, "outcome_summary", "")
        if outcome_summary:
            evidence.append(
                DiagnosisEvidence(
                    source="benchmark",
                    snippet=_shorten(outcome_summary, 900),
                    reason="The benchmark outcome should be used as execution evidence during revision.",
                )
            )

    def _looks_over_specific(self, text: str, evaluation: PairedEvaluation) -> bool:
        hardcoded_literals = len(re.findall(r"`[^`]+/[^`]+`|\b[a-zA-Z0-9_.-]+\.[a-z]{1,4}\b", text))
        return hardcoded_literals >= 2 and (
            evaluation.no_skill.success or any(event.kind == "env_error" for event in evaluation.with_skill.events)
        )

    def _looks_over_general(self, text: str) -> bool:
        generic_hits = sum(marker in text for marker in GENERIC_MARKERS)
        imperative_steps = sum(token in text for token in ("verify", "run", "inspect", "edit", "test"))
        return generic_hits >= 2 and imperative_steps <= 3

    def _has_context_pollution(self, skill: Skill, evaluation: PairedEvaluation) -> bool:
        word_count = len(skill.as_markdown().split())
        return word_count > 220 or evaluation.with_skill.tokens > evaluation.no_skill.tokens * 1.25

    def _has_environment_mismatch(self, evaluation: PairedEvaluation) -> bool:
        return any(event.kind == "env_error" for event in evaluation.with_skill.events)

    def _has_false_certainty(self, text: str, evaluation: PairedEvaluation) -> bool:
        return any(marker in text for marker in ABSOLUTE_MARKERS) and any(
            event.kind in {"false_certainty", "assumption_error"} for event in evaluation.with_skill.events
        )

    def _first_event(self, evaluation: PairedEvaluation, kind: str):
        return next(event for event in evaluation.with_skill.events if event.kind == kind)

    def _first_matching_line(self, skill: Skill, pattern: str) -> str | None:
        compiled = re.compile(pattern, re.IGNORECASE)
        for line in skill.lines():
            if compiled.search(line):
                return line.strip()
        return None

    def _build_causal_judgment(self, evaluation: PairedEvaluation, labels: list[FailureType]) -> str:
        if not labels:
            return "No strong evidence that the skill is harming execution under the current protocol."
        if evaluation.no_skill.success and not evaluation.with_skill.success:
            return "The skill likely causes regression by steering the agent toward the wrong procedure."
        if evaluation.with_skill.success and evaluation.utility.efficiency_gain < 0:
            return "The skill is not blocking success, but it adds friction and should be compressed."
        return "The skill underperforms because its guidance shape does not match the task-family requirements."

    def _rewrite_target(self, label: FailureType) -> str:
        targets = {
            FailureType.OVER_SPECIFICITY: "Replace hard-coded paths, commands, and versions with conditional checks.",
            FailureType.OVER_GENERALITY: "Turn broad advice into explicit workflow steps with verifiable checkpoints.",
            FailureType.WRONG_ABSTRACTION_LEVEL: "Rewrite the skill as a mid-level task-family workflow.",
            FailureType.CONTEXT_POLLUTION: "Trim repeated or low-signal text and keep only action-driving guidance.",
            FailureType.ENVIRONMENT_MISMATCH: "Add tool, file, and checker discovery before execution.",
            FailureType.FALSE_CERTAINTY: "Add input validation, fallback handling, and strict constraint checks before acting.",
        }
        return targets[label]

    def _verifier_specific_rewrite_targets(self, evidence: list[DiagnosisEvidence]) -> list[str]:
        text = "\n".join(item.snippet for item in evidence if item.source in {"verifier", "benchmark"}).lower()
        targets: list[str] = []
        graph_contract_failure = (
            "unreachable nodes found" in text
            or "reachability" in text
            or "shape=diamond" in text
            or "choice nodes should be visualized as diamonds" in text
        )
        if "unreachable nodes found" in text or "reachability" in text:
            targets.append(
                "For graph tasks, copy the verifier's terminal-sentinel convention into the skill: if a target such as "
                "`End` is allowed as an edge target but skipped during traversal, keep edges with `to == \"End\"` while "
                "excluding `End` from JSON `nodes`; run the same reachability walk from the declared entry node (for "
                "dialogue graphs, `Start`) and enqueue only non-terminal targets before export."
            )
            targets.append(
                "Make the repair executable as a post-write check: after writing graph JSON/DOT, reload the JSON and "
                "assert `\"End\" not in node_ids`, every edge target is either in `node_ids` or equals `\"End\"`, "
                "reachability from `Start` enqueues only targets not equal to `\"End\"`, no non-terminal node remains "
                "unreachable, and the DOT text contains `shape=diamond` for choice nodes."
            )
        if "shape=diamond" in text or "choice nodes should be visualized as diamonds" in text:
            targets.append(
                "For DOT visualizations, emit explicit `shape=diamond` attributes for choice nodes rather than relying on a global node default."
            )
        if graph_contract_failure:
            targets.append(
                "When fixing a graph verifier assertion, preserve already-passing graph contracts: required node ids/text, "
                "edge text schema, output paths, and DOT visualization conventions such as choice-node diamonds. Do not "
                "prune or rewrite nodes/edges unless the verifier evidence specifically requires it."
            )
        if "file not found" in text or "solution file not found" in text or "no such file" in text:
            targets.append(
                "Before finalizing, assert that every task-specified output path exists and is readable from the verifier-visible location."
            )
        if "expected" in text and ("actual" in text or "assertionerror" in text):
            targets.append(
                "Translate each verifier assertion into a local pre-finalization check with the same expected/actual condition."
            )
        return targets

    def _dedupe_targets(self, targets: list[str]) -> list[str]:
        deduped: list[str] = []
        for target in targets:
            if target not in deduped:
                deduped.append(target)
        return deduped


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


class NoOpDiagnoser:
    """Ablation diagnoser that intentionally withholds failure analysis.

    This is useful for isolating the value of the diagnosis stage while keeping
    authoring, execution, and revision budgets otherwise comparable.
    """

    def diagnose(self, task: TaskSpec, skill: Skill, evaluation: PairedEvaluation) -> DiagnosisReport:
        return DiagnosisReport(
            labels=[],
            evidence=[],
            causal_judgment="Diagnosis disabled for ablation; no causal failure analysis was provided.",
            rewrite_targets=[],
            summary="Diagnosis disabled for ablation.",
        )


class LLMDiagnoser:
    def __init__(
        self,
        llm: LLMClient,
        *,
        fallback: HeuristicDiagnoser | None = None,
        checker: SkillConstraintChecker | None = None,
    ) -> None:
        self.llm = llm
        self.fallback = fallback or HeuristicDiagnoser(checker)
        self.checker = checker or SkillConstraintChecker()

    def diagnose(self, task: TaskSpec, skill: Skill, evaluation: PairedEvaluation) -> DiagnosisReport:
        prompt = self._build_prompt(task, skill, evaluation)
        try:
            response = self.llm.complete(prompt, purpose="skill_diagnosis")
            payload = self._load_json(response.text)
            report = self._parse_report(payload)
            report.evidence.append(
                DiagnosisEvidence(
                    source="llm_metadata",
                    snippet=f"latency_seconds={response.latency_seconds}",
                    reason="LLM diagnosis call completed.",
                )
            )
            return report
        except Exception as exc:
            report = self.fallback.diagnose(task, skill, evaluation)
            report.evidence.append(
                DiagnosisEvidence(
                    source="llm_fallback",
                    snippet=type(exc).__name__,
                    reason=str(exc),
                )
            )
            return report

    def _build_prompt(self, task: TaskSpec, skill: Skill, evaluation: PairedEvaluation) -> str:
        violations = self.checker.check(skill, task)
        violation_lines = "\n".join(
            f"- {item.code}: {item.message} Suggestion: {item.suggestion}" for item in violations
        ) or "- None"
        labels = ", ".join(label.value for label in FailureType)
        return "\n\n".join(
            [
                "Diagnose why an LLM-authored skill helps, hurts, or fails to help a task execution.",
                "Use paired execution evidence, not stylistic preference alone.",
                f"Allowed failure labels: {labels}",
                "Return only JSON with keys: labels, evidence, causal_judgment, rewrite_targets, summary.",
                "Evidence items must have keys: source, snippet, reason.",
                f"Task ID: {task.task_id}",
                f"Task family: {task.family}",
                f"Task instruction:\n{task.instruction}",
                f"Acceptance criteria:\n{json.dumps(task.acceptance_criteria, ensure_ascii=True)}",
                f"Skill:\n{skill.as_markdown()}",
                f"Authoring prior violations:\n{violation_lines}",
                f"No-skill trace:\n{self._trace_summary(evaluation.no_skill)}",
                f"With-skill trace:\n{self._trace_summary(evaluation.with_skill)}",
                f"Utility:\n{json.dumps(evaluation.utility.__dict__, ensure_ascii=True)}",
            ]
        )

    def _trace_summary(self, trace) -> str:
        events = [
            {
                "kind": event.kind,
                "summary": event.summary,
                "evidence": event.evidence,
            }
            for event in trace.events
        ]
        return json.dumps(
            {
                "success": trace.success,
                "status": trace.status,
                "tokens": trace.tokens,
                "tool_calls": trace.tool_calls,
                "steps": trace.steps,
                "latency_seconds": trace.latency_seconds,
                "outcome_summary": trace.outcome_summary,
                "events": events,
            },
            ensure_ascii=True,
        )

    def _load_json(self, text: str) -> dict:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)
        return json.loads(stripped)

    def _parse_report(self, payload: dict) -> DiagnosisReport:
        labels: list[FailureType] = []
        for item in payload.get("labels", []):
            try:
                label = FailureType(str(item))
            except ValueError:
                continue
            if label not in labels:
                labels.append(label)

        evidence = []
        for item in payload.get("evidence", []):
            if not isinstance(item, dict):
                continue
            evidence.append(
                DiagnosisEvidence(
                    source=str(item.get("source", "llm")),
                    snippet=str(item.get("snippet", "")),
                    reason=str(item.get("reason", "")),
                )
            )

        return DiagnosisReport(
            labels=labels,
            evidence=evidence,
            causal_judgment=str(payload.get("causal_judgment", "")),
            rewrite_targets=[str(item) for item in payload.get("rewrite_targets", [])],
            summary=str(payload.get("summary", "")),
        )
