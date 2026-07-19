from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

SelectionNormalizer = Callable[[Any], str]


def normalize_task_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("task_id", "id", "name"):
            if value.get(key):
                return normalize_task_id(value[key])
        raise ValueError(f"Selection item has no task id field: {value}")
    task_id = str(value).strip()
    if not task_id:
        raise ValueError("Selection item is empty.")
    return task_id


def normalize_swe_task_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("task_id", "id", "name"):
            if value.get(key):
                return normalize_swe_task_id(value[key])
        metadata = value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {}
        batch = (
            value.get("batch")
            or value.get("source_batch")
            or metadata.get("source_batch")
        )
        skill_id = (
            value.get("skill_id")
            or value.get("source_skill_id")
            or metadata.get("source_skill_id")
        )
        if batch and skill_id:
            return f"swe-{batch}-{skill_id}".lower()
        raise ValueError(f"SWE selection item has no task id or batch/skill fields: {value}")

    text = str(value).strip()
    if not text:
        raise ValueError("Selection item is empty.")
    if "/" in text and not text.lower().startswith("swe-"):
        batch, skill_id = text.split("/", 1)
        batch = batch.strip()
        skill_id = skill_id.strip()
        if not batch or not skill_id:
            raise ValueError(f"Invalid SWE selection entry: {text}")
        return f"swe-{batch}-{skill_id}".lower()
    return text.lower()


def read_selection(path: Path, *, normalizer: SelectionNormalizer = normalize_task_id) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if path.suffix.lower() == ".json" or stripped.startswith(("[", "{")):
        payload = json.loads(raw)
        ids = [normalizer(item) for item in _selection_items(payload)]
    else:
        ids = [
            normalizer(line.strip())
            for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    return _dedupe(ids)


def select_tasks(
    *,
    manifest_path: Path,
    jobs_path: Path,
    selection_path: Path,
    tasks_output: Path,
    jobs_output: Path,
    benchmark_name: str,
    selection_name: str,
    normalizer: SelectionNormalizer = normalize_task_id,
    allow_missing: bool = False,
) -> dict[str, Any]:
    selected_ids = read_selection(selection_path, normalizer=normalizer)
    manifest = _read_json(manifest_path)
    source_tasks = _manifest_tasks(manifest, manifest_path)
    source_jobs = _jobs(_read_json(jobs_path), jobs_path)

    tasks_by_id = {normalize_task_id(task): task for task in source_tasks}
    jobs_by_id = {normalize_task_id(job): job for job in source_jobs}

    missing_tasks = [task_id for task_id in selected_ids if task_id not in tasks_by_id]
    missing_jobs = [task_id for task_id in selected_ids if task_id not in jobs_by_id]
    if (missing_tasks or missing_jobs) and not allow_missing:
        raise ValueError(
            json.dumps(
                {"missing_tasks": missing_tasks, "missing_jobs": missing_jobs},
                indent=2,
                sort_keys=True,
            )
        )

    kept_ids = [
        task_id
        for task_id in selected_ids
        if task_id in tasks_by_id and task_id in jobs_by_id
    ]
    selected_tasks = [tasks_by_id[task_id] for task_id in kept_ids]
    selected_jobs = [jobs_by_id[task_id] for task_id in kept_ids]

    output_manifest = _selected_manifest(
        manifest,
        benchmark_name=benchmark_name,
        selection_name=selection_name,
        selection_path=selection_path,
        selected_ids=kept_ids,
        tasks=selected_tasks,
    )
    tasks_output.parent.mkdir(parents=True, exist_ok=True)
    jobs_output.parent.mkdir(parents=True, exist_ok=True)
    tasks_output.write_text(json.dumps(output_manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    jobs_output.write_text(json.dumps(selected_jobs, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return {
        "selection": selection_name,
        "selection_path": str(selection_path),
        "tasks_output": str(tasks_output),
        "jobs_output": str(jobs_output),
        "num_selected": len(selected_ids),
        "num_tasks": len(selected_tasks),
        "num_jobs": len(selected_jobs),
        "missing_tasks": missing_tasks,
        "missing_jobs": missing_jobs,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _selection_items(payload: Any) -> Sequence[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("task_ids", "selected_task_ids", "tasks", "selection"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if any(key in payload for key in ("task_id", "id", "name", "batch", "source_batch")):
            return [payload]
    raise ValueError("Selection JSON must be a list, a task manifest, or contain task_ids.")


def _manifest_tasks(manifest: Any, path: Path) -> list[Mapping[str, Any]]:
    if isinstance(manifest, list):
        tasks = manifest
    elif isinstance(manifest, Mapping) and isinstance(manifest.get("tasks"), list):
        tasks = manifest["tasks"]
    else:
        raise ValueError(f"Expected manifest with a tasks list: {path}")
    if not all(isinstance(task, Mapping) for task in tasks):
        raise ValueError(f"Manifest contains non-object tasks: {path}")
    return list(tasks)


def _jobs(payload: Any, path: Path) -> list[Mapping[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(job, Mapping) for job in payload):
        raise ValueError(f"Expected jobs JSON list: {path}")
    return list(payload)


def _selected_manifest(
    manifest: Any,
    *,
    benchmark_name: str,
    selection_name: str,
    selection_path: Path,
    selected_ids: list[str],
    tasks: list[Mapping[str, Any]],
) -> dict[str, Any]:
    base = dict(manifest) if isinstance(manifest, Mapping) else {}
    base.pop("tasks", None)
    base["benchmark"] = benchmark_name
    base["count"] = len(tasks)
    base["selection"] = {
        "name": selection_name,
        "source": str(selection_path),
        "task_ids": selected_ids,
    }
    base["tasks"] = tasks
    return base


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    duplicates: list[str] = []
    for task_id in ids:
        if task_id in seen:
            duplicates.append(task_id)
            continue
        seen.add(task_id)
        result.append(task_id)
    if duplicates:
        raise ValueError(f"Duplicate selected task ids: {', '.join(duplicates)}")
    if not result:
        raise ValueError("Selection is empty.")
    return result
