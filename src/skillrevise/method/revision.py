from __future__ import annotations

import json
import re
from typing import Any, Protocol

from skillrevise.method.authoring import AuthoringPrior, SkillConstraintChecker
from skillrevise.llm import LLMClient
from skillrevise.core.models import DiagnosisReport, FailureType, RevisionCandidate, Skill, TaskSpec
from skillrevise.method.principles import PrincipleBank
from skillrevise.method.skill_parser import parse_skill_markdown


REVISION_ABLATIONS = frozenset({"none", "no-execution-anchors", "no-preserve-ledger"})


class RevisionEngine(Protocol):
    def revise(self, task: TaskSpec, skill: Skill, diagnosis: DiagnosisReport) -> RevisionCandidate:
        """Return one revised skill candidate."""


class HeuristicRevisionEngine:
    def __init__(self, prior: AuthoringPrior | None = None) -> None:
        self.prior = prior or AuthoringPrior()
        self.checker = SkillConstraintChecker(self.prior)

    def revise(self, task: TaskSpec, skill: Skill, diagnosis: DiagnosisReport) -> RevisionCandidate:
        revised_skill = Skill(
            name=skill.name.replace("Direct Fix", "Validated Workflow"),
            purpose=(
                f"Provide a reusable {task.family} workflow that is explicit, validated, "
                "environment-grounded, recoverable, and constraint-checked."
            ),
            when_to_use=(
                f"Use for {task.family} tasks where requirements, files, tools, commands, or validation routes "
                "may vary across environments."
            ),
            procedure=self._build_procedure(task, diagnosis),
            constraints=self._build_constraints(diagnosis),
            version=self._bump_version(skill.version),
            metadata={
                "reviser": "heuristic_revision",
                "labels": [label.value for label in diagnosis.labels],
            },
        )
        revised_skill.metadata["prior_violations"] = [
            violation.code for violation in self.checker.check(revised_skill, task)
        ]
        rationale = "; ".join(diagnosis.rewrite_targets) if diagnosis.rewrite_targets else "No revision required."
        return RevisionCandidate(parent_version=skill.version, revised_skill=revised_skill, rationale=rationale)

    def _build_procedure(self, task: TaskSpec, diagnosis: DiagnosisReport) -> list[str]:
        procedure = [
            "First restate the required outcome and identify the smallest verifiable unit of work.",
            "Inspect the environment to discover relevant files, available tools, and the repository-native validation entrypoint.",
            "Validate inputs, assumptions, target files, and expected outputs before editing or running commands.",
            "Apply the change only after the environment assumptions are confirmed and scoped to the acceptance criteria.",
            "Run the smallest reliable check first, then widen validation only when the local result is inconclusive.",
            "If a planned file, command, tool, or check is unavailable, fall back to the closest environment-supported alternative and record why.",
            "Before finishing, compare the result against every explicit constraint and verifier signal.",
        ]
        labels = set(diagnosis.labels)
        if FailureType.OVER_GENERALITY in labels:
            procedure.insert(
                3,
                "Translate the plan into one concrete checkpoint so the next action can be confirmed or rejected quickly.",
            )
        if FailureType.CONTEXT_POLLUTION in labels:
            procedure = procedure[:6]
        if FailureType.WRONG_ABSTRACTION_LEVEL in labels:
            procedure[0] = "Start from the task-family workflow, then specialize only after the local environment is verified."
        return procedure

    def _build_constraints(self, diagnosis: DiagnosisReport) -> list[str]:
        constraints = [
            "Do not assume a fixed path, tool, or version before verification.",
            "Prefer repository-native commands over copied examples or stale templates.",
            "Only act on inputs, files, and commands after they are checked in the current environment.",
            "Do not continue with a plan after verifier output contradicts it.",
            "Stop and re-check when the environment contradicts the initial plan.",
        ]
        labels = set(diagnosis.labels)
        if FailureType.CONTEXT_POLLUTION in labels:
            constraints.append("Keep the skill concise: every line should change an execution decision.")
        if FailureType.FALSE_CERTAINTY in labels:
            constraints.append("Phrase directives as validated conditions rather than unconditional commands.")
        return constraints

    def _bump_version(self, version: str) -> str:
        if not version.startswith("v"):
            return f"{version}-revised"
        try:
            return f"v{int(version[1:]) + 1}"
        except ValueError:
            return f"{version}-revised"


