from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    OVER_SPECIFICITY = "over_specificity"
    OVER_GENERALITY = "over_generality"
    WRONG_ABSTRACTION_LEVEL = "wrong_abstraction_level"
    CONTEXT_POLLUTION = "context_pollution"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    FALSE_CERTAINTY = "false_certainty"


@dataclass
class TaskSpec:
    task_id: str
    family: str
    instruction: str
    acceptance_criteria: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    name: str
    purpose: str
    when_to_use: str
    procedure: list[str]
    constraints: list[str]
    version: str = "v0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_markdown(self) -> str:
        lines = [
            f"# {self.name}",
            "",
            "## Purpose",
            self.purpose,
            "",
            "## When to Use",
            self.when_to_use,
            "",
            "## Procedure",
        ]
        lines.extend(f"- {step}" for step in self.procedure)
        lines.extend(["", "## Constraints / Pitfalls"])
        lines.extend(f"- {item}" for item in self.constraints)
        return "\n".join(lines).strip()

    def lines(self) -> list[str]:
        return self.as_markdown().splitlines()


@dataclass
class TrajectoryEvent:
    step_index: int
    kind: str
    summary: str
    evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    run_id: str
    task_id: str
    skill_version: str | None
    success: bool
    status: str
    started_at: str
    ended_at: str
    tokens: int
    tool_calls: int
    steps: int
    latency_seconds: float
    outcome_summary: str
    events: list[TrajectoryEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UtilityBreakdown:
    success_gain: float
    token_gain: float
    tool_gain: float
    step_gain: float
    latency_gain: float
    efficiency_gain: float
    transfer_gain: float
    interference_cost: float
    overall_score: float
    notes: list[str] = field(default_factory=list)


@dataclass
class DiagnosisEvidence:
    source: str
    snippet: str
    reason: str


@dataclass
class DiagnosisReport:
    labels: list[FailureType]
    evidence: list[DiagnosisEvidence]
    causal_judgment: str
    rewrite_targets: list[str]
    summary: str


@dataclass
class RepairPrinciple:
    principle_id: str
    title: str
    defect_labels: list[str]
    failure_types: list[FailureType]
    trigger_keywords: list[str]
    trigger_evidence: str
    repair_rule: str
    transfer_constraint: str
    supporting_cases: list[str] = field(default_factory=list)
    acceptance_evidence: list[str] = field(default_factory=list)
    intent: str = ""
    trigger: str = ""
    applicable_failure_modes: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    retrieval_text: str = ""
    action_template: str = ""
    verification_template: str = ""
    escalation_rule: str = ""
    supporting_episodes: list[dict[str, Any]] = field(default_factory=list)
    negative_episodes: list[dict[str, Any]] = field(default_factory=list)
    utility_stats: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    status: str = "active"


@dataclass
class RevisionCandidate:
    parent_version: str
    revised_skill: Skill
    rationale: str
    principles: list[RepairPrinciple] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PairedEvaluation:
    task: TaskSpec
    skill: Skill
    no_skill: ExecutionTrace
    with_skill: ExecutionTrace
    utility: UtilityBreakdown
    transfer_summary: dict[str, float] = field(default_factory=dict)


@dataclass
class HarnessIteration:
    iteration_index: int
    skill: Skill
    evaluation: PairedEvaluation
    diagnosis: DiagnosisReport
    revision: RevisionCandidate | None = None


@dataclass
class HarnessResult:
    task: TaskSpec
    initial_skill: Skill
    iterations: list[HarnessIteration]
    selected_skill: Skill
    selected_evaluation: PairedEvaluation
