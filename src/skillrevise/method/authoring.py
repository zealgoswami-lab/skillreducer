from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from skillrevise.llm import LLMClient
from skillrevise.core.models import DiagnosisReport, FailureType, Skill, TaskSpec
from skillrevise.method.principles import PrincipleBank
from skillrevise.method.skill_parser import parse_skill_markdown


WORKFLOW_MARKERS = ("first", "then", "before", "after", "step", "workflow")
VALIDATION_MARKERS = ("verify", "validate", "check", "inspect", "confirm", "test")
ENVIRONMENT_MARKERS = (
    "discover",
    "repository-native",
    "repo-native",
    "available",
    "entrypoint",
    "current environment",
    "local environment",
    "environment-supported",
)
FALLBACK_MARKERS = ("fallback", "if unavailable", "if missing", "otherwise", "alternative", "recover")
STRICT_CONSTRAINT_MARKERS = ("do not", "only after", "before", "avoid", "stop", "must not")
GENERIC_MARKERS = (
    "be careful",
    "think step by step",
    "follow best practices",
    "analyze carefully",
    "consider edge cases",
)
ABSOLUTE_MARKERS = ("always", "must", "directly", "without checking", "without additional", "never")
LITERAL_PATTERN = re.compile(r"`[^`]+/[^`]+`|\b[a-zA-Z0-9_.-]+\.[a-z]{1,5}\b")


@dataclass
class AuthoringPrior:
    """Platform-agnostic constraints distilled from skill-creator-style practice."""

    max_words: int = 220
    min_procedure_steps: int = 4
    allow_literal_examples: bool = False


@dataclass
class SkillConstraintViolation:
    code: str
    severity: str
    location: str
    message: str
    suggestion: str


