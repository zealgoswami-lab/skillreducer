from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from skillrevise.core.models import TaskSpec


def _load_records(path: str | Path) -> list[dict[str, Any] | str]:
    input_path = Path(path)
    payload = json.loads(input_path.read_text())
    if isinstance(payload, dict) and "tasks" in payload:
        return list(payload["tasks"])
    if isinstance(payload, list):
        return list(payload)
    raise ValueError(f"Unsupported ALFWorld manifest shape in {input_path}")


class ALFWorldTaskLoader:
    """Load ALFWorld text-only task folders into generic TaskSpec objects."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = _resolve_data_root(root)

    def load(self, source: str | Path) -> list[TaskSpec]:
        source_path = Path(source)
        if source_path.exists():
            records = _load_records(source_path)
            items = [self._record_to_task(record, index=index) for index, record in enumerate(records)]
        else:
            split = str(source)
            records = [
                {"split": split, "problem_path": str(path)}
                for path in _find_problem_dirs(self.root, split)
            ]
            items = [self._record_to_task(record, index=index) for index, record in enumerate(records)]
        items.sort(key=lambda item: item.task_id)
        return items

    def _record_to_task(self, record: dict[str, Any] | str, *, index: int) -> TaskSpec:
        if isinstance(record, str):
            record_data: dict[str, Any] = {}
            problem_path = _resolve_problem_path(self.root, record)
        else:
            record_data = dict(record)
            raw_path = record_data.get("problem_path") or record_data.get("path") or record_data.get("task_path")
            if raw_path:
                problem_path = _resolve_problem_path(self.root, str(raw_path))
            else:
                problem_path = _problem_path_from_id(self.root, str(record_data.get("task_id") or ""))

        task_data = _read_public_task_data(problem_path)
        split = str(record_data.get("split") or task_data["split"])
        scenario = str(record_data.get("scenario") or task_data["scenario"])
        trial = str(record_data.get("trial") or task_data["trial"])
        task_id = str(record_data.get("task_id") or _task_id(split, scenario, trial, index))
        family = str(record_data.get("family") or _family_from_scenario(scenario))
        instruction = str(record_data.get("instruction") or task_data["instruction"])

        metadata = dict(record_data.get("metadata") or {})
        metadata.setdefault("benchmark", "alfworld")
        metadata.setdefault("alfworld_data", str(self.root))
        metadata.setdefault("problem_path", str(problem_path))
        metadata.setdefault("problem_path_relative", _relative_to_root(problem_path, self.root))
        metadata.setdefault("split", split)
        metadata.setdefault("scenario", scenario)
        metadata.setdefault("trial", trial)
        metadata.setdefault("task_type", family)

        context = dict(record_data.get("context") or {})
        context.setdefault("problem_path", str(problem_path))
        context.setdefault("split", split)
        context.setdefault("scenario", scenario)
        context.setdefault("trial", trial)

        tags = record_data.get("tags") or ["alfworld", split, family]
        if isinstance(tags, str):
            tags = [tags]

        return TaskSpec(
            task_id=task_id,
            family=family,
            instruction=instruction,
            acceptance_criteria=list(
                record_data.get("acceptance_criteria")
                or [
                    "Complete the ALFWorld text-only task.",
                    "The environment should report the episode as won.",
                ]
            ),
            context=context,
            tags=list(tags),
            metadata=metadata,
        )


def _resolve_data_root(root: str | Path | None) -> Path:
    candidates = []
    if root is not None:
        candidates.append(Path(root))
    if os.environ.get("ALFWORLD_DATA"):
        candidates.append(Path(os.environ["ALFWORLD_DATA"]))
    candidates.extend([Path.home() / "alfworld_data", Path.cwd()])
    for candidate in candidates:
        if _looks_like_alfworld_data(candidate):
            return candidate.resolve()
    return candidates[0].resolve()


def _looks_like_alfworld_data(path: Path) -> bool:
    return (path / "json_2.1.1").exists() and (path / "logic" / "alfred.pddl").exists()


def _find_problem_dirs(root: Path, split: str) -> list[Path]:
    split_dir = root / "json_2.1.1" / split
    if not split_dir.exists():
        raise FileNotFoundError(f"ALFWorld split not found: {split_dir}")
    problem_dirs = [path.parent for path in split_dir.glob("*/*/traj_data.json")]
    if not problem_dirs:
        problem_dirs = [path.parent for path in split_dir.rglob("traj_data.json")]
    return sorted(problem_dirs)


def _resolve_problem_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    candidates = [root / path, root / "json_2.1.1" / path]
    for candidate in candidates:
        if (candidate / "traj_data.json").exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _problem_path_from_id(root: Path, task_id: str) -> Path:
    parts = task_id.split("__", 2)
    if len(parts) == 3:
        split, scenario, trial = parts
        return (root / "json_2.1.1" / split / scenario / trial).resolve()
    raise ValueError("ALFWorld manifest record needs problem_path/path when task_id is not split__scenario__trial.")


def _read_public_task_data(problem_path: Path) -> dict[str, str]:
    traj_path = problem_path / "traj_data.json"
    if not traj_path.exists():
        raise FileNotFoundError(f"Missing ALFWorld traj_data.json: {traj_path}")
    payload = json.loads(traj_path.read_text())
    instruction = _instruction_from_traj(payload) or _family_from_scenario(problem_path.parent.name)
    split = problem_path.parent.parent.name
    scenario = problem_path.parent.name
    trial = problem_path.name
    return {
        "instruction": instruction,
        "split": split,
        "scenario": scenario,
        "trial": trial,
    }


def _instruction_from_traj(payload: dict[str, Any]) -> str:
    annotations = payload.get("turk_annotations") or {}
    anns = annotations.get("anns") if isinstance(annotations, dict) else None
    if isinstance(anns, list):
        for ann in anns:
            if isinstance(ann, dict) and ann.get("task_desc"):
                return str(ann["task_desc"])
    for key in ("task_desc", "task_description", "goal_desc"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _task_id(split: str, scenario: str, trial: str, index: int) -> str:
    candidate = f"{split}__{scenario}__{trial}"
    candidate = re.sub(r"[^A-Za-z0-9_.=-]+", "_", candidate)
    return candidate or f"alfworld-{index}"


def _family_from_scenario(scenario: str) -> str:
    return scenario.split("-", 1)[0] if "-" in scenario else scenario


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)
