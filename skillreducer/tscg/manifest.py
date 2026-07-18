"""Build and load MCP / tool manifests for TSCG."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_tools_json(path: Path) -> list[dict[str, Any]]:
    """Load tools from JSON: bare list, {tools: [...]}, or MCP-style entries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return normalize_tools(data)


def normalize_tools(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        if isinstance(data.get("tools"), list):
            raw = data["tools"]
        elif "name" in data and ("parameters" in data or "input_schema" in data or "inputSchema" in data):
            raw = [data]
        else:
            raise ValueError(
                "Tool JSON must be a list, {\"tools\": [...]}, or a single tool object"
            )
    else:
        raise ValueError("Tool JSON must be a list or object")

    tools: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Tool entry must be an object, got {type(item).__name__}")
        tools.append(_to_openai_tool(item))
    if not tools:
        raise ValueError("Tool list is empty")
    return tools


def _to_openai_tool(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenAI, Anthropic, or MCP tool shapes to OpenAI function format."""
    if item.get("type") == "function" and isinstance(item.get("function"), dict):
        return item

    if "function" in item and isinstance(item["function"], dict):
        return {"type": "function", "function": item["function"]}

    name = item.get("name")
    if not name:
        raise ValueError(f"Tool missing name: {list(item.keys())}")

    description = item.get("description") or ""
    params = (
        item.get("parameters")
        or item.get("input_schema")
        or item.get("inputSchema")
        or {"type": "object", "properties": {}}
    )
    return {
        "type": "function",
        "function": {
            "name": str(name),
            "description": str(description),
            "parameters": params,
        },
    }


def tools_from_scripts(script_paths: list[str] | dict[str, str]) -> list[dict[str, Any]]:
    """Build minimal OpenAI-format tools from script file paths (Stage 3 / scripts/)."""
    if isinstance(script_paths, dict):
        paths = list(script_paths.keys())
    else:
        paths = list(script_paths)

    tools: list[dict[str, Any]] = []
    for rel in paths:
        path = Path(rel.replace("\\", "/"))
        stem = path.stem
        name = _safe_tool_name(stem)
        lang = "python" if path.suffix.lower() == ".py" else "shell"
        runner = f"python {path.as_posix()}" if lang == "python" else f"bash {path.as_posix()}"
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Run {path.as_posix()} ({lang}). Invoke via: {runner}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "args": {
                                "type": "string",
                                "description": "Optional CLI arguments for the script",
                            }
                        },
                        "required": [],
                    },
                },
            }
        )
    return tools


def _safe_tool_name(stem: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", stem).strip("_").lower()
    if not name:
        name = "script"
    if name[0].isdigit():
        name = f"run_{name}"
    return name[:64]


def write_mcp_manifest(path: Path, tools: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tools": tools}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def find_existing_manifest(skill_dir: Path) -> Path | None:
    for name in ("mcp_manifest.json", "tools.json"):
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    return None
