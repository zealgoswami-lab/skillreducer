"""Run @tscg/core via the Node bridge to compress tool schemas."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TscgError(RuntimeError):
    """TSCG bridge failed or is unavailable."""


@dataclass
class TscgResult:
    compressed: str
    original_tokens: int = 0
    compressed_tokens: int = 0
    savings_percent: float = 0.0
    applied_principles: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def savings(self) -> float:
        if self.original_tokens <= 0:
            return 0.0
        return 1.0 - self.compressed_tokens / self.original_tokens


def bridge_dir() -> Path:
    return Path(__file__).resolve().parent


def bridge_script() -> Path:
    return bridge_dir() / "bridge.mjs"


def node_available() -> bool:
    return shutil.which("node") is not None


def tscg_dependency_installed() -> bool:
    local = bridge_dir() / "node_modules" / "@tscg" / "core"
    return local.is_dir()


def compress_tools(
    tools: list[dict[str, Any]],
    *,
    model: str = "claude-sonnet",
    profile: str = "balanced",
    timeout_s: float = 60.0,
) -> TscgResult:
    """Compress tool definitions with @tscg/core (Node bridge)."""
    if not tools:
        raise TscgError("No tools to compress")
    if not node_available():
        raise TscgError("Node.js not found on PATH (need Node >= 18 for TSCG)")
    if not bridge_script().is_file():
        raise TscgError(f"Missing TSCG bridge: {bridge_script()}")
    if not tscg_dependency_installed():
        raise TscgError(
            "TSCG dependency missing. Run: cd skillreducer/tscg && npm install"
        )

    payload = json.dumps({"tools": tools, "model": model, "profile": profile})
    try:
        proc = subprocess.run(
            ["node", str(bridge_script())],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(bridge_dir()),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TscgError(f"TSCG bridge timed out after {timeout_s}s") from exc
    except OSError as exc:
        raise TscgError(f"Failed to run Node bridge: {exc}") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise TscgError(f"TSCG bridge failed: {err}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise TscgError(f"TSCG bridge returned invalid JSON: {exc}") from exc

    metrics = data.get("metrics") or {}
    tokens = metrics.get("tokens") or {}
    original = int(tokens.get("original") or 0)
    compressed_tok = int(tokens.get("compressed") or 0)
    savings_pct = float(tokens.get("savingsPercent") or 0.0)
    compressed = data.get("compressed") or ""
    if not compressed:
        raise TscgError("TSCG bridge returned empty compressed output")

    note = (
        f"TSCG: schema tokens {original} -> {compressed_tok} "
        f"({savings_pct:.1f}% savings)"
    )
    return TscgResult(
        compressed=compressed,
        original_tokens=original,
        compressed_tokens=compressed_tok,
        savings_percent=savings_pct,
        applied_principles=list(data.get("appliedPrinciples") or []),
        metrics=metrics if isinstance(metrics, dict) else {},
        notes=[note],
    )


def write_tscg_outputs(
    out_dir: Path,
    tools: list[dict[str, Any]],
    result: TscgResult,
) -> list[str]:
    """Write mcp_manifest.json + compressed artifacts. Returns relative paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    manifest_path = out_dir / "mcp_manifest.json"
    manifest_path.write_text(
        json.dumps({"tools": tools}, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append("mcp_manifest.json")

    txt_path = out_dir / "mcp_manifest.tscg.txt"
    txt_path.write_text(result.compressed.rstrip() + "\n", encoding="utf-8")
    written.append("mcp_manifest.tscg.txt")

    meta = {
        "compressed": result.compressed,
        "metrics": result.metrics,
        "appliedPrinciples": result.applied_principles,
        "original_tokens": result.original_tokens,
        "compressed_tokens": result.compressed_tokens,
        "savings_percent": result.savings_percent,
    }
    meta_path = out_dir / "mcp_manifest.tscg.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    written.append("mcp_manifest.tscg.json")
    return written
