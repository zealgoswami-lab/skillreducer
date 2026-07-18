from __future__ import annotations

from rich.console import Console
from rich.table import Table

from skillreducer.models import AuditReport, ReduceReport

console = Console()


def print_audit_report(report: AuditReport) -> None:
    console.print(f"\n[bold]Skill audit:[/bold] {report.skill_path}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Tokens", justify="right")
    table.add_row("Description", str(report.stats.description))
    table.add_row("Body", str(report.stats.body))
    table.add_row("References", str(report.stats.references))
    table.add_row("Total", str(report.stats.total), style="bold")
    console.print(table)
    console.print(f"Body lines: {report.body_lines} | Reference files: {report.reference_count}")

    if not report.issues:
        console.print("[green]No issues detected.[/green]")
        return

    console.print("\n[bold]Issues[/bold]")
    for issue in report.issues:
        color = {"error": "red", "warning": "yellow", "info": "cyan"}.get(issue.severity, "white")
        console.print(f"[{color}]{issue.code}[/{color}] {issue.message}")


def print_reduce_report(report: ReduceReport) -> None:
    console.print(f"\n[bold]Reduced skill:[/bold] {report.output}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Savings", justify="right")

    def pct(before: int, after: int) -> str:
        if before == 0:
            return "-"
        return f"{(1 - after / before) * 100:.1f}%"

    table.add_row(
        "Description",
        str(report.original_stats.description),
        str(report.optimized_stats.description),
        pct(report.original_stats.description, report.optimized_stats.description),
    )
    table.add_row(
        "Body",
        str(report.original_stats.body),
        str(report.optimized_stats.body),
        pct(report.original_stats.body, report.optimized_stats.body),
    )
    table.add_row(
        "References",
        str(report.original_stats.references),
        str(report.optimized_stats.references),
        pct(report.original_stats.references, report.optimized_stats.references),
    )
    table.add_row(
        "Total",
        str(report.original_stats.total),
        str(report.optimized_stats.total),
        f"{report.total_savings * 100:.1f}%",
        style="bold",
    )
    console.print(table)

    if report.tscg_stats is not None:
        t = report.tscg_stats
        console.print("\n[bold]TSCG (tool schemas)[/bold]")
        console.print(
            f"  Tools: {t.tool_count} | "
            f"{t.original_tokens} -> {t.compressed_tokens} tokens "
            f"({t.savings * 100:.1f}% savings)"
        )

    if report.files_written:
        console.print("\n[bold]Files written[/bold]")
        for name in report.files_written:
            console.print(f"  - {name}")

    if report.stage_notes:
        console.print("\n[bold]Notes[/bold]")
        for note in report.stage_notes:
            console.print(f"  - {note}")
