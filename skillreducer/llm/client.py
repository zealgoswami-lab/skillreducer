from __future__ import annotations

from typing import Any

from openai import AzureOpenAI, OpenAI

from skillreducer.config import (
    Config,
    resolve_api_base_url,
    resolve_api_key,
    resolve_api_version,
    resolve_azure_endpoint,
    resolve_azure_subscription,
    resolve_compression_model,
)
from skillreducer.llm.json_util import parse_llm_json
from skillreducer.models import LlmUsage


class LLMClient:
    def __init__(self, config: Config) -> None:
        api_key = resolve_api_key(config)
        if not api_key:
            self._client = None
            self._enabled = False
        elif resolve_azure_subscription(config):
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "api_version": resolve_api_version(config),
            }
            endpoint = resolve_azure_endpoint(config)
            if endpoint:
                kwargs["azure_endpoint"] = endpoint
            self._client = AzureOpenAI(**kwargs)
            self._enabled = config.use_llm
        else:
            kwargs = {"api_key": api_key}
            base_url = resolve_api_base_url(config)
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
            self._enabled = config.use_llm
        self._config = config
        self.usage = LlmUsage()

    @property
    def enabled(self) -> bool:
        return bool(self._client and self._enabled)

    def complete(self, prompt: str, model: str | None = None, system: str | None = None) -> str:
        if not self.enabled:
            raise RuntimeError(
                "LLM client is not configured. Set api_key in the environment, .env, or config.yaml."
            )
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=model or resolve_compression_model(self._config),
            messages=messages,
            temperature=0,
        )
        self.usage.absorb(LlmUsage.from_openai_response(response))
        return (response.choices[0].message.content or "").strip()

    def complete_json(self, prompt: str, model: str | None = None, system: str | None = None) -> Any:
        """Return parsed JSON, or None if the model reply is empty / not JSON."""
        text = self.complete(prompt, model=model, system=system)
        return parse_llm_json(text)
