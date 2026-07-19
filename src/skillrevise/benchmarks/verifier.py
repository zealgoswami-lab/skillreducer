from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from skillrevise.core.env import set_env_with_legacy
from skillrevise.core.models import TaskSpec


@dataclass
class VerifierResult:
    success: bool
    summary: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Verifier(Protocol):
    def verify(self, workspace: Path, task: TaskSpec) -> VerifierResult:
        """Return a deterministic verification result for one task execution."""


class CommandVerifier:
    def __init__(
        self,
        command: str | list[str] | tuple[str, ...] | None = None,
        *,
        timeout_seconds: int = 600,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.env = env or {}

    def verify(self, workspace: Path, task: TaskSpec) -> VerifierResult:
        command = self.command or task.metadata.get("verifier_command")
        if not command:
            return VerifierResult(
                success=False,
                summary="No verifier command configured.",
                exit_code=-1,
            )

        argv = shlex.split(command) if isinstance(command, str) else list(command)
        env = os.environ.copy()
        env.update(self.env)
        set_env_with_legacy(env, "SKILL_REVISE_TASK_ID", task.task_id)
        set_env_with_legacy(env, "SKILL_REVISE_WORKSPACE", str(workspace))

        completed = subprocess.run(
            argv,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=int(task.metadata.get("timeout_seconds", self.timeout_seconds)),
        )
        summary = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else "Verifier finished."
        return VerifierResult(
            success=completed.returncode == 0,
            summary=summary,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
