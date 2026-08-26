"""Agno agent adapter for pipeline LLM calls."""

from __future__ import annotations

from typing import Any

from skillreducer.llm.json_util import parse_llm_json
from skillreducer.models import LlmUsage

try:
    from agno.agent import Agent
except ImportError:  # pragma: no cover
    Agent = None  # type: ignore[misc, assignment]


class AgnoLLMClient:
    """Expose complete/complete_json so stage modules can call an Agno agent."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent
        self._enabled = True
        self.usage = LlmUsage()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def complete(self, prompt: str, model: str | None = None, system: str | None = None) -> str:
        message = f"{system}\n\n{prompt}" if system else prompt
        run = self._agent.run(message)
        self.usage.absorb(LlmUsage.from_agno_run(run))
        content = run.content
        if content is None:
            return ""
        return content.strip() if isinstance(content, str) else str(content).strip()

    def complete_json(self, prompt: str, model: str | None = None, system: str | None = None) -> Any:
        """Return parsed JSON, or None if the model reply is empty / not JSON."""
        text = self.complete(prompt, model=model, system=system)
        return parse_llm_json(text)
