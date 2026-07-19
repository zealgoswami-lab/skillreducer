from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from skillrevise.core.io import to_jsonable, write_json
from skillrevise.core.models import TaskSpec
from skillrevise.benchmarks.skillsbench import SkillsBenchTaskLoader

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def normalize_tasks(
    input_path: str | Path,
    *,
    workspace_root: str | Path | None = None,
    default_family: str | None = None,
    default_verifier_command: str | None = None,
    default_timeout_seconds: int | None = None,
    strict: bool = False,
) -> list[TaskSpec]:
    source = Path(input_path)
    if source.is_dir():
        tasks = load_skillsbench_task_directories(source)
    else:
        tasks = SkillsBenchTaskLoader(workspace_root).load(input_path)
    normalized = [
        _apply_defaults(
            task,
            default_family=default_family,
            default_verifier_command=default_verifier_command,
            default_timeout_seconds=default_timeout_seconds,
        )
        for task in tasks
    ]
    if strict:
        _validate_tasks(normalized)
    return normalized


def load_skillsbench_task_directories(root: str | Path) -> list[TaskSpec]:
    root_path = Path(root).resolve()
    tasks_root = root_path / "tasks" if (root_path / "tasks").is_dir() else root_path
    task_dirs = sorted(path.parent for path in tasks_root.glob("*/task.toml"))
    if not task_dirs:
        raise ValueError(f"No SkillsBench task directories with task.toml found under {root_path}")
    return [_task_dir_to_spec(task_dir) for task_dir in task_dirs]


def _task_dir_to_spec(task_dir: Path) -> TaskSpec:
    task_toml = _load_toml(task_dir / "task.toml")
    metadata_section = dict(task_toml.get("metadata") or {})
    verifier_section = dict(task_toml.get("verifier") or {})
    agent_section = dict(task_toml.get("agent") or {})
    environment_section = dict(task_toml.get("environment") or {})

    tags = metadata_section.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    category = str(metadata_section.get("category") or (tags[0] if tags else "") or task_dir.name.split("-")[0])

    timeout = _coerce_timeout(
        verifier_section.get("timeout_sec"),
        agent_section.get("timeout_sec"),
    )
    verifier_command = "bash tests/test.sh" if (task_dir / "tests" / "test.sh").exists() else ""
    acceptance = _acceptance_criteria_for_task(task_dir, verifier_command)

    metadata = {
        "repo_path": str(task_dir.resolve()),
        "skillsbench_task_dir": str(task_dir.resolve()),
        "instruction_path": str((task_dir / "instruction.md").resolve()),
        "task_toml_path": str((task_dir / "task.toml").resolve()),
        "verifier_command": verifier_command,
        "timeout_seconds": timeout,
        "skillsbench_version": str(task_toml.get("version", "")),
        "difficulty": metadata_section.get("difficulty"),
        "category": category,
        "environment": environment_section,
    }
    metadata = {key: value for key, value in metadata.items() if value not in (None, "")}

    return TaskSpec(
        task_id=task_dir.name,
        family=category,
        instruction=_read_text(task_dir / "instruction.md"),
        acceptance_criteria=acceptance,
        tags=list(tags),
        metadata=metadata,
    )


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text().strip()


def _coerce_timeout(*values) -> int:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return 600
    return int(max(numeric))


def _acceptance_criteria_for_task(task_dir: Path, verifier_command: str) -> list[str]:
    criteria = ["The task instruction is satisfied in the prepared SkillsBench environment."]
    if verifier_command:
        criteria.append(f"The SkillsBench verifier command succeeds: `{verifier_command}`.")
    if (task_dir / "tests" / "test_outputs.py").exists():
        criteria.append("The generated outputs satisfy `tests/test_outputs.py`.")
    if (task_dir / "tests" / "expected_values.json").exists():
        criteria.append("The generated outputs match `tests/expected_values.json`.")
    if (task_dir / "tests" / "ground_truth.json").exists():
        criteria.append("The generated outputs match `tests/ground_truth.json`.")
    return criteria


def _apply_defaults(
    task: TaskSpec,
    *,
    default_family: str | None,
    default_verifier_command: str | None,
    default_timeout_seconds: int | None,
) -> TaskSpec:
    metadata = dict(task.metadata)
    family = task.family
    if family == "unassigned" and default_family:
        family = default_family
    if default_verifier_command and not metadata.get("verifier_command"):
        metadata["verifier_command"] = default_verifier_command
    if default_timeout_seconds is not None and not metadata.get("timeout_seconds"):
        metadata["timeout_seconds"] = default_timeout_seconds
    return replace(task, family=family, metadata=metadata)


def _validate_tasks(tasks: list[TaskSpec]) -> None:
    errors: list[str] = []
    for task in tasks:
        prefix = f"{task.task_id}: "
        if not task.instruction.strip():
            errors.append(prefix + "missing instruction")
        if not task.family.strip() or task.family == "unassigned":
            errors.append(prefix + "missing family")
        if not task.acceptance_criteria:
            errors.append(prefix + "missing acceptance_criteria")
        if not task.metadata.get("repo_path"):
            errors.append(prefix + "missing metadata.repo_path")
        if not task.metadata.get("verifier_command"):
            errors.append(prefix + "missing metadata.verifier_command")
    if errors:
        joined = "\n".join(f"- {item}" for item in errors)
        raise ValueError(f"Invalid converted manifest:\n{joined}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a SkillsBench-style manifest into SkillRevise TaskSpec JSON.")
    parser.add_argument("input", help="Input SkillsBench-style JSON or JSONL manifest.")
    parser.add_argument("output", help="Output TaskSpec JSON manifest.")
    parser.add_argument("--workspace-root", help="Root used to resolve relative repo_path values.")
    parser.add_argument("--default-family", help="Family to use when a record has no domain/subdomain/family.")
    parser.add_argument("--default-verifier-command", help="Verifier command to use when a record has none.")
    parser.add_argument("--default-timeout-seconds", type=int, help="Timeout to use when a record has none.")
    parser.add_argument("--strict", action="store_true", help="Fail if required experiment fields are missing.")
    args = parser.parse_args()

    tasks = normalize_tasks(
        args.input,
        workspace_root=args.workspace_root,
        default_family=args.default_family,
        default_verifier_command=args.default_verifier_command,
        default_timeout_seconds=args.default_timeout_seconds,
        strict=args.strict,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, {"tasks": [to_jsonable(task) for task in tasks]})
    print(f"Wrote {len(tasks)} converted tasks to {args.output}")


if __name__ == "__main__":
    main()
