from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skillrevise.core.io import to_jsonable
from skillrevise.core.models import ExecutionTrace, Skill, TaskSpec


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def start_run(self, task_id: str, label: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.root / task_id / f"{timestamp}-{label}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def write_task(self, task: TaskSpec, run_dir: str | Path) -> Path:
        return self.write_json("task.json", to_jsonable(task), run_dir)

    def write_skill(self, skill: Skill, run_dir: str | Path, filename: str | None = None) -> Path:
        target = Path(run_dir) / (filename or f"skill_{skill.version}.md")
        target.write_text(skill.as_markdown())
        return target

    def write_trace(self, trace: ExecutionTrace, run_dir: str | Path, filename: str = "execution_trace.json") -> Path:
        return self.write_json(filename, to_jsonable(trace), run_dir)

    def write_json(self, filename: str, payload: Any, run_dir: str | Path) -> Path:
        target = Path(run_dir) / filename
        target.write_text(__import__("json").dumps(payload, indent=2, ensure_ascii=True))
        return target

    def write_text(self, filename: str, content: str, run_dir: str | Path) -> Path:
        target = Path(run_dir) / filename
        target.write_text(content)
        return target
