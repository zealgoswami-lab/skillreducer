from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any


class ContentType(str, Enum):
    CORE_RULE = "core_rule"
    BACKGROUND = "background"
    EXAMPLE = "example"
    TEMPLATE = "template"
    REDUNDANT = "redundant"


@dataclass
class ContentItem:
    text: str
    content_type: ContentType
    index: int = 0


@dataclass
class ReferenceFile:
    path: Path
    content: str
    token_count: int = 0
    when: str = ""
    topics: list[str] = field(default_factory=list)


@dataclass
class Skill:
    path: Path
    name: str
    description: str
    body: str
    frontmatter: dict
    references: list[ReferenceFile] = field(default_factory=list)

    @property
    def skill_dir(self) -> Path:
        return self.path.parent


def _as_int(value: Any) -> int:
    """Coerce provider metric values to int; treat unknown types as 0."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _as_cost(value: Any) -> float | None:
    """Coerce a provider cost field to float, or None if missing."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


@dataclass
class TokenStats:
    description: int = 0
    body: int = 0
    references: int = 0

    @property
    def total(self) -> int:
        return self.description + self.body + self.references


@dataclass(slots=True)
class LlmUsage:
    """Accumulated LLM API token consumption (not skill-file token counts).

    Attributes:
        input_tokens: Prompt tokens sent to the model.
        output_tokens: Completion tokens returned by the model.
        total_tokens: Input plus output (and provider extras when reported).
        calls: Number of model requests.
        reasoning_tokens: Reasoning tokens when the provider reports them.
        cost: Estimated USD cost when the provider reports it.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None

    def copy(self) -> LlmUsage:
        """Return a snapshot of current totals."""
        return replace(self)

    def absorb(self, other: LlmUsage) -> None:
        """Add ``other`` into this accumulator."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.calls += other.calls
        self.reasoning_tokens += other.reasoning_tokens
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost

    def since(self, earlier: LlmUsage) -> LlmUsage:
        """Return usage accumulated after ``earlier`` was snapshotted."""
        cost: float | None = None
        if self.cost is not None or earlier.cost is not None:
            cost = (self.cost or 0.0) - (earlier.cost or 0.0)
        return LlmUsage(
            input_tokens=max(0, self.input_tokens - earlier.input_tokens),
            output_tokens=max(0, self.output_tokens - earlier.output_tokens),
            total_tokens=max(0, self.total_tokens - earlier.total_tokens),
            calls=max(0, self.calls - earlier.calls),
            reasoning_tokens=max(0, self.reasoning_tokens - earlier.reasoning_tokens),
            cost=cost,
        )

    def summary(self) -> str:
        """One-line human-readable usage string."""
        if self.calls <= 0:
            return "0 tokens (no LLM calls)"
        text = (
            f"{self.total_tokens} tokens "
            f"({self.input_tokens} in / {self.output_tokens} out, {self.calls} calls)"
        )
        if self.reasoning_tokens:
            text += f", {self.reasoning_tokens} reasoning"
        if self.cost is not None:
            text += f", ${self.cost:.4f}"
        return text

    @classmethod
    def from_agno_run(cls, run: object) -> LlmUsage:
        """Build usage from an Agno ``RunOutput`` (or similar) object."""
        metrics = getattr(run, "metrics", None)
        input_tokens = _as_int(getattr(metrics, "input_tokens", 0) if metrics is not None else 0)
        output_tokens = _as_int(getattr(metrics, "output_tokens", 0) if metrics is not None else 0)
        total_tokens = _as_int(getattr(metrics, "total_tokens", 0) if metrics is not None else 0)
        reasoning_tokens = _as_int(
            getattr(metrics, "reasoning_tokens", 0) if metrics is not None else 0
        )
        cost = _as_cost(getattr(metrics, "cost", None) if metrics is not None else None)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            calls=1,
            reasoning_tokens=reasoning_tokens,
            cost=cost,
        )

    @classmethod
    def from_openai_response(cls, response: object) -> LlmUsage:
        """Build usage from an OpenAI-compatible chat completion response."""
        usage = getattr(response, "usage", None)
        input_tokens = _as_int(getattr(usage, "prompt_tokens", 0) if usage is not None else 0)
        output_tokens = _as_int(getattr(usage, "completion_tokens", 0) if usage is not None else 0)
        total_tokens = _as_int(getattr(usage, "total_tokens", 0) if usage is not None else 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            calls=1,
        )


@dataclass
class AuditIssue:
    code: str
    message: str
    severity: str = "warning"


@dataclass
class AuditReport:
    skill_path: Path
    stats: TokenStats
    issues: list[AuditIssue] = field(default_factory=list)
    body_lines: int = 0
    reference_count: int = 0


@dataclass
class TscgStats:
    """Tool-schema compression metrics (separate from skill TokenStats)."""

    original_tokens: int = 0
    compressed_tokens: int = 0
    tool_count: int = 0

    @property
    def savings(self) -> float:
        if self.original_tokens <= 0:
            return 0.0
        return 1.0 - self.compressed_tokens / self.original_tokens


@dataclass
class ReduceReport:
    source: Path
    output: Path
    original_stats: TokenStats
    optimized_stats: TokenStats
    description_changed: bool = False
    files_written: list[str] = field(default_factory=list)
    stage_notes: list[str] = field(default_factory=list)
    tscg_stats: TscgStats | None = None
    llm_usage: LlmUsage = field(default_factory=LlmUsage)

    @property
    def description_savings(self) -> float:
        if self.original_stats.description == 0:
            return 0.0
        return 1.0 - self.optimized_stats.description / self.original_stats.description

    @property
    def body_savings(self) -> float:
        if self.original_stats.body == 0:
            return 0.0
        return 1.0 - self.optimized_stats.body / self.original_stats.body

    @property
    def total_savings(self) -> float:
        if self.original_stats.total == 0:
            return 0.0
        return 1.0 - self.optimized_stats.total / self.original_stats.total