class SkillConstraintChecker:
    def __init__(self, prior: AuthoringPrior | None = None) -> None:
        self.prior = prior or AuthoringPrior()

    def check(self, skill: Skill, task: TaskSpec | None = None) -> list[SkillConstraintViolation]:
        text = skill.as_markdown().lower()
        procedure_text = " ".join(skill.procedure).lower()
        constraints_text = " ".join(skill.constraints).lower()
        violations: list[SkillConstraintViolation] = []

        if not skill.when_to_use.strip() or "similar to the current task" in skill.when_to_use.lower():
            violations.append(
                SkillConstraintViolation(
                    code="unclear_trigger",
                    severity="medium",
                    location="when_to_use",
                    message="The skill trigger is tied to a task instance or is underspecified.",
                    suggestion="Describe the reusable task family and the conditions under which the skill applies.",
                )
            )

        if len(skill.procedure) < self.prior.min_procedure_steps or not self._has_any(procedure_text, WORKFLOW_MARKERS):
            violations.append(
                SkillConstraintViolation(
                    code="missing_workflow_explicitness",
                    severity="high",
                    location="procedure",
                    message="The skill does not expose a clear executable workflow.",
                    suggestion="State the order of actions, checkpoints, and decision points explicitly.",
                )
            )

        if not self._has_positive_marker(text, VALIDATION_MARKERS):
            violations.append(
                SkillConstraintViolation(
                    code="missing_input_validation",
                    severity="high",
                    location="procedure",
                    message="The skill does not require validating inputs or assumptions before acting.",
                    suggestion="Add an early verification step for requirements, files, tools, and expected outputs.",
                )
            )

        if not self._has_positive_marker(text, ENVIRONMENT_MARKERS):
            violations.append(
                SkillConstraintViolation(
                    code="missing_environment_grounding",
                    severity="high",
                    location="procedure",
                    message="The skill is not grounded in the actual execution environment.",
                    suggestion="Require discovering repo-native files, commands, tools, and validation entrypoints.",
                )
            )

        if not self._has_positive_marker(text, FALLBACK_MARKERS):
            violations.append(
                SkillConstraintViolation(
                    code="missing_fallback_handling",
                    severity="medium",
                    location="procedure",
                    message="The skill has no recovery path when its first plan fails.",
                    suggestion="Add fallback rules for missing files, unavailable commands, failed checks, and ambiguous requirements.",
                )
            )

        if not self._has_any(constraints_text, STRICT_CONSTRAINT_MARKERS):
            violations.append(
                SkillConstraintViolation(
                    code="missing_strict_constraints",
                    severity="medium",
                    location="constraints",
                    message="The skill lacks hard constraints that prevent brittle behavior.",
                    suggestion="Add explicit do-not rules and preconditions for fragile operations.",
                )
            )

        literal_count = len(LITERAL_PATTERN.findall(text))
        if literal_count >= 2 and not self.prior.allow_literal_examples:
            violations.append(
                SkillConstraintViolation(
                    code="over_specific_literals",
                    severity="high",
                    location="skill",
                    message="The skill contains multiple path, file, command, or version literals.",
                    suggestion="Replace literals with discovery rules unless they are verified task-family invariants.",
                )
            )

        word_count = len(skill.as_markdown().split())
        if word_count > self.prior.max_words:
            violations.append(
                SkillConstraintViolation(
                    code="context_pollution_risk",
                    severity="medium",
                    location="skill",
                    message=f"The skill has {word_count} words, above the {self.prior.max_words}-word prior.",
                    suggestion="Remove background, repeated explanations, and details that do not change execution.",
                )
            )

        generic_hits = sum(marker in text for marker in GENERIC_MARKERS)
        action_hits = sum(marker in text for marker in VALIDATION_MARKERS + ("run", "edit", "open", "create"))
        if generic_hits >= 2 and action_hits <= 3:
            violations.append(
                SkillConstraintViolation(
                    code="over_general_guidance",
                    severity="medium",
                    location="procedure",
                    message="The skill relies on broad advice rather than operational steps.",
                    suggestion="Replace generic advice with action-driving checkpoints.",
                )
            )

        if self._has_any(text, ABSOLUTE_MARKERS) and not (
            self._has_positive_marker(text, VALIDATION_MARKERS)
            and self._has_positive_marker(text, FALLBACK_MARKERS)
        ):
            violations.append(
                SkillConstraintViolation(
                    code="false_certainty",
                    severity="high",
                    location="skill",
                    message="The skill uses unconditional language without validation or recovery.",
                    suggestion="Convert hard directives into if/then rules with verification and fallback.",
                )
            )

        return violations

    def render_prompt_prior(self) -> str:
        return "\n".join(
            [
                "Use these platform-agnostic skill authoring constraints:",
                "1. Write a reusable task-family procedure, not a task-instance answer.",
                "2. Keep the skill concise; include only details that change execution behavior.",
                "3. Make the workflow explicit: order, checkpoints, and decision points must be clear.",
                "4. Validate inputs, files, tools, and assumptions before taking irreversible actions.",
                "5. Ground the procedure in the actual environment using discovery before fixed commands.",
                "6. Include fallback handling for missing tools, failed checks, and ambiguous requirements.",
                "7. Add strict constraints that prevent brittle or unsafe behavior.",
                "8. Avoid hard-coded paths, versions, and commands unless they are verified invariants.",
            ]
        )

    def _has_any(self, text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

    def _has_positive_marker(self, text: str, markers: tuple[str, ...]) -> bool:
        segments = re.split(r"[\n.;]", text)
        negative_prefixes = ("avoid ", "without ", "no ", "do not ", "never ")
        for segment in segments:
            clean = segment.strip()
            for marker in markers:
                if marker not in clean:
                    continue
                if any(f"{prefix}{marker}" in clean for prefix in negative_prefixes):
                    continue
                return True
        return False


def summarize_violations(violations: list[SkillConstraintViolation]) -> list[str]:
    return [f"{item.code}: {item.suggestion}" for item in violations]


class SkillAuthor(Protocol):
    def author(self, task: TaskSpec) -> Skill:
        """Produce an initial direct skill draft."""


class TemplateSkillAuthor:
    """Initial direct-skill baseline.

    The template intentionally behaves like a common failure mode:
    it converts one task instance into a brittle procedure with concrete literals.
    """

    def author(self, task: TaskSpec) -> Skill:
        default_path = task.metadata.get("default_path", "src/main.py")
        default_command = task.metadata.get("default_command", "pytest -q")
        name = f"{task.family.title().replace('-', ' ')} Direct Fix"
        return Skill(
            name=name,
            purpose=f"Finish the current {task.family} task as quickly as possible.",
            when_to_use=f"Use for {task.family} requests that look similar to the current task instance.",
            procedure=[
                f"Directly open `{default_path}` and implement the requested change.",
                f"Run `{default_command}` immediately after the edit.",
                "If the command passes, return the result without additional environment checks.",
            ],
            constraints=[
                "Prefer a fast direct fix over broader repository exploration.",
                "Avoid fallback logic unless the first command clearly fails.",
            ],
            version="v0",
            metadata={"author": "template_direct"},
        )


class PriorGuidedSkillAuthor:
    """Rule-based author that follows the platform-agnostic authoring prior.

    This is not meant to replace an LLM author. It gives the harness a deterministic
    implementation of the design constraints while skill prompts are still being refined.
    """

    def __init__(self, prior: AuthoringPrior | None = None) -> None:
        self.prior = prior or AuthoringPrior()
        self.checker = SkillConstraintChecker(self.prior)

    def author(self, task: TaskSpec) -> Skill:
        skill = Skill(
            name=f"{task.family.title().replace('-', ' ')} Workflow",
            purpose=(
                f"Guide reusable {task.family} execution with explicit validation, "
                "environment grounding, fallback handling, and strict constraints."
            ),
            when_to_use=(
                f"Use for {task.family} tasks that require acting in a local or tool-backed environment "
                "where file paths, commands, tools, or acceptance checks may vary."
            ),
            procedure=[
                "First restate the required outcome and identify the smallest verifiable unit of work.",
                "Inspect the environment to discover relevant files, available tools, and the repository-native validation entrypoint.",
                "Validate inputs and assumptions before editing, executing, or committing to a fixed path or command.",
                "Apply the change using the discovered workflow, keeping the action scoped to the acceptance criteria.",
                "Run the smallest reliable check first, then widen validation only when the local result is inconclusive.",
                "If a file, command, tool, or check is unavailable, use the closest environment-supported alternative and record why.",
            ],
            constraints=[
                "Do not hard-code paths, commands, versions, or tool names before verifying they exist in the environment.",
                "Only proceed after the requirement, target files, and validation route are checked.",
                "Avoid broad rewrites when a narrower change satisfies the acceptance criteria.",
                "Stop and re-check the plan when verifier output or tool feedback contradicts the current assumption.",
            ],
            version="v0",
            metadata={"author": "prior_guided", "prior_violations": []},
        )
        violations = self.checker.check(skill, task)
        skill.metadata["prior_violations"] = [violation.code for violation in violations]
        return skill


class FileSkillAuthor:
    """Loads a prewritten Markdown skill as the initial v0 skill.

    This is useful for matched revision ablations where multiple revision engines
    should start from the same initial skill instead of paying for another
    stochastic authoring call.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        version: str = "v0",
        checker: SkillConstraintChecker | None = None,
    ) -> None:
        self.path = Path(path)
        self.version = version
        self.checker = checker or SkillConstraintChecker()

    def author(self, task: TaskSpec) -> Skill:
        skill = parse_skill_markdown(
            self.path.read_text(errors="replace"),
            default_name=f"{task.family.title().replace('-', ' ')} Skill",
            version=self.version,
            metadata={"author": "file", "source_path": str(self.path)},
        )
        violations = self.checker.check(skill, task)
        skill.metadata["prior_violations"] = [violation.code for violation in violations]
        return skill


class SkillAuthoringPromptBuilder:
    """Builds LLM prompts without binding the method to a specific agent platform."""

    strategy_name = "principle_bank_seed_guided"

    def __init__(
        self,
        prior: AuthoringPrior | None = None,
        *,
        principle_bank: PrincipleBank | None = None,
        principle_limit: int = 4,
        principle_interface: str = "legacy",
    ) -> None:
        if principle_interface not in {"legacy", "action-map"}:
            raise ValueError("principle_interface must be 'legacy' or 'action-map'.")
        self.checker = SkillConstraintChecker(prior)
        self.principle_bank = principle_bank
        self.principle_limit = principle_limit
        self.principle_interface = principle_interface
        self.strategy_name = (
            "principle_bank_seed_guided"
            if principle_interface == "legacy"
            else "principle_bank_seed_guided_action_map"
        )

    def build(self, task: TaskSpec) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- Not specified"
        sections = [
            "You are writing a task-family skill for an LLM agent.",
            self.checker.render_prompt_prior(),
        ]
        bank_guidance = self._render_principle_bank_guidance(task)
        if bank_guidance:
            sections.append(bank_guidance)
        sections.extend(
            [
                f"Task family: {task.family}",
                f"Source task:\n{task.instruction}",
                f"Acceptance criteria:\n{criteria}",
                self._render_output_template(),
            ]
        )
        return "\n\n".join(sections)

    def _render_output_template(self) -> str:
        if self.principle_interface == "legacy":
            return "\n".join(
                [
                    "Return only Markdown in exactly this structure:",
                    "# <Skill Name>",
                    "",
                    "## Purpose",
                    "<1 concise paragraph>",
                    "",
                    "## When to Use",
                    "<1 concise paragraph describing the reusable task family trigger>",
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
        return "\n".join(
            [
                "Return only Markdown in exactly this structure:",
                "# <Skill Name>",
                "",
                "## Purpose",
                "<1 concise paragraph naming the reusable task-family capability and the concrete outcome it protects>",
                "",
                "## When to Use",
                "<1 concise paragraph with positive triggers and at least one boundary where the skill should not be used>",
                "",
                "## Procedure",
                "- Preflight: <inspect task-visible inputs, file/container structure, available tools, and verifier/output contract before choosing an implementation route>",
                "- Strategy: <choose an implementation route from the inspected evidence; include the fallback route if the preferred parser/tool/library is unavailable or incomplete>",
                "- Execute: <perform the smallest scoped transformation/analysis needed for the task, preserving source data and avoiding hidden-answer or single-instance constants>",
                "- Validate: <run task-visible checks that mirror the acceptance criteria, including schema, counts, tolerances, artifact existence, and semantic sanity checks as applicable>",
                "- Fallback: <when validation fails or evidence is inconclusive, re-inspect the failing artifact/log and switch to a lower-level or independently verified method>",
                "",
                "## Constraints / Pitfalls",
                "- <principle-derived pitfall that would cause verifier-visible failure if ignored>",
                "- <principle-derived pitfall about overfitting, unsupported assumptions, brittle paths/tools, or missing validation>",
            ]
        )

    def _render_principle_bank_guidance(self, task: TaskSpec) -> str:
        if self.principle_bank is None or self.principle_limit <= 0:
            return ""
        diagnosis = DiagnosisReport(
            labels=[
                FailureType.WRONG_ABSTRACTION_LEVEL,
                FailureType.OVER_SPECIFICITY,
                FailureType.FALSE_CERTAINTY,
            ],
            evidence=[],
            causal_judgment=(
                "Initial skill authoring should prevent common reusable-skill defects before execution."
            ),
            rewrite_targets=[
                "Design a transferable, action-driving skill that avoids task-instance solutions.",
                "Ground paths, commands, artifacts, and checks in the current environment.",
                "Include validation and fallback behavior before finalizing.",
            ],
            summary="Initial design-time retrieval from the reusable principle bank.",
        )
        candidates = self.principle_bank.retrieve_candidates(
            task,
            diagnosis,
            limit=self.principle_limit,
        )
        blocks = []
        for candidate in candidates:
            principle = candidate.principle
            blocks.append(
                "\n".join(
                    [
                        f"- [{principle.principle_id}] {principle.title}",
                        f"  Trigger: {principle.trigger or principle.trigger_evidence}",
                        f"  Do: {principle.action_template or principle.repair_rule}",
                        f"  Check: {principle.verification_template or 'Verify the observable task contract before finalizing.'}",
                        f"  Avoid: {principle.transfer_constraint}",
                    ]
                )
        )
        rendered = "\n".join(blocks) if blocks else "- No principle matched strongly enough; rely on the authoring prior."
        if self.principle_interface == "legacy":
            return "\n".join(
                [
                    "Most relevant reusable operating principles for the initial skill:",
                    rendered,
                    (
                        "Use at most the relevant parts as operating guidance. The final skill must be a concrete "
                        "task-family workflow, not a list of meta-principles. Do not copy task-specific answers, "
                        "identifiers, constants, paths, or verifier-local values."
                    ),
                ]
            )
        return "\n".join(
            [
                "Most relevant reusable operating principles for the initial skill:",
                rendered,
                "Direct-design operationalization contract:",
                (
                    "Before writing the final skill, internally map each relevant principle into an executable "
                    "task-specific design move: task feature -> preflight action -> implementation choice -> "
                    "validation hook -> fallback/boundary. Discard principles whose trigger does not match the "
                    "source task."
                ),
                (
                    "The final skill must not merely restate or summarize the principles. It must embed the mapped "
                    "moves inside Procedure and Constraints / Pitfalls as concrete actions an agent can perform "
                    "before seeing any failure trace."
                ),
                (
                    "Do not copy task-specific answers, identifiers, constants, hidden verifier values, or one-off "
                    "file paths unless the source task explicitly requires that visible path. Do not mention "
                    "principle IDs in the final skill."
                ),
            ]
        )


class NaiveSkillAuthoringPromptBuilder:
    """Builds an LLM skill-authoring prompt without the proposed seed principles.

    The prompt still asks for a parseable skill structure, but it intentionally avoids
    the principle-bank seed layer so it can serve as the "LLM unaided skill authoring" baseline.
    """

    strategy_name = "naive"

    def build(self, task: TaskSpec) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- Not specified"
        output_template = "\n".join(
            [
                "Return only Markdown in exactly this structure:",
                "# <Skill Name>",
                "",
                "## Purpose",
                "<1 concise paragraph>",
                "",
                "## When to Use",
                "<1 concise paragraph>",
                "",
                "## Procedure",
                "- <step 1>",
                "- <step 2>",
                "- <step 3>",
                "",
                "## Constraints / Pitfalls",
                "- <constraint or pitfall 1>",
                "- <constraint or pitfall 2>",
            ]
        )
        return "\n\n".join(
            [
                "You are writing a skill for an LLM agent.",
                f"Task family: {task.family}",
                f"Source task:\n{task.instruction}",
                f"Acceptance criteria:\n{criteria}",
                output_template,
            ]
        )


class SkillCreatorPromptBuilder:
    """Builds an authoring prompt based on the official skill-creator guidance.

    This is an ablation baseline: it uses general skill-creator design advice
    but does not include our repair-principle bank or execution-conditioned
    revision protocol.
    """

    strategy_name = "skill_creator"

    def build(self, task: TaskSpec) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- Not specified"
        output_template = "\n".join(
            [
                "Return only Markdown in exactly this structure:",
                "# <Skill Name>",
                "",
                "## Purpose",
                "<1 concise paragraph>",
                "",
                "## When to Use",
                "<1 concise paragraph describing when this reusable skill should trigger>",
                "",
                "## Procedure",
                "- <ordered, action-driving step 1>",
                "- <ordered, action-driving step 2>",
                "- <ordered, action-driving step 3>",
                "- <ordered, action-driving step 4>",
                "",
                "## Constraints / Pitfalls",
                "- <constraint or pitfall 1>",
                "- <constraint or pitfall 2>",
            ]
        )
        return "\n\n".join(
            [
                "You are creating a reusable SKILL.md-style guide for an LLM coding/tool agent.",
                "Use the official skill-creator design principles, but output only the requested skill body.",
                "Skill-creator principles to follow:",
                "1. Be concise: include only procedural knowledge that changes execution behavior.",
                "2. Set the right degree of freedom: use text guidance for flexible workflows, pseudocode/checks for fragile patterns, and concrete scripts only when deterministic reliability is needed.",
                "3. Prefer reusable task-family guidance over a one-off answer for this task instance.",
                "4. Make the trigger clear: the When to Use section should describe when the skill applies and when it should not.",
                "5. Use progressive disclosure in spirit: keep the main skill lean and mention references/scripts only if they are truly needed.",
                "6. Protect validation integrity: do not leak the hidden answer or overfit to one instance; include only checks an agent can honestly run.",
                f"Task family: {task.family}",
                f"Source task:\n{task.instruction}",
                f"Acceptance criteria:\n{criteria}",
                output_template,
            ]
        )


class LLMSkillAuthor:
    def __init__(
        self,
        llm: LLMClient,
        *,
        prompt_builder: SkillAuthoringPromptBuilder | NaiveSkillAuthoringPromptBuilder | SkillCreatorPromptBuilder | None = None,
        fallback_author: SkillAuthor | None = None,
        checker: SkillConstraintChecker | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder or SkillAuthoringPromptBuilder()
        self.fallback_author = fallback_author or PriorGuidedSkillAuthor()
        self.checker = checker or SkillConstraintChecker()
        self.allow_fallback = allow_fallback

    def author(self, task: TaskSpec) -> Skill:
        prompt = self.prompt_builder.build(task)
        try:
            response = self.llm.complete(prompt, purpose="skill_authoring")
            skill = parse_skill_markdown(
                response.text,
                default_name=f"{task.family.title().replace('-', ' ')} Skill",
                version="v0",
                metadata={
                    "author": "llm",
                    "prompt_strategy": getattr(self.prompt_builder, "strategy_name", "unknown"),
                    "llm_latency_seconds": response.latency_seconds,
                    "llm_metadata": response.metadata,
                },
            )
        except Exception as exc:
            if not self.allow_fallback:
                raise RuntimeError(f"LLM skill authoring failed: {exc}") from exc
            skill = self.fallback_author.author(task)
            skill.metadata["author"] = "llm_fallback"
            skill.metadata["prompt_strategy"] = getattr(self.prompt_builder, "strategy_name", "unknown")
            skill.metadata["llm_error"] = str(exc)
            return skill

        violations = self.checker.check(skill, task)
        skill.metadata["prior_violations"] = [violation.code for violation in violations]
        return skill