class LLMRevisionEngine:
    def __init__(
        self,
        llm: LLMClient,
        *,
        prior: AuthoringPrior | None = None,
        fallback: RevisionEngine | None = None,
        principle_bank: PrincipleBank | None = None,
        principle_limit: int = 4,
        allow_fallback: bool = True,
        use_principle_memory: bool = True,
        revision_ablation: str = "none",
    ) -> None:
        if revision_ablation not in REVISION_ABLATIONS:
            raise ValueError(f"Unknown revision ablation: {revision_ablation}")
        self.llm = llm
        self.prior = prior or AuthoringPrior()
        self.checker = SkillConstraintChecker(self.prior)
        self.fallback = fallback or HeuristicRevisionEngine(self.prior)
        self.allow_fallback = allow_fallback
        self.principle_bank = principle_bank or PrincipleBank.default()
        self.principle_limit = principle_limit
        self.use_principle_memory = use_principle_memory
        self.revision_ablation = revision_ablation

    def revise(self, task: TaskSpec, skill: Skill, diagnosis: DiagnosisReport) -> RevisionCandidate:
        using_principle_memory = self.use_principle_memory and self.principle_limit > 0
        removed_mechanism = _removed_mechanism_for_revision_ablation(self.revision_ablation)
        principle_candidates = (
            self.principle_bank.retrieve_candidates(task, diagnosis, limit=self.principle_limit)
            if using_principle_memory
            else []
        )
        principles = [candidate.principle for candidate in principle_candidates]
        prompt = self._build_prompt(
            task,
            skill,
            diagnosis,
            principle_candidates=principle_candidates,
            using_principle_memory=using_principle_memory,
        )
        next_version = self._bump_version(skill.version)
        try:
            response = self.llm.complete(prompt, purpose="skill_revision")
            revision_trace, skill_markdown = _split_revision_response(response.text)
            revision_trace = _sanitize_revision_trace(
                revision_trace,
                revision_ablation=self.revision_ablation,
            )
            revision_protocol_version = "principle_revision_v2" if using_principle_memory else "diagnosis_revision_v1"
            revision_framework = "principle_bank_guided" if using_principle_memory else "diagnosis_guided_no_principle_memory"
            selected_ids = _selected_principle_ids(revision_trace)
            selected_principles = _principles_by_ids(principles, selected_ids) or principles
            metadata = {
                "reviser": "llm",
                "parent_version": skill.version,
                "llm_latency_seconds": response.latency_seconds,
                "llm_metadata": response.metadata,
                "labels": [label.value for label in diagnosis.labels],
                "revision_framework": revision_framework,
                "revision_protocol_version": revision_protocol_version,
                "revision_ablation": self.revision_ablation,
                "removed_mechanism": removed_mechanism,
                "principle_memory_enabled": using_principle_memory,
                "retrieved_principle_ids": [principle.principle_id for principle in principles],
                "retrieved_principles": [
                    {
                        "principle_id": candidate.principle.principle_id,
                        "rank": candidate.rank,
                        "score": candidate.score,
                        "matched_signals": candidate.matched_signals,
                    }
                    for candidate in principle_candidates
                ],
                "selected_principle_ids": selected_ids,
                "revision_trace": revision_trace,
                "failure_primary": _trace_failure_primary(revision_trace),
                "principle_ids": [principle.principle_id for principle in selected_principles],
            }
            if _include_execution_anchors(self.revision_ablation):
                metadata["execution_anchors"] = _trace_execution_anchors(revision_trace)
            revised = parse_skill_markdown(
                skill_markdown,
                default_name=skill.name,
                version=next_version,
                metadata=metadata,
            )
        except Exception as exc:
            if not self.allow_fallback:
                raise RuntimeError(f"LLM skill revision failed: {exc}") from exc
            candidate = self.fallback.revise(task, skill, diagnosis)
            candidate.revised_skill.metadata["reviser"] = "llm_fallback"
            candidate.revised_skill.metadata["llm_error"] = str(exc)
            candidate.revised_skill.metadata["revision_framework"] = (
                "principle_bank_guided_fallback"
                if using_principle_memory
                else "diagnosis_guided_no_principle_memory_fallback"
            )
            candidate.revised_skill.metadata["revision_ablation"] = self.revision_ablation
            candidate.revised_skill.metadata["removed_mechanism"] = removed_mechanism
            candidate.revised_skill.metadata["principle_memory_enabled"] = using_principle_memory
            candidate.revised_skill.metadata["principle_ids"] = [principle.principle_id for principle in principles]
            candidate.revised_skill.metadata["retrieved_principle_ids"] = [
                principle.principle_id for principle in principles
            ]
            candidate.principles = principles
            candidate.metadata["revision_ablation"] = self.revision_ablation
            candidate.metadata["removed_mechanism"] = removed_mechanism
            return candidate

        violations = self.checker.check(revised, task)
        revised.metadata["prior_violations"] = [violation.code for violation in violations]
        rationale = (
            "LLM revision guided by paired-execution diagnosis, "
            + (
                "retrieved repair principles, "
                if using_principle_memory
                else "with principle-memory retrieval disabled, "
            )
            + "anti-overfitting checks, verifier alignment, and utility-based acceptance."
        )
        candidate_metadata = {
            "retrieved_principle_ids": [principle.principle_id for principle in principles],
            "selected_principle_ids": selected_ids,
            "revision_trace": revision_trace,
            "failure_primary": _trace_failure_primary(revision_trace),
            "principle_memory_enabled": using_principle_memory,
            "revision_ablation": self.revision_ablation,
            "removed_mechanism": removed_mechanism,
        }
        if _include_execution_anchors(self.revision_ablation):
            candidate_metadata["execution_anchors"] = _trace_execution_anchors(revision_trace)
        return RevisionCandidate(
            parent_version=skill.version,
            revised_skill=revised,
            rationale=rationale,
            principles=selected_principles,
            metadata=candidate_metadata,
        )

    def _build_prompt(
        self,
        task: TaskSpec,
        skill: Skill,
        diagnosis: DiagnosisReport,
        *,
        principle_candidates,
        using_principle_memory: bool = True,
    ) -> str:
        evidence = "\n".join(
            f"- [{item.source}] {item.snippet}: {item.reason}" for item in diagnosis.evidence
        ) or "- None"
        targets = "\n".join(f"- {item}" for item in diagnosis.rewrite_targets) or "- None"
        include_execution_anchors = _include_execution_anchors(self.revision_ablation)
        include_preserve_ledger = _include_preserve_ledger(self.revision_ablation)
        revision_memory = _render_revision_memory(
            skill,
            include_execution_anchors=include_execution_anchors,
            include_preserve_ledger=include_preserve_ledger,
        )
        output_template = (
            _revision_output_template(
                include_execution_anchors=include_execution_anchors,
                include_preserve_ledger=include_preserve_ledger,
            )
            if using_principle_memory
            else _diagnosis_revision_output_template(
                include_execution_anchors=include_execution_anchors,
                include_preserve_ledger=include_preserve_ledger,
            )
        )
        memory_guard = _revision_memory_guard(
            include_execution_anchors=include_execution_anchors,
            include_preserve_ledger=include_preserve_ledger,
        )
        executable_guard = (
            (
                "Executable repair guard: every revision must include at least one execution anchor "
                "inside the revised skill: a concrete action, expected observable evidence, and placement."
            )
            if include_execution_anchors
            else None
        )
        if not using_principle_memory:
            sections = [
                "Revise this task-family skill using execution evidence and structured diagnosis.",
                (
                    "Principle-memory ablation: do not retrieve, quote, select, or rely on repair-principle "
                    "bank entries. Use only the task, current skill, execution evidence, and diagnosis fields."
                ),
                self.checker.render_prompt_prior(),
                _diagnosis_guided_revision_protocol(
                    include_execution_anchors=include_execution_anchors,
                    include_preserve_ledger=include_preserve_ledger,
                ),
                "Keep validated useful content, remove brittle content, and do not include the source task answer.",
                memory_guard,
            ]
            if executable_guard:
                sections.append(executable_guard)
            sections.extend(
                [
                    (
                        "The revised skill should teach a reusable non-regression workflow, not memorize this "
                        "task's answer."
                    ),
                    f"Previous revision trace / task-local memory:\n{revision_memory}",
                    f"Task family: {task.family}",
                    f"Task instruction:\n{task.instruction}",
                    f"Acceptance criteria:\n{task.acceptance_criteria}",
                    f"Current skill:\n{skill.as_markdown()}",
                    f"Diagnosis labels: {[label.value for label in diagnosis.labels]}",
                    f"Causal judgment:\n{diagnosis.causal_judgment}",
                    f"Evidence:\n{evidence}",
                    f"Rewrite targets:\n{targets}",
                    output_template,
                ]
            )
            return "\n\n".join(sections)

        rendered_principles = self.principle_bank.render_candidates_for_prompt(principle_candidates)
        sections = [
            "Revise this task-family skill using execution evidence and the repair-principle bank.",
            self.checker.render_prompt_prior(),
            "Top-k candidate repair principles retrieved from the principle bank:",
            rendered_principles,
            _principle_bank_revision_protocol(
                include_execution_anchors=include_execution_anchors,
                include_preserve_ledger=include_preserve_ledger,
            ),
            "Keep validated useful content, remove brittle content, and do not include the source task answer.",
            memory_guard,
        ]
        if executable_guard:
            sections.append(executable_guard)
        sections.extend(
            [
                (
                    "The revised skill should teach a reusable non-regression workflow, not memorize this "
                    "task's answer. Use selected principles as repair operators, not as extra prose pasted "
                    "into the skill."
                ),
                f"Previous revision trace / task-local memory:\n{revision_memory}",
                f"Task family: {task.family}",
                f"Task instruction:\n{task.instruction}",
                f"Acceptance criteria:\n{task.acceptance_criteria}",
                f"Current skill:\n{skill.as_markdown()}",
                f"Diagnosis labels: {[label.value for label in diagnosis.labels]}",
                f"Causal judgment:\n{diagnosis.causal_judgment}",
                f"Evidence:\n{evidence}",
                f"Rewrite targets:\n{targets}",
                output_template,
            ]
        )
        return "\n\n".join(sections)

    def _bump_version(self, version: str) -> str:
        if not version.startswith("v"):
            return f"{version}-revised"
        try:
            return f"v{int(version[1:]) + 1}"
        except ValueError:
            return f"{version}-revised"


