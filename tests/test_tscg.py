from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skillreducer.config import Config
from skillreducer.models import TscgStats
from skillreducer.pipeline import reduce_skill
from skillreducer.tscg.compress import TscgError, TscgResult, compress_tools
from skillreducer.tscg.manifest import (
    load_tools_json,
    normalize_tools,
    tools_from_scripts,
)


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    }
]


def _write_skill(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill for tests\n---\n\n"
        "# Demo\n\nDo the thing carefully.\n",
        encoding="utf-8",
    )
    return skill_dir


def test_normalize_openai_and_mcp_tools() -> None:
    openai = normalize_tools(SAMPLE_TOOLS)
    assert openai[0]["function"]["name"] == "get_weather"

    mcp = normalize_tools(
        {
            "tools": [
                {
                    "name": "ping",
                    "description": "Ping a host",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"host": {"type": "string"}},
                        "required": ["host"],
                    },
                }
            ]
        }
    )
    assert mcp[0]["type"] == "function"
    assert mcp[0]["function"]["name"] == "ping"
    assert "host" in mcp[0]["function"]["parameters"]["properties"]


def test_tools_from_scripts() -> None:
    tools = tools_from_scripts(["scripts/extract_pdf.py", "scripts/run_job.sh"])
    assert [t["function"]["name"] for t in tools] == ["extract_pdf", "run_job"]


def test_load_tools_json(tmp_path: Path) -> None:
    path = tmp_path / "tools.json"
    path.write_text(json.dumps({"tools": SAMPLE_TOOLS}), encoding="utf-8")
    loaded = load_tools_json(path)
    assert len(loaded) == 1
    assert loaded[0]["function"]["name"] == "get_weather"


def test_compress_tools_requires_node_dep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillreducer.tscg.compress.node_available", lambda: False)
    with pytest.raises(TscgError, match="Node.js"):
        compress_tools(SAMPLE_TOOLS)


def test_reduce_with_tscg_mocked(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path)
    tools_path = tmp_path / "tools.json"
    tools_path.write_text(json.dumps(SAMPLE_TOOLS), encoding="utf-8")
    out = tmp_path / "optimized"

    fake = TscgResult(
        compressed="get_weather(location:str!) -> weather",
        original_tokens=100,
        compressed_tokens=40,
        savings_percent=60.0,
        applied_principles=["sdm"],
        metrics={"tokens": {"original": 100, "compressed": 40, "savingsPercent": 60.0}},
        notes=["TSCG: schema tokens 100 -> 40 (60.0% savings)"],
    )

    with patch("skillreducer.pipeline.compress_tools", return_value=fake):
        report = reduce_skill(
            skill_dir,
            output_dir=out,
            config=Config(use_llm=False, tscg_enabled=True),
            stage=1,
            tscg=True,
            tools_path=tools_path,
        )

    assert report.tscg_stats == TscgStats(
        original_tokens=100, compressed_tokens=40, tool_count=1
    )
    assert (out / "demo-skill" / "mcp_manifest.json").is_file()
    assert (out / "demo-skill" / "mcp_manifest.tscg.txt").is_file()
    assert (out / "demo-skill" / "mcp_manifest.tscg.json").is_file()
    assert any("TSCG:" in n for n in report.stage_notes)


def test_reduce_tscg_skips_without_tools(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path)
    out = tmp_path / "optimized"
    report = reduce_skill(
        skill_dir,
        output_dir=out,
        config=Config(use_llm=False),
        stage=1,
        tscg=True,
    )
    assert report.tscg_stats is None
    assert any("TSCG skipped: no tools" in n for n in report.stage_notes)
