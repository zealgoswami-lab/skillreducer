from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from skillreducer.config import Config
from skillreducer.llm.agno_client import AgnoLLMClient
from skillreducer.llm.client import LLMClient
from skillreducer.models import LlmUsage, ReduceReport, TokenStats
from skillreducer.report import print_reduce_report
from skillreducer import report as report_mod


def test_llm_usage_absorb_and_since() -> None:
    first = LlmUsage(input_tokens=10, output_tokens=4, total_tokens=14, calls=1, cost=0.01)
    second = LlmUsage(input_tokens=5, output_tokens=2, total_tokens=7, calls=1, cost=0.02)
    first.absorb(second)
    assert first.input_tokens == 15
    assert first.output_tokens == 6
    assert first.total_tokens == 21
    assert first.calls == 2
    assert first.cost == pytest.approx(0.03)

    earlier = LlmUsage(input_tokens=10, output_tokens=4, total_tokens=14, calls=1, cost=0.01)
    delta = first.since(earlier)
    assert delta.input_tokens == 5
    assert delta.calls == 1
    assert delta.cost == pytest.approx(0.02)


def test_llm_usage_from_agno_run() -> None:
    run = SimpleNamespace(
        metrics=SimpleNamespace(
            input_tokens=40,
            output_tokens=8,
            total_tokens=48,
            reasoning_tokens=3,
            cost=0.004,
        )
    )
    usage = LlmUsage.from_agno_run(run)
    assert usage.input_tokens == 40
    assert usage.output_tokens == 8
    assert usage.total_tokens == 48
    assert usage.reasoning_tokens == 3
    assert usage.calls == 1
    assert usage.cost == 0.004
    assert "48 tokens" in usage.summary()


def test_llm_usage_from_openai_response() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3, total_tokens=15)
    )
    usage = LlmUsage.from_openai_response(response)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 3
    assert usage.total_tokens == 15
    assert usage.calls == 1


def test_agno_llm_client_tracks_usage() -> None:
    agent = MagicMock()
    agent.run.return_value = SimpleNamespace(
        content="ok",
        metrics=SimpleNamespace(
            input_tokens=20,
            output_tokens=5,
            total_tokens=25,
            reasoning_tokens=0,
            cost=None,
        ),
    )
    client = AgnoLLMClient(agent)
    assert client.complete("hello") == "ok"
    assert client.usage.input_tokens == 20
    assert client.usage.output_tokens == 5
    assert client.usage.total_tokens == 25
    assert client.usage.calls == 1


def test_openai_llm_client_tracks_usage() -> None:
    config = Config(api_key="test-key", use_llm=True)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3, total_tokens=15),
    )
    with patch("skillreducer.llm.client.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.return_value = response
        client = LLMClient(config)
        assert client.complete("hi") == "hello"
    assert client.usage.input_tokens == 12
    assert client.usage.output_tokens == 3
    assert client.usage.total_tokens == 15
    assert client.usage.calls == 1


def test_print_reduce_report_includes_llm_usage(monkeypatch) -> None:
    buf = StringIO()
    monkeypatch.setattr(report_mod, "console", Console(file=buf, force_terminal=False))
    report = ReduceReport(
        source=Path("src"),
        output=Path("out"),
        original_stats=TokenStats(10, 100, 0),
        optimized_stats=TokenStats(5, 50, 0),
        llm_usage=LlmUsage(input_tokens=80, output_tokens=40, total_tokens=120, calls=4),
    )
    print_reduce_report(report)
    text = buf.getvalue()
    assert "LLM usage" in text
    assert "120 tokens" in text
    assert "80 in / 40 out" in text
    assert "4 calls" in text
