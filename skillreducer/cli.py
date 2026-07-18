from __future__ import annotations

from pathlib import Path

import click

from skillreducer import __version__
from skillreducer.agent import SkillReducerAgent
from skillreducer.audit import audit_skill
from skillreducer.config import Config, ensure_dotenv_loaded
from skillreducer.parser import find_skill_paths
from skillreducer.pipeline import reduce_skill
from skillreducer.report import print_audit_report, print_reduce_report


@click.group()
@click.version_option(__version__, prog_name="skillreducer")
def main() -> None:
    """Implementation of SkillReducer (Gao et al., arXiv:2603.29919) for LLM agent skills."""
    ensure_dotenv_loaded()


@main.command("audit")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", "-r", is_flag=True, help="Audit all skills under PATH")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def audit_cmd(path: Path, recursive: bool, config_path: Path | None) -> None:
    """Audit skill token usage and report routing/body issues."""
    config = Config.load(config_path)
    skill_paths = find_skill_paths(path, recursive=recursive)
    if not skill_paths:
        raise click.ClickException(f"No skill files (SKILL.md) found under {path}")

    for skill_path in skill_paths:
        report = audit_skill(skill_path, config)
        print_audit_report(report)


@main.command("reduce")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("optimized"))
@click.option("--recursive", "-r", is_flag=True, help="Reduce all skills under PATH")
@click.option("--stage", type=click.Choice(["1", "2", "3"]), default=None, help="Run a single stage")
@click.option("--dry-run", is_flag=True, help="Compute report without writing files")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--no-llm", is_flag=True, help="Use heuristic mode without LLM API calls")
@click.option(
    "--tscg/--no-tscg",
    default=None,
    help="Compress tool schemas with TSCG (requires Node + npm install in skillreducer/tscg)",
)
@click.option(
    "--tools",
    "tools_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Tool / MCP manifest JSON for TSCG (OpenAI, Anthropic, or {tools: [...]})",
)
def reduce_cmd(
    path: Path,
    output: Path,
    recursive: bool,
    stage: str | None,
    dry_run: bool,
    config_path: Path | None,
    no_llm: bool,
    tscg: bool | None,
    tools_path: Path | None,
) -> None:
    """Reduce skill token cost via routing compression and progressive disclosure."""
    config = Config.load(config_path)
    if no_llm:
        config.use_llm = False
    if tscg is True:
        config.tscg_enabled = True
    elif tscg is False:
        config.tscg_enabled = False

    skill_paths = find_skill_paths(path, recursive=recursive)
    if not skill_paths:
        raise click.ClickException(f"No skill files (SKILL.md) found under {path}")

    stage_num = int(stage) if stage else None
    for skill_path in skill_paths:
        report = reduce_skill(
            skill_path,
            output_dir=output,
            config=config,
            stage=stage_num,
            dry_run=dry_run,
            tscg=tscg,
            tools_path=tools_path,
        )
        print_reduce_report(report)


@main.command("agent")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("optimized"))
@click.option("--recursive", "-r", is_flag=True, help="Optimize all skills under PATH")
@click.option("--stage", type=click.Choice(["1", "2", "3"]), default=None, help="Run a single stage")
@click.option("--dry-run", is_flag=True, help="Compute report without writing files")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option(
    "--tscg/--no-tscg",
    default=None,
    help="Compress tool schemas with TSCG after optimization",
)
@click.option(
    "--tools",
    "tools_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Tool / MCP manifest JSON for TSCG",
)
def agent_cmd(
    path: Path,
    output: Path,
    recursive: bool,
    stage: str | None,
    dry_run: bool,
    config_path: Path | None,
    tscg: bool | None,
    tools_path: Path | None,
) -> None:
    """Optimize skills using the Agno agent (skill folder in, updated files out)."""
    config = Config.load(config_path)
    if tscg is True:
        config.tscg_enabled = True
    elif tscg is False:
        config.tscg_enabled = False
    agent = SkillReducerAgent(config)
    stage_num = int(stage) if stage else None

    skill_paths = find_skill_paths(path, recursive=recursive)
    if not skill_paths:
        raise click.ClickException(f"No skill files (SKILL.md) found under {path}")

    for skill_path in skill_paths:
        result = agent.optimize(
            skill_path,
            output_dir=output,
            stage=stage_num,
            dry_run=dry_run,
            tscg=tscg,
            tools_path=tools_path,
        )
        if result.report:
            print_reduce_report(result.report)
        click.echo(result.agent_summary)
        if not dry_run:
            click.echo(f"Wrote: {result.output_dir}")


if __name__ == "__main__":
    main()
