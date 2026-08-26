from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skillreducer.agent import SkillOptimizationResult, SkillReducerAgent
from skillreducer.config import Config


@pytest.fixture
def mock_agno_agent():
    run_output = MagicMock()
    run_output.content = "ok"
    agent = MagicMock()
    agent.run.return_value = run_output
    return agent


def test_skill_optimization_result_paths(tmp_path: Path) -> None:
    out = tmp_path / "optimized" / "my-skill"
    out.mkdir(parents=True)
    skill_md = out / "SKILL.md"
    skill_md.write_text("---\nname: my-skill\n---\n", encoding="utf-8")
    examples = out / "examples.md"
    examples.write_text("# examples\n", encoding="utf-8")

    result = SkillOptimizationResult(
        input_dir=tmp_path / "input",
        output_dir=out,
        skill_md=skill_md,
        reference_files=[examples],
    )
    assert skill_md in result.all_files
    assert examples in result.all_files


@patch("skillreducer.agent.Stage1RoutingAgent")
@patch("skillreducer.agent.create_skill_reducer_agent")
@patch("skillreducer.agent.create_completion_agent")
@patch("skillreducer.agent.reduce_skill")
def test_skill_reducer_agent_optimize_dry_run(
    mock_reduce,
    mock_completion,
    mock_orchestrator,
    mock_stage1_cls,
    mock_agno_agent,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: test skill\n---\n# Body\n",
        encoding="utf-8",
    )

    mock_orchestrator.return_value = mock_agno_agent
    mock_completion.return_value = mock_agno_agent
    mock_stage1_cls.return_value.run.return_value = MagicMock(
        description="compressed skill",
        notes=["Stage 1: test"],
        generated=False,
        compressed=True,
    )

    from skillreducer.models import LlmUsage, ReduceReport, TokenStats

    mock_reduce.return_value = ReduceReport(
        source=skill_dir / "SKILL.md",
        output=tmp_path / "optimized" / "my-skill",
        original_stats=TokenStats(10, 100, 0),
        optimized_stats=TokenStats(5, 50, 0),
        files_written=["SKILL.md"],
        llm_usage=LlmUsage(input_tokens=80, output_tokens=20, total_tokens=100, calls=3),
    )

    config = Config(api_key="test-key", use_llm=True)
    agent = SkillReducerAgent(config)
    result = agent.optimize(skill_dir, output_dir=tmp_path / "optimized", dry_run=True)

    assert result.input_dir == skill_dir.resolve()
    assert result.report is not None
    assert "Optimized" in result.agent_summary
    assert "LLM used 100 tokens" in result.agent_summary
    assert "80 in / 20 out" in result.agent_summary
    mock_reduce.assert_called_once()


def test_create_openai_chat_requires_agno() -> None:
    from skillreducer.model import create_openai_chat

    config = Config(api_key="test-key")
    model = create_openai_chat(config)
    assert model.id == config.compression_model