class FreeFormLLMRevisionEngine:
    def __init__(
        self,
        llm: LLMClient,
        *,
        prior: AuthoringPrior | None = None,
        fallback: RevisionEngine | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self.llm = llm
        self.prior = prior or AuthoringPrior()
        self.checker = SkillConstraintChecker(self.prior)
        self.fallback = fallback or HeuristicRevisionEngine(self.prior)
        self.allow_fallback = allow_fallback

    def revise(self, task: TaskSpec, skill: Skill, diagnosis: DiagnosisReport) -> RevisionCandidate:
        prompt = self._build_prompt(task, skill, diagnosis)
        next_version = self._bump_version(skill.version)
        try:
            response = self.llm.complete(prompt, purpose="skill_revision_freeform")
            revised = parse_skill_markdown(
                response.text,
                default_name=skill.name,
                version=next_version,
                metadata={
                    "reviser": "llm_freeform",
                    "parent_version": skill.version,
                    "llm_latency_seconds": response.latency_seconds,
                    "llm_metadata": response.metadata,
                },
            )
        except Exception as exc:
            if not self.allow_fallback:
                raise RuntimeError(f"Free-form LLM skill revision failed: {exc}") from exc
            candidate = self.fallback.revise(task, skill, diagnosis)
            candidate.revised_skill.metadata["reviser"] = "llm_freeform_fallback"
            candidate.revised_skill.metadata["llm_error"] = str(exc)
            return candidate

        violations = self.checker.check(revised, task)
        revised.metadata["prior_violations"] = [violation.code for violation in violations]
        rationale = "Free-form LLM revision from task context, current skill, and observed execution feedback."
        return RevisionCandidate(parent_version=skill.version, revised_skill=revised, rationale=rationale)

    def _build_prompt(self, task: TaskSpec, skill: Skill, diagnosis: DiagnosisReport) -> str:
        feedback = "\n".join(
            f"- [{item.source}] {item.snippet}: {item.reason}" for item in diagnosis.evidence
        ) or "- No concrete feedback was extracted."
        output_template = _freeform_revision_output_template()
        return "\n\n".join(
            [
                "Improve this LLM-authored task skill using the observed execution feedback.",
                "Do not use any predefined failure taxonomy, repair-principle checklist, or structured defect labels.",
                "Keep useful parts of the current skill, remove misleading parts, and make the revised skill reusable.",
                "Do not regress other verifier checks that already passed while addressing the observed feedback.",
                f"Task family: {task.family}",
                f"Task instruction:\n{task.instruction}",
                f"Acceptance criteria:\n{task.acceptance_criteria}",
                f"Current skill:\n{skill.as_markdown()}",
                f"Observed execution feedback:\n{feedback}",
                output_template,
            ]
        )

    def _bump_version(self, version: str) -> str:
        if not version.startswith("v"):
            return f"{version}-revised"
        try:
            return f"v{int(version[1:]) + 1}"
        except ValueError:
            return f"{version}-revised"


def _principle_bank_revision_protocol(
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    first_step = (
        "Structured diagnosis first: build Verifier Contract, Failure Ledger, and Preserve Ledger before editing the skill."
        if include_preserve_ledger
        else "Structured diagnosis first: build Verifier Contract and Failure Ledger before editing the skill."
    )
    principle_selection = (
        "Principle selection: select at most 3 retrieved principles. For each selected principle, explain why it applies, which failed check/evidence it addresses, what concrete skill operation it induces, and what preserve constraint it protects. Ignore high-ranked principles not supported by observable evidence."
        if include_preserve_ledger
        else "Principle selection: select at most 3 retrieved principles. For each selected principle, explain why it applies, which failed check/evidence it addresses, and what concrete skill operation it induces. Ignore high-ranked principles not supported by observable evidence."
    )
    acceptance_signals = (
        "Acceptance signals: final selection is utility-based, but assertion-level progress can justify continued revision. Report expected utility improvement, expected failed assertions reduced, and preserve risk."
        if include_preserve_ledger
        else "Acceptance signals: final selection is utility-based, but assertion-level progress can justify continued revision. Report expected utility improvement and expected failed assertions reduced."
    )
    items = [
        first_step,
        "Verifier Contract must list only observable requirements: required output paths, schemas/formats, numeric thresholds, and pass/fail assertions. Do not invent hidden contracts; use unknown or [] when evidence is missing.",
        "Failure Ledger must state failed checks, actual behavior, likely cause, and a lightweight failure_type with primary plus optional secondary_tags. Primary must be one of: path, schema, method, environment, incomplete_execution, data_understanding, constraint_violation, verification_gap, efficiency_timeout, overfit_or_hardcode, unknown.",
    ]
    if include_preserve_ledger:
        items.append(
            "Preserve Ledger must record task-local passed checks and concrete successful choices to keep. Do not remove, rename, contradict, or replace preserved items unless they directly conflict with repairing a failed check; if there is a conflict, explain it in the trace."
        )
    items.extend(
        [
            principle_selection,
            "Repeated-failure escalation: if the previous revision trace shows the same primary failure type as the current Failure Ledger across consecutive failed attempts, escalate from local patching to method-level repair. Escalation means changing the repair level, not adding cautionary prose.",
        ]
    )
    if include_execution_anchors:
        items.append(
            "Execution anchor: every revision must introduce or preserve at least one concrete execution anchor in the revised skill. Each anchor needs action, expected evidence, and placement. When principles are selected, the anchor should operationalize them."
        )
    items.extend(
        [
            "Minimal repair scope: edit only the procedure, trigger, or constraint responsible for the failing contract unless evidence implicates shared setup.",
            "Anti-overfitting check: remove task-instance answers, brittle literals, hidden-verifier guesses, and instructions that would only work for this exact instance.",
            "Expected verifier alignment: make final checks match explicit paths, schemas, tests, formats, scoring contracts, entrypoints, or semantic assertions.",
            acceptance_signals,
        ]
    )
    return _numbered_protocol("Principle-bank revision protocol:", items)


def _diagnosis_guided_revision_protocol(
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    first_step = (
        "Structured diagnosis first: build Verifier Contract, Failure Ledger, and Preserve Ledger before editing the skill."
        if include_preserve_ledger
        else "Structured diagnosis first: build Verifier Contract and Failure Ledger before editing the skill."
    )
    acceptance_signals = (
        "Acceptance signals: final selection is utility-based, but assertion-level progress can justify continued revision. Report expected utility improvement, expected failed assertions reduced, and preserve risk."
        if include_preserve_ledger
        else "Acceptance signals: final selection is utility-based, but assertion-level progress can justify continued revision. Report expected utility improvement and expected failed assertions reduced."
    )
    items = [
        first_step,
        "Verifier Contract must list only observable requirements: required output paths, schemas/formats, numeric thresholds, and pass/fail assertions. Do not invent hidden contracts; use unknown or [] when evidence is missing.",
        "Failure Ledger must state failed checks, actual behavior, likely cause, and a lightweight failure_type with primary plus optional secondary_tags. Primary must be one of: path, schema, method, environment, incomplete_execution, data_understanding, constraint_violation, verification_gap, efficiency_timeout, overfit_or_hardcode, unknown.",
    ]
    if include_preserve_ledger:
        items.append(
            "Preserve Ledger must record task-local passed checks and concrete successful choices to keep. Do not remove, rename, contradict, or replace preserved items unless they directly conflict with repairing a failed check; if there is a conflict, explain it in the trace."
        )
    items.append(
        "Repeated-failure escalation: if the previous revision trace shows the same primary failure type as the current Failure Ledger across consecutive failed attempts, escalate from local patching to method-level repair. Escalation means changing the repair level, not adding cautionary prose."
    )
    if include_execution_anchors:
        items.append(
            "Execution anchor: every revision must introduce or preserve at least one concrete execution anchor in the revised skill. Each anchor needs action, expected evidence, and placement."
        )
    items.extend(
        [
            "Minimal repair scope: edit only the procedure, trigger, or constraint responsible for the failing contract unless evidence implicates shared setup.",
            "Anti-overfitting check: remove task-instance answers, brittle literals, hidden-verifier guesses, and instructions that would only work for this exact instance.",
            "Expected verifier alignment: make final checks match explicit paths, schemas, tests, formats, scoring contracts, entrypoints, or semantic assertions.",
            acceptance_signals,
        ]
    )
    return _numbered_protocol("Diagnosis-guided revision protocol:", items)


def _numbered_protocol(title: str, items: list[str]) -> str:
    return "\n".join([title, *(f"{index}. {item}" for index, item in enumerate(items, start=1))])


def _revision_output_template(
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    selected_principle = (
        '{"principle_id": "", "why_selected": "", "failure_addressed": "", "induced_skill_operation": "", "preserve_constraint": ""}'
        if include_preserve_ledger
        else '{"principle_id": "", "why_selected": "", "failure_addressed": "", "induced_skill_operation": ""}'
    )
    trace_lines = _base_revision_trace_lines(
        include_execution_anchors=include_execution_anchors,
        include_preserve_ledger=include_preserve_ledger,
        selected_principles_lines=[
            '  "selected_principles": [',
            f"    {selected_principle}",
            "  ],",
            '  "ignored_principles": [',
            '    {"principle_id": "", "reason": ""}',
            "  ],",
        ],
    )
    return "\n".join(_structured_revision_template_lines(trace_lines))


def _diagnosis_revision_output_template(
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    trace_lines = _base_revision_trace_lines(
        include_execution_anchors=include_execution_anchors,
        include_preserve_ledger=include_preserve_ledger,
        selected_principles_lines=[],
    )
    return "\n".join(_structured_revision_template_lines(trace_lines))


def _base_revision_trace_lines(
    *,
    include_execution_anchors: bool,
    include_preserve_ledger: bool,
    selected_principles_lines: list[str],
) -> list[str]:
    lines = [
        "{",
        '  "verifier_contract": {',
        '    "required_output_paths": [],',
        '    "required_schemas": [],',
        '    "numeric_thresholds": [],',
        '    "pass_fail_assertions": []',
        "  },",
        '  "failure_ledger": {',
        '    "failed_checks": [],',
        '    "actual_behavior": "",',
        '    "likely_cause": "",',
        '    "failure_type": {',
        '      "primary": "unknown",',
        '      "secondary_tags": []',
        "    }",
        "  },",
    ]
    if include_preserve_ledger:
        lines.extend(
            [
                '  "preserve_ledger": {',
                '    "passed_checks": [],',
                '    "successful_choices_to_keep": []',
                "  },",
            ]
        )
    lines.extend(selected_principles_lines)
    lines.extend(
        [
            '  "repeated_failure_escalation": {',
            '    "triggered": false,',
            '    "reason": "",',
            '    "escalation_action": ""',
            "  },",
        ]
    )
    if include_execution_anchors:
        lines.extend(
            [
                '  "execution_anchors": [',
                '    {"action": "", "evidence": "", "placement": ""}',
                "  ],",
            ]
        )
    lines.extend(
        [
            '  "acceptance_signals": {',
            '    "expected_utility_improvement": "",',
            '    "expected_failed_assertions_reduced": []' + ("," if include_preserve_ledger else ""),
        ]
    )
    if include_preserve_ledger:
        lines.append('    "preserve_risk": "low"')
    lines.extend(["  }", "}"])
    return lines


def _structured_revision_template_lines(trace_lines: list[str]) -> list[str]:
    return [
        "Return exactly two blocks. First a fenced JSON block named REVISION_TRACE_JSON, then the revised skill Markdown.",
        "",
        "REVISION_TRACE_JSON:",
        "```json",
        *trace_lines,
        "```",
        "",
        "REVISED_SKILL_MARKDOWN:",
        "# <Skill Name>",
        "",
        "## Purpose",
        "<1 concise paragraph>",
        "",
        "## When to Use",
        "<1 concise paragraph describing the reusable task-family trigger>",
        "",
        "## Procedure",
        "- <ordered, executable step 1>",
        "- <ordered, executable step 2>",
        "- <ordered, executable step 3>",
        "- <ordered, executable step 4>",
        "",
        "## Constraints / Pitfalls",
        "- <strict constraint or pitfall 1>",
        "- <strict constraint or pitfall 2>",
    ]


def _freeform_revision_output_template() -> str:
    return "\n".join(
        [
            "Return only the revised skill Markdown in this structure:",
            "# <Skill Name>",
            "",
            "## Purpose",
            "<1 concise paragraph>",
            "",
            "## When to Use",
            "<1 concise paragraph describing the reusable task-family trigger>",
            "",
            "## Procedure",
            "- <ordered, executable step 1>",
            "- <ordered, executable step 2>",
            "- <ordered, executable step 3>",
            "- <ordered, executable step 4>",
            "",
            "## Constraints / Pitfalls",
            "- <strict constraint or pitfall 1>",
            "- <strict constraint or pitfall 2>",
        ]
    )


def _has_constraints_section(skill_markdown: str) -> bool:
    for raw_line in skill_markdown.splitlines():
        title = re.sub(r"[*_`#]", "", raw_line.strip())
        title = re.sub(r"\s+", " ", title).strip().lower()
        if title in {"constraints", "constraints / pitfalls", "constraints/pitfalls", "pitfalls"}:
            return True
    return False


def _render_revision_memory(
    skill: Skill,
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    trace = skill.metadata.get("revision_trace") if isinstance(skill.metadata, dict) else None
    if not isinstance(trace, dict) or not trace:
        return "- No previous revision trace is available. Treat this as the first revision attempt."

    acceptance_signals = trace.get("acceptance_signals", {})
    if isinstance(acceptance_signals, dict):
        acceptance_signals = dict(acceptance_signals)
        if not include_preserve_ledger:
            acceptance_signals.pop("preserve_risk", None)
    memory = {
        "previous_skill_version": skill.version,
        "previous_failure_primary": _trace_failure_primary(trace),
        "previous_selected_principle_ids": skill.metadata.get("selected_principle_ids", []),
        "previous_repeated_failure_escalation": trace.get("repeated_failure_escalation", {}),
        "previous_acceptance_signals": acceptance_signals,
    }
    if include_preserve_ledger:
        memory["previous_preserve_ledger"] = trace.get("preserve_ledger", {})
    if include_execution_anchors:
        memory["previous_execution_anchors"] = _trace_execution_anchors(trace)
    return json.dumps(memory, indent=2, ensure_ascii=True)


def _revision_memory_guard(
    *,
    include_execution_anchors: bool = True,
    include_preserve_ledger: bool = True,
) -> str:
    local_signals = []
    if include_preserve_ledger:
        local_signals.append("Preserve Ledger items")
        local_signals.append("successful local choices")
    else:
        local_signals.append("successful local choices")
    if include_execution_anchors:
        local_signals.append("execution anchors")
    local_signals.append("repeated failure signals")
    signals = ", ".join(local_signals[:-1]) + f", and {local_signals[-1]}"
    return (
        f"Task-local revision memory guard: {signals} are local to this task episode. "
        "Use them to protect and steer the next revision, but do not treat them as bank-level principles."
    )


def _include_execution_anchors(revision_ablation: str) -> bool:
    return revision_ablation != "no-execution-anchors"


def _include_preserve_ledger(revision_ablation: str) -> bool:
    return revision_ablation != "no-preserve-ledger"


def _removed_mechanism_for_revision_ablation(revision_ablation: str) -> str:
    return {
        "none": "none",
        "no-execution-anchors": "execution anchors",
        "no-preserve-ledger": "preserve ledger",
    }[revision_ablation]


def _sanitize_revision_trace(trace: dict[str, Any], *, revision_ablation: str) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {}
    sanitized = json.loads(json.dumps(trace))
    if not _include_execution_anchors(revision_ablation):
        sanitized.pop("execution_anchors", None)
    if not _include_preserve_ledger(revision_ablation):
        sanitized.pop("preserve_ledger", None)
        selected = sanitized.get("selected_principles")
        if isinstance(selected, list):
            for item in selected:
                if isinstance(item, dict):
                    item.pop("preserve_constraint", None)
        acceptance = sanitized.get("acceptance_signals")
        if isinstance(acceptance, dict):
            acceptance.pop("preserve_risk", None)
    return sanitized


def _trace_failure_primary(trace: dict[str, Any]) -> str:
    failure_ledger = trace.get("failure_ledger")
    if isinstance(failure_ledger, dict):
        failure_type = failure_ledger.get("failure_type")
        if isinstance(failure_type, dict):
            primary = str(failure_type.get("primary", "")).strip()
            if primary:
                return primary
        primary = str(failure_ledger.get("primary", "")).strip()
        if primary:
            return primary
    if isinstance(failure_ledger, list):
        for item in failure_ledger:
            if not isinstance(item, dict):
                continue
            primary = str(item.get("primary") or item.get("likely_failure_mode") or "").strip()
            if primary:
                return primary
    return "unknown"


def _trace_execution_anchors(trace: dict[str, Any]) -> list[dict[str, Any]]:
    anchors = trace.get("execution_anchors")
    if not isinstance(anchors, list):
        return []
    return [dict(anchor) for anchor in anchors if isinstance(anchor, dict)]


def _split_revision_response(text: str) -> tuple[dict, str]:
    trace: dict = {}
    trace_match = re.search(
        r"REVISION_TRACE_JSON:\s*```(?:json)?\s*(\{.*?\})\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if trace_match:
        try:
            parsed = json.loads(trace_match.group(1))
            if isinstance(parsed, dict):
                trace = parsed
        except json.JSONDecodeError:
            trace = {}
    markdown_match = re.search(
        r"REVISED_SKILL_MARKDOWN:\s*(.*)$",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if markdown_match:
        return trace, markdown_match.group(1).strip()
    if trace_match:
        text = text[: trace_match.start()] + text[trace_match.end() :]
    return trace, text.strip()


def _selected_principle_ids(trace: dict) -> list[str]:
    selected = trace.get("selected_principles")
    if not isinstance(selected, list):
        return []
    ids: list[str] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        principle_id = str(item.get("principle_id", "")).strip()
        if principle_id and principle_id not in ids:
            ids.append(principle_id)
    return ids


def _principles_by_ids(principles, principle_ids: list[str]):
    if not principle_ids:
        return []
    by_id = {principle.principle_id: principle for principle in principles}
    return [by_id[principle_id] for principle_id in principle_ids if principle_id in by_id]
