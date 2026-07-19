"""Tests for SkillRevise CLI forward (vendored under src/skillrevise)."""

from __future__ import annotations

from click.testing import CliRunner

from skillreducer.cli import main


def test_vendored_skillrevise_imports() -> None:
    import skillrevise
    from skillrevise.cli import main as skillrevise_main

    assert callable(skillrevise_main)
    assert skillrevise.__doc__


def test_revise_command_usage_when_no_args() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["revise"])
    assert result.exit_code == 0, result.output
    assert "skillreducer revise" in result.output
    assert "src/skillrevise/README.md" in result.output


def test_revise_command_forwards_argv(monkeypatch) -> None:
    seen: list[str] = []

    def fake_main() -> None:
        import sys

        seen.extend(sys.argv[1:])

    monkeypatch.setattr("skillrevise.cli.main", fake_main)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["revise", "tasks.json", "--max-revisions", "3", "--baseline-only"],
    )
    assert result.exit_code == 0, result.output
    assert seen == ["tasks.json", "--max-revisions", "3", "--baseline-only"]


def test_revise_command_missing_import_message(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "skillrevise" or name.startswith("skillrevise."):
            raise ImportError("simulated missing skillrevise")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    runner = CliRunner()
    result = runner.invoke(main, ["revise", "tasks.json"])
    assert result.exit_code != 0
    assert "SkillRevise" in result.output or "src/skillrevise" in result.output
