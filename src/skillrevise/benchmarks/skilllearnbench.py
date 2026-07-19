from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from skillrevise.core.models import TaskSpec


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "tasks" in payload:
        return list(payload["tasks"])
    if isinstance(payload, list):
        return list(payload)
    raise ValueError(f"Unsupported SkillLearnBench manifest shape in {path}")


class SkillLearnBenchTaskLoader:
    """Load SkillLearnBench task instances into the generic skill harness.

    SkillLearnBench stores instances as:

        tasks/<task-family>/<task-family>-N/{instruction.md, task.toml, ...}

    The loader intentionally exposes each instance as a TaskSpec while keeping the
    family at the top-level task name. For standard SkillLearnBench continual
    learning, run only the first instance of each family for skill generation,
    then export the selected skills and evaluate all instances with the upstream
    evaluator.
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = None if workspace_root is None else Path(workspace_root).resolve()

    def load(self, path: str | Path) -> list[TaskSpec]:
        input_path = self._resolve_root_or_manifest(path)
        if input_path.is_file():
            tasks = [self._record_to_task(record, index) for index, record in enumerate(_load_json_records(input_path))]
        else:
            tasks = [self._instance_to_task(instance) for instance in self._iter_instances(input_path)]
        tasks.sort(key=lambda item: item.task_id)
        return tasks

    def _resolve_root_or_manifest(self, path: str | Path) -> Path:
        input_path = Path(path)
        if not input_path.is_absolute() and self.workspace_root is not None:
            input_path = self.workspace_root / input_path
        return input_path.resolve()

    def _iter_instances(self, root_or_tasks_dir: Path) -> list[Path]:
        tasks_dir = root_or_tasks_dir / "tasks" if (root_or_tasks_dir / "tasks").is_dir() else root_or_tasks_dir
        if not tasks_dir.is_dir():
            raise ValueError(f"SkillLearnBench tasks directory not found: {tasks_dir}")

        instances: list[Path] = []
        for family_dir in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
            for instance_dir in sorted(path for path in family_dir.iterdir() if path.is_dir()):
                if (instance_dir / "instruction.md").is_file() and (instance_dir / "environment" / "Dockerfile").is_file():
                    instances.append(instance_dir)
        return instances

    def _instance_to_task(self, instance_dir: Path) -> TaskSpec:
        family = instance_dir.parent.name
        query_name = instance_dir.name
        task_id = f"{family}/{query_name}"
        instruction = (instance_dir / "instruction.md").read_text(errors="replace").strip()
        task_config = _read_toml(instance_dir / "task.toml")
        category = str(task_config.get("metadata", {}).get("category", "skilllearnbench"))
        tags = [str(item) for item in task_config.get("metadata", {}).get("tags", [])]

        return TaskSpec(
            task_id=task_id,
            family=family,
            instruction="\n\n".join(
                [
                    f"SkillLearnBench family: {family}",
                    f"Training/evaluation instance: {query_name}",
                    "Visible task instruction:",
                    instruction,
                ]
            ),
            acceptance_criteria=[
                "Produce a reusable Claude/Codex skill for this SkillLearnBench task family.",
                "Do not rely on hidden verifier files or solution scripts.",
                "The upstream SkillLearnBench verifier should pass when the skill is injected.",
            ],
            context={
                    "skilllearnbench_root": str(instance_dir.parents[2].resolve()),
                "instance_dir": str(instance_dir.resolve()),
                "task_config": task_config,
            },
            tags=[category, *tags],
            metadata={
                "skilllearnbench_root": str(instance_dir.parents[2].resolve()),
                "skilllearnbench_task": family,
                "skilllearnbench_instance": query_name,
                "skilllearnbench_query_id": task_id,
                "timeout_seconds": int(task_config.get("agent", {}).get("timeout_sec", 1800) or 1800),
            },
        )

    def _record_to_task(self, record: dict[str, Any], index: int) -> TaskSpec:
        task_id = str(record.get("task_id") or record.get("id") or f"task-{index}")
        family = str(record.get("family") or record.get("skilllearnbench_task") or task_id.split("/")[0])
        metadata = dict(record.get("metadata") or {})
        for key in ("skilllearnbench_root", "skilllearnbench_task", "skilllearnbench_instance", "timeout_seconds"):
            if key in record and key not in metadata:
                metadata[key] = record[key]
        return TaskSpec(
            task_id=task_id,
            family=family,
            instruction=str(record.get("instruction") or record.get("prompt") or ""),
            acceptance_criteria=list(record.get("acceptance_criteria") or []),
            context=dict(record.get("context") or {}),
            tags=list(record.get("tags") or []),
            metadata=metadata,
        )


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        if sys.version_info >= (3, 11):
            import tomllib
        else:  # pragma: no cover - Python < 3.11 compatibility
            import tomli as tomllib  # type: ignore[no-redef]
        return tomllib.loads(path.read_text())
    except Exception:
        return {}
