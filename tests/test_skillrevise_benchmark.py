"""Tests for SkillRevise benchmark-only entry point."""

from __future__ import annotations

import pytest

from skillrevise.benchmarks.run_benchmark import BENCHMARK_KINDS, main as benchmark_main


def test_benchmark_help_prints_banner(capsys) -> None:
    benchmark_main(["--help"])
    out = capsys.readouterr().out
    assert "BENCHMARK" in out
    assert "skillsbench" in out


def test_benchmark_requires_manifest_kind(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        benchmark_main(["tasks.json", "--limit", "1"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--manifest-kind" in err


def test_benchmark_rejects_generic(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        benchmark_main(["tasks.json", "--manifest-kind", "generic"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "generic" in err


def test_benchmark_kinds_are_eval_only() -> None:
    assert "generic" not in BENCHMARK_KINDS
    assert "skillsbench" in BENCHMARK_KINDS
