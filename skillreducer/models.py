from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


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


@dataclass
class TokenStats:
    description: int = 0
    body: int = 0
    references: int = 0

    @property
    def total(self) -> int:
        return self.description + self.body + self.references


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
