"""Tests for the optional SkillRevise CLI wrapper (no upstream install required)."""

from __future__ import annotations

from click.testing import CliRunner

from skillreducer.cli import main
from skillreducer.revise import runner as revise_runner
from skillreducer.revise.runner import (
    INSTALL_HINT,
    SkillReviseNotInstalled,
    run_skillrevise,
    skillrevise_installed,
)


def test_skillrevise_installed_is_bool() -> None:
    assert isinstance(skillrevise_installed(), bool)


def test_run_skillrevise_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(revise_runner, "skillrevise_installed", lambda: False)
    try:
        run_skillrevise(["--help"])
        raise AssertionError("expected SkillReviseNotInstalled")
    except SkillReviseNotInstalled as exc:
        assert "pip install" in str(exc)


def test_revise_command_missing_dep_message(monkeypatch) -> None:
    monkeypatch.setattr(revise_runner, "skillrevise_installed", lambda: False)
    runner = CliRunner()
    result = runner.invoke(main, ["revise", "tasks.json", "--limit", "1"])
    assert result.exit_code != 0
    assert "SkillRevise" in result.output or "pip install" in result.output


def test_revise_command_forwards_argv(monkeypatch) -> None:
    seen: list[str] = []

    def fake_run(argv: list[str]) -> int:
        seen.extend(argv)
        return 0

    monkeypatch.setattr(revise_runner, "run_skillrevise", fake_run)
    monkeypatch.setattr(revise_runner, "skillrevise_installed", lambda: True)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["revise", "tasks.json", "--max-revisions", "3", "--baseline-only"],
    )
    assert result.exit_code == 0, result.output
    assert seen == ["tasks.json", "--max-revisions", "3", "--baseline-only"]


def test_install_hint_mentions_separate_commands() -> None:
    assert "audit" in INSTALL_HINT
    assert "reduce" in INSTALL_HINT
    assert "xuansenpa1/skillrevise" in INSTALL_HINT
    assert "src/skillrevise" in INSTALL_HINT


def test_vendored_skillrevise_imports() -> None:
    """Vendored package under src/ must be importable when on pythonpath."""
    import skillrevise
    from skillrevise.cli import main as skillrevise_main

    assert callable(skillrevise_main)
    assert skillrevise.__doc__
