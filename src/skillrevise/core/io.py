from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from skillrevise.core.models import TaskSpec


def load_tasks(path: str | Path) -> list[TaskSpec]:
    data = json.loads(Path(path).read_text())
    items = data["tasks"] if isinstance(data, dict) and "tasks" in data else data
    tasks: list[TaskSpec] = []
    for item in items:
        tasks.append(
            TaskSpec(
                task_id=item["task_id"],
                family=item["family"],
                instruction=item["instruction"],
                acceptance_criteria=item.get("acceptance_criteria", []),
                context=item.get("context", {}),
                tags=item.get("tags", []),
                metadata=item.get("metadata", {}),
            )
        )
    return tasks


def write_json(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), indent=2, ensure_ascii=True))


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
