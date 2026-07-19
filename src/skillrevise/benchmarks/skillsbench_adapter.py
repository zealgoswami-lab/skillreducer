from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from skillrevise.core.agents import AgentAdapter
from skillrevise.core.artifacts import ArtifactStore
from skillrevise.core.env import env_flag_enabled, get_env, set_env_with_legacy
from skillrevise.core.models import ExecutionTrace, Skill, TaskSpec, TrajectoryEvent
from skillrevise.benchmarks.verifier import CommandVerifier, Verifier, VerifierResult


_PROXY_ENV_KEYS = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}


@dataclass
class HarnessExecution:
    status: str
    tokens: int
    tool_calls: int
    steps: int
    latency_seconds: float
    outcome_summary: str
    events: list[TrajectoryEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""


class AgentHarness(Protocol):
    def execute(
        self,
        task: TaskSpec,
        workspace: Path,
        skill_path: Path | None,
        run_dir: Path,
    ) -> HarnessExecution:
        """Execute one task inside a prepared workspace."""


class CommandAgentHarness:
    """Runs an external harness command and optionally consumes a JSON trace file.

    The external process can read these environment variables:
    - SKILL_REVISE_TASK_ID
    - SKILL_REVISE_WORKSPACE
    - SKILL_REVISE_SKILL_PATH
    - SKILL_REVISE_TRACE_PATH
    - SKILL_REVISE_INSTRUCTION
    """

    def __init__(
        self,
        command: str | list[str] | tuple[str, ...],
        *,
        timeout_seconds: int = 3_600,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.env = env or {}

    def execute(
        self,
        task: TaskSpec,
        workspace: Path,
        skill_path: Path | None,
        run_dir: Path,
    ) -> HarnessExecution:
        trace_path = run_dir / "harness_trace.json"
        argv = shlex.split(self.command) if isinstance(self.command, str) else list(self.command)
        env = os.environ.copy()
        env.update(self.env)
        if _bypass_proxy_enabled(env):
            env = _without_proxy_env(env)
        set_env_with_legacy(env, "SKILL_REVISE_TASK_ID", task.task_id)
        set_env_with_legacy(env, "SKILL_REVISE_WORKSPACE", str(workspace))
        set_env_with_legacy(env, "SKILL_REVISE_TRACE_PATH", str(trace_path))
        set_env_with_legacy(env, "SKILL_REVISE_INSTRUCTION", task.instruction)
        set_env_with_legacy(env, "SKILL_REVISE_SKILL_PATH", "" if skill_path is None else str(skill_path))
        timeout_seconds = int(task.metadata.get("timeout_seconds", self.timeout_seconds))
        if get_env(env, "SKILL_REVISE_TIMEOUT") is None:
            set_env_with_legacy(env, "SKILL_REVISE_TIMEOUT", str(timeout_seconds))
        outer_timeout = (
            timeout_seconds
            + int(get_env(env, "SKILL_REVISE_TIMEOUT_GRACE_SECONDS", "900") or "900")
            + int(get_env(env, "SKILL_REVISE_OUTER_TIMEOUT_EXTRA_SECONDS", "300") or "300")
        )

        start = time.perf_counter()
        timed_out = False
        stdout = ""
        stderr = ""
        returncode = 0
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=outer_timeout,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _coerce_timeout_output(exc.stdout)
            stderr = _coerce_timeout_output(exc.stderr)
            returncode = 124
        latency = round(time.perf_counter() - start, 4)

        trace_payload: dict[str, Any] = {}
        if trace_path.exists():
            trace_payload = json.loads(trace_path.read_text())

        events = self._coerce_events(trace_payload.get("events", []))
        outcome_summary = trace_payload.get("outcome_summary")
        if not outcome_summary:
            if timed_out:
                output_tail = _last_nonempty_line(stdout) or _last_nonempty_line(stderr)
                outcome_summary = f"Harness timed out after {outer_timeout} seconds."
                if output_tail:
                    outcome_summary += f" Last output: {output_tail}"
            else:
                outcome_summary = _last_nonempty_line(stdout) or "Harness finished."
        metadata = dict(trace_payload.get("metadata", {}))
        if timed_out:
            metadata.update({"timed_out": True, "outer_timeout_seconds": outer_timeout})

        return HarnessExecution(
            status="timeout" if timed_out else "success" if returncode == 0 else "failure",
            tokens=int(trace_payload.get("tokens", 0)),
            tool_calls=int(trace_payload.get("tool_calls", 0)),
            steps=int(trace_payload.get("steps", len(events))),
            latency_seconds=float(trace_payload.get("latency_seconds", latency)),
            outcome_summary=outcome_summary,
            events=events,
            metadata=metadata,
            stdout=stdout,
            stderr=stderr,
        )

    def _coerce_events(self, payload: list[dict[str, Any]]) -> list[TrajectoryEvent]:
        events: list[TrajectoryEvent] = []
        for index, item in enumerate(payload, start=1):
            events.append(
                TrajectoryEvent(
                    step_index=int(item.get("step_index", index)),
                    kind=str(item.get("kind", "event")),
                    summary=str(item.get("summary", "")),
                    evidence=str(item.get("evidence", "")),
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return events


def _bypass_proxy_enabled(env: dict[str, str]) -> bool:
    return env_flag_enabled(env, "SKILL_REVISE_BYPASS_PROXY") or env_flag_enabled(env, "SKILL_REVISE_NO_PROXY")


def _without_proxy_env(env: dict[str, str]) -> dict[str, str]:
    cleaned = {key: value for key, value in env.items() if key not in _PROXY_ENV_KEYS}
    set_env_with_legacy(cleaned, "SKILL_REVISE_BYPASS_PROXY", "1")
    return cleaned


def _coerce_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _last_nonempty_line(value: str) -> str:
    for line in reversed(value.strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


class SkillsBenchAgentAdapter(AgentAdapter):
    """Real benchmark adapter shell.

    This class handles workspace materialization, optional skill injection, external harness
    execution, deterministic verification, and artifact writing.
    """

    def __init__(
        self,
        *,
        harness: AgentHarness,
        artifact_store: ArtifactStore | None = None,
        verifier: Verifier | None = None,
        copy_workspace: bool = True,
        disable_verifier: bool = False,
    ) -> None:
        self.harness = harness
        self.artifact_store = artifact_store
        self.verifier = verifier
        self.copy_workspace = copy_workspace
        self.disable_verifier = disable_verifier

    def run(self, task: TaskSpec, skill: Skill | None) -> ExecutionTrace:
        label = "no-skill" if skill is None else skill.version
        run_dir = self._create_run_dir(task, label)
        workspace = self._prepare_workspace(task, run_dir)
        if self.artifact_store:
            self.artifact_store.write_task(task, run_dir)
        skill_path = None
        if skill is not None and self.artifact_store is not None:
            skill_path = self.artifact_store.write_skill(skill, run_dir)
        elif skill is not None:
            skill_path = run_dir / f"skill_{skill.version}.md"
            skill_path.write_text(skill.as_markdown())

        execution = self.harness.execute(task, workspace, skill_path, run_dir)
        verifier = (
            None
            if self.disable_verifier or self._harness_already_verified(execution)
            else self.verifier or self._build_verifier(task)
        )
        verifier_result = verifier.verify(workspace, task) if verifier is not None else None

        events = list(execution.events)
        if verifier_result is not None:
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="verifier",
                    summary=verifier_result.summary,
                    evidence=verifier_result.stderr.strip(),
                    metadata={"exit_code": verifier_result.exit_code},
                )
            )

        trace = ExecutionTrace(
            run_id=run_dir.name,
            task_id=task.task_id,
            skill_version=None if skill is None else skill.version,
            success=execution.status == "success" if verifier_result is None else verifier_result.success,
            status=execution.status,
            started_at=run_dir.name.split("-")[0] if "-" in run_dir.name else run_dir.name,
            ended_at=run_dir.name.split("-")[0] if "-" in run_dir.name else run_dir.name,
            tokens=execution.tokens,
            tool_calls=execution.tool_calls,
            steps=execution.steps,
            latency_seconds=execution.latency_seconds,
            outcome_summary=execution.outcome_summary if verifier_result is None else verifier_result.summary,
            events=events,
            metadata={
                "workspace": str(workspace),
                "harness_stdout_path": str(run_dir / "harness_stdout.txt"),
                "harness_stderr_path": str(run_dir / "harness_stderr.txt"),
                "verifier": None
                if verifier_result is None
                else {"exit_code": verifier_result.exit_code, "success": verifier_result.success},
                **execution.metadata,
            },
        )

        if self.artifact_store:
            self.artifact_store.write_text("harness_stdout.txt", execution.stdout, run_dir)
            self.artifact_store.write_text("harness_stderr.txt", execution.stderr, run_dir)
            if verifier_result is not None:
                self.artifact_store.write_json(
                    "verifier_result.json",
                    {
                        "success": verifier_result.success,
                        "summary": verifier_result.summary,
                        "exit_code": verifier_result.exit_code,
                        "stdout": verifier_result.stdout,
                        "stderr": verifier_result.stderr,
                        "metadata": verifier_result.metadata,
                    },
                    run_dir,
                )
            self.artifact_store.write_trace(trace, run_dir)
        return trace

    def _create_run_dir(self, task: TaskSpec, label: str) -> Path:
        if self.artifact_store is not None:
            return self.artifact_store.start_run(task.task_id, label)
        safe_task_id = task.task_id.replace("/", "-").replace("\\", "-")
        return Path(tempfile.mkdtemp(prefix=f"{safe_task_id}-{label}-"))

    def _prepare_workspace(self, task: TaskSpec, run_dir: Path) -> Path:
        source_path = self._resolve_repo_path(task)
        workspace = run_dir / "workspace"
        if source_path is None:
            workspace.mkdir(parents=True, exist_ok=True)
            return workspace

        if self.copy_workspace:
            shutil.copytree(
                source_path,
                workspace,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".mypy_cache"),
            )
        else:
            workspace = source_path

        commit = task.metadata.get("commit")
        if commit and (workspace / ".git").exists():
            subprocess.run(
                ["git", "checkout", "--detach", str(commit)],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
            )
        return workspace

    def _resolve_repo_path(self, task: TaskSpec) -> Path | None:
        candidate = task.metadata.get("repo_path") or task.context.get("repo_path")
        if not candidate:
            return None
        return Path(candidate).resolve()

    def _build_verifier(self, task: TaskSpec) -> Verifier | None:
        if task.metadata.get("verifier_command"):
            return CommandVerifier()
        return None

    def _harness_already_verified(self, execution: HarnessExecution) -> bool:
        return "reward" in execution.metadata or bool(execution.metadata.get("result_path"))
