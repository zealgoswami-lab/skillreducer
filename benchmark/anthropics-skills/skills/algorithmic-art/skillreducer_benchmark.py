"""Benchmark SkillReducer token savings for the algorithmic-art skill.

Audits this folder's ``SKILL.md``, runs SkillReducer with an LLM, audits the
reduced copy, and writes ``skillreducer_results/result.md``.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    """Return the skillreducer repository root that contains this skill."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "skillreducer").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not find the skillreducer repo root (pyproject.toml + skillreducer/)."
    )


REPO_ROOT = _repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from skillreducer.audit import audit_skill  # noqa: E402
from skillreducer.config import (  # noqa: E402
    Config,
    ensure_dotenv_loaded,
    resolve_api_key,
    resolve_compression_model,
)
from skillreducer.models import AuditReport, ReduceReport, TokenStats  # noqa: E402
from skillreducer.pipeline import reduce_skill  # noqa: E402
from skillreducer.report import print_audit_report, print_reduce_report  # noqa: E402

RESULTS_DIRNAME = "skillreducer_results"
console = Console()


def always_loaded_tokens(stats: TokenStats) -> int:
    """Return tokens always placed in context (description + body).

    Args:
        stats: Token counts for one skill snapshot.

    Returns:
        Sum of description and body tokens.
    """
    return stats.description + stats.body


def _percent(before: int, after: int) -> str:
    """Format savings as a percentage of the before count."""
    if before <= 0:
        return "-"
    return f"{(1.0 - after / before) * 100:.1f}%"


def _saved(before: int, after: int) -> int:
    """Return tokens removed (before minus after)."""
    return before - after


def _display_path(path: Path) -> str:
    """Return a repo-relative POSIX path when the file is inside the repo."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _markdown_stats_table(stats: TokenStats) -> str:
    """Return a markdown table of token counts for one skill snapshot."""
    loaded = always_loaded_tokens(stats)
    return "\n".join(
        [
            "| Component | Tokens |",
            "| --- | ---: |",
            f"| Description | {stats.description} |",
            f"| Body | {stats.body} |",
            f"| References | {stats.references} |",
            f"| Always-loaded (description + body) | {loaded} |",
            f"| Total | {stats.total} |",
        ]
    )


def format_result_markdown(
    *,
    skill_name: str,
    source: Path,
    model_id: str,
    before: TokenStats,
    after: TokenStats,
    report: ReduceReport,
    timestamp: str,
) -> str:
    """Build the before/after token report written to ``result.md``.

    Args:
        skill_name: Skill folder name used in the title.
        source: Original skill directory.
        model_id: Compression model id used for LLM reduction.
        before: Token counts from the original skill.
        after: Token counts from the reduced skill on disk.
        report: Pipeline report with notes and written files.
        timestamp: Human-readable run time.

    Returns:
        Markdown document with before, after, and savings tables.
    """
    before_loaded = always_loaded_tokens(before)
    after_loaded = always_loaded_tokens(after)
    rows = (
        ("Description", before.description, after.description),
        ("Body", before.body, after.body),
        ("References", before.references, after.references),
        ("Always-loaded (description + body)", before_loaded, after_loaded),
        ("Total", before.total, after.total),
    )

    savings_lines = [
        "| Component | Before | After | Saved | Percent |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, before_n, after_n in rows:
        savings_lines.append(
            f"| {label} | {before_n} | {after_n} | {_saved(before_n, after_n)} | "
            f"{_percent(before_n, after_n)} |"
        )

    notes = "\n".join(f"- {note}" for note in report.stage_notes) or "- (none)"
    files = "\n".join(f"- `{name}`" for name in report.files_written) or "- (none)"
    source_display = _display_path(source)
    output_display = _display_path(report.output)

    return "\n".join(
        [
            f"# SkillReducer benchmark: {skill_name}",
            "",
            f"- Source: `{source_display}`",
            f"- Mode: LLM (`{model_id}`)",
            f"- Date: {timestamp}",
            f"- Reduced output: `{output_display}`",
            "",
            "## Token usage before SkillReducer",
            "",
            _markdown_stats_table(before),
            "",
            "## Token usage after SkillReducer",
            "",
            _markdown_stats_table(after),
            "",
            "## Savings",
            "",
            *savings_lines,
            "",
            "## Pipeline notes",
            "",
            notes,
            "",
            "## Files written",
            "",
            files,
            "",
        ]
    )


def print_savings_table(before: TokenStats, after: TokenStats) -> None:
    """Print a console table of before/after token counts and savings.

    Args:
        before: Token counts from the original skill.
        after: Token counts from the reduced skill.
    """
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Saved", justify="right")
    table.add_column("Percent", justify="right")

    rows = (
        ("Description", before.description, after.description),
        ("Body", before.body, after.body),
        ("References", before.references, after.references),
        (
            "Always-loaded",
            always_loaded_tokens(before),
            always_loaded_tokens(after),
        ),
        ("Total", before.total, after.total),
    )
    for index, (label, before_n, after_n) in enumerate(rows):
        style = "bold" if index >= len(rows) - 2 else None
        table.add_row(
            label,
            str(before_n),
            str(after_n),
            str(_saved(before_n, after_n)),
            _percent(before_n, after_n),
            style=style,
        )
    console.print(table)


def run_benchmark(skill_dir: Path, config: Config) -> Path:
    """Audit a skill, reduce it with an LLM, and write ``result.md``.

    Args:
        skill_dir: Skill folder containing ``SKILL.md``.
        config: Loaded SkillReducer config (LLM required).

    Returns:
        Path to the written ``result.md``.

    Raises:
        FileNotFoundError: If ``SKILL.md`` is missing.
        ValueError: If no API key is configured.
    """
    skill_dir = skill_dir.resolve()
    if not (skill_dir / "SKILL.md").is_file() and not (skill_dir / "skill.md").is_file():
        raise FileNotFoundError(f"No SKILL.md found in {skill_dir}")

    api_key = resolve_api_key(config)
    if not api_key:
        raise ValueError(
            "API key required for LLM reduction. Set api_key in .env or the environment, "
            "or in config.yaml."
        )

    model_id = resolve_compression_model(config)
    results_dir = skill_dir / RESULTS_DIRNAME
    results_dir.mkdir(parents=True, exist_ok=True)

    before_report: AuditReport = audit_skill(skill_dir, config)
    print_audit_report(before_report)

    reduce_report = reduce_skill(
        skill_dir,
        output_dir=results_dir,
        config=config,
    )
    print_reduce_report(reduce_report)

    after_report = audit_skill(reduce_report.output, config)
    console.print("\n[bold]Token savings[/bold]")
    print_savings_table(before_report.stats, after_report.stats)

    result_path = results_dir / "result.md"
    result_path.write_text(
        format_result_markdown(
            skill_name=skill_dir.name,
            source=skill_dir,
            model_id=model_id,
            before=before_report.stats,
            after=after_report.stats,
            report=reduce_report,
            timestamp=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        ),
        encoding="utf-8",
    )
    console.print(f"\nWrote: {result_path}")
    return result_path


def main() -> int:
    """Run the algorithmic-art SkillReducer token benchmark.

    Returns:
        Process exit code (``0`` on success, ``1`` on configuration errors).
    """
    ensure_dotenv_loaded()
    config = Config.load()
    config.use_llm = True
    skill_dir = Path(__file__).resolve().parent
    try:
        run_benchmark(skill_dir, config)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
