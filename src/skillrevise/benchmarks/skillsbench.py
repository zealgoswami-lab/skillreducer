from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from skillrevise.core.models import TaskSpec


def _load_records(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    if input_path.suffix == ".jsonl":
        return [json.loads(line) for line in input_path.read_text().splitlines() if line.strip()]
    payload = json.loads(input_path.read_text())
    if isinstance(payload, dict) and "tasks" in payload:
        return list(payload["tasks"])
    if isinstance(payload, list):
        return list(payload)
    raise ValueError(f"Unsupported manifest shape in {input_path}")


class SkillsBenchTaskLoader:
    """Maps a generic SkillsBench-style manifest into TaskSpec objects.

    The loader is intentionally permissive because benchmark manifests often differ
    across local experiments. We normalize the most common field names and keep the
    remainder in metadata so the method code can stay stable.
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = None if workspace_root is None else Path(workspace_root).resolve()

    def load(self, path: str | Path) -> list[TaskSpec]:
        records = _load_records(path)
        tasks = [self._to_task_spec(record, index) for index, record in enumerate(records)]
        tasks.sort(key=lambda item: item.task_id)
        return tasks

    def _to_task_spec(self, record: dict[str, Any], index: int) -> TaskSpec:
        task_id = str(record.get("task_id") or record.get("id") or f"task-{index}")
        family = str(
            record.get("family")
            or record.get("family_id")
            or record.get("skill_id")
            or record.get("subdomain")
            or record.get("domain")
            or "unassigned"
        )
        instruction = str(
            record.get("instruction")
            or record.get("requirement")
            or record.get("task")
            or record.get("prompt")
            or ""
        )
        acceptance = record.get("acceptance_criteria") or record.get("acceptance") or []
        if isinstance(acceptance, str):
            acceptance = [acceptance]
        tags = record.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]

        context = dict(record.get("context") or {})
        metadata = dict(record.get("metadata") or {})
        passthrough_keys = (
            "repo_path",
            "commit",
            "verifier_command",
            "timeout_seconds",
            "curated_skill_ids",
            "domain",
            "subdomain",
            "split",
        )
        for key in passthrough_keys:
            if key in record and key not in metadata:
                metadata[key] = record[key]

        repo_path = metadata.get("repo_path")
        if repo_path and self.workspace_root is not None:
            repo = Path(repo_path)
            if not repo.is_absolute():
                metadata["repo_path"] = str((self.workspace_root / repo).resolve())

        return TaskSpec(
            task_id=task_id,
            family=family,
            instruction=instruction,
            acceptance_criteria=list(acceptance),
            context=context,
            tags=list(tags),
            metadata=metadata,
        )


def build_family_index(tasks: Sequence[TaskSpec]) -> dict[str, list[TaskSpec]]:
    families: dict[str, list[TaskSpec]] = defaultdict(list)
    for task in tasks:
        families[task.family].append(task)
    for family in families:
        families[family].sort(key=lambda item: item.task_id)
    return dict(families)


def select_sibling_tasks(
    task: TaskSpec,
    family_index: dict[str, list[TaskSpec]],
    *,
    max_tasks: int | None = None,
) -> list[TaskSpec]:
    siblings = [candidate for candidate in family_index.get(task.family, []) if candidate.task_id != task.task_id]
    if max_tasks is not None:
        siblings = siblings[:max_tasks]
    return siblings


def family_coverage(tasks: Sequence[TaskSpec]) -> dict[str, int]:
    return {family: len(items) for family, items in build_family_index(tasks).items()}
