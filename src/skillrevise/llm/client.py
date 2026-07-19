from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Protocol

from skillrevise.core.env import env_flag_enabled, set_env_with_legacy


PROXY_ENV_KEYS = {
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
class LLMResponse:
    text: str
    latency_seconds: float
    metadata: dict[str, object] = field(default_factory=dict)


class LLMClient(Protocol):
    def complete(self, prompt: str, *, purpose: str) -> LLMResponse:
        """Return a completion for one SkillRevise prompt."""


class CommandLLMClient:
    """Runs an external LLM command that reads the prompt from stdin.

    This keeps SkillRevise independent from OpenAI, Anthropic, local models, or any
    specific SDK. The command should write the final model response to stdout.
    """

    def __init__(
        self,
        command: str | list[str] | tuple[str, ...],
        *,
        timeout_seconds: int = 600,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.env = env or {}

    def complete(self, prompt: str, *, purpose: str) -> LLMResponse:
        argv = shlex.split(self.command) if isinstance(self.command, str) else list(self.command)
        env = os.environ.copy()
        env.update(self.env)
        if _bypass_proxy_enabled(env):
            env = _without_proxy_env(env)
        set_env_with_legacy(env, "SKILL_REVISE_REVISION_LLM_PURPOSE", purpose)

        started = time.perf_counter()
        completed = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
            timeout=self.timeout_seconds,
        )
        latency = round(time.perf_counter() - started, 4)
        if completed.returncode != 0:
            raise RuntimeError(
                f"LLM command failed for {purpose} with exit code {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        return LLMResponse(
            text=completed.stdout.strip(),
            latency_seconds=latency,
            metadata={"command": argv[0], "purpose": purpose, "stderr": completed.stderr.strip()},
        )


class StaticLLMClient:
    """Deterministic test double for LLM-backed components."""

    def __init__(self, responses: list[str] | tuple[str, ...]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def complete(self, prompt: str, *, purpose: str) -> LLMResponse:
        self.calls.append({"purpose": purpose, "prompt": prompt})
        if not self.responses:
            raise RuntimeError(f"No static LLM response left for {purpose}")
        return LLMResponse(text=self.responses.pop(0), latency_seconds=0.0, metadata={"purpose": purpose})


def _bypass_proxy_enabled(env: dict[str, str]) -> bool:
    return env_flag_enabled(env, "SKILL_REVISE_BYPASS_PROXY") or env_flag_enabled(env, "SKILL_REVISE_NO_PROXY")


def _without_proxy_env(env: dict[str, str]) -> dict[str, str]:
    cleaned = {key: value for key, value in env.items() if key not in PROXY_ENV_KEYS}
    set_env_with_legacy(cleaned, "SKILL_REVISE_BYPASS_PROXY", "1")
    return cleaned
