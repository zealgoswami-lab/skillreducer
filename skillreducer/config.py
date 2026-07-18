from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path.home() / ".config" / "skillreducer" / "config.yaml",
]

# Env / .env field names (only these).
_API_KEY_ENV = ("api_key",)
_API_BASE_URL_ENV = ("api_base_url",)
_AZURE_SUBSCRIPTION_ENV = ("azure_subscription",)
_AZURE_ENDPOINT_ENV = ("azure_endpoint",)
_API_VERSION_ENV = ("api_version", "azure_api_version")
_COMPRESSION_MODEL_ENV = ("compression_model", "compression")
_ROUTING_MODEL_ENV = ("routing_model", "routing_oracle")
_EVALUATION_MODEL_ENV = ("evaluation_model", "evaluation")
_TSCG_ENABLED_ENV = ("tscg_enabled", "tscg")
_TSCG_MODEL_ENV = ("tscg_model",)
_TSCG_PROFILE_ENV = ("tscg_profile",)


_dotenv_loaded = False
_dotenv_keys: set[str] = set()


def _dotenv_search_paths() -> list[Path]:
    """Return .env paths from least to most specific (later may override earlier)."""
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(directory: Path) -> None:
        path = (directory / ".env").resolve()
        if path not in seen:
            seen.add(path)
            ordered.append(path)

    add(Path(__file__).resolve().parents[1])

    cwd = Path.cwd()
    for parent in list(cwd.parents)[::-1]:
        add(parent)
    add(cwd)

    return ordered


def _apply_dotenv_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
            _dotenv_keys.add(key)
        elif key in _dotenv_keys:
            os.environ[key] = value


def load_dotenv(path: Path | None = None, *, force: bool = False) -> None:
    """Load KEY=VALUE pairs from .env into os.environ.

    OS environment variables are never overwritten. Among .env files, later
    search paths override earlier ones (package root → ancestors → cwd).
    """
    global _dotenv_loaded

    if path is not None:
        if path.is_file():
            _apply_dotenv_file(path)
        return

    if _dotenv_loaded and not force:
        return

    _dotenv_keys.clear()
    for candidate in _dotenv_search_paths():
        if candidate.is_file():
            _apply_dotenv_file(candidate)
    _dotenv_loaded = True


def ensure_dotenv_loaded() -> None:
    """Load .env once before reading credentials or model ids."""
    load_dotenv()


def _env_value(*names: str) -> str | None:
    ensure_dotenv_loaded()
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _env_bool(*names: str) -> bool | None:
    value = _env_value(*names)
    if value is None:
        return None
    return value.lower() in ("1", "true", "yes", "on")


def normalize_azure_endpoint(url: str) -> str:
    """Strip OpenAI v1 suffix so AzureOpenAI gets a resource endpoint."""
    endpoint = url.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        endpoint = endpoint[: -len("/openai/v1")]
    return endpoint.rstrip("/") + "/"


def resolve_api_key(config: Config | None = None) -> str | None:
    """Resolve API key: environment variables override config.yaml / Config fields."""
    value = _env_value(*_API_KEY_ENV)
    if value:
        return value
    if config and config.api_key:
        return config.api_key
    return None


def resolve_api_base_url(config: Config | None = None) -> str | None:
    """Resolve API base URL: environment overrides config.yaml (base_url / api_base_url)."""
    value = _env_value(*_API_BASE_URL_ENV)
    if value:
        return value
    if config:
        if config.api_base_url:
            return config.api_base_url
        if config.base_url:
            return config.base_url
    return None


def resolve_compression_model(config: Config | None = None) -> str:
    """Resolve compression model id: environment overrides config.yaml."""
    value = _env_value(*_COMPRESSION_MODEL_ENV)
    if value:
        return value
    if config:
        return config.compression_model
    return Config.compression_model


def resolve_routing_model(config: Config | None = None) -> str:
    """Resolve routing oracle model id: environment overrides config.yaml."""
    value = _env_value(*_ROUTING_MODEL_ENV)
    if value:
        return value
    if config:
        return config.routing_model
    return Config.routing_model


def resolve_evaluation_model(config: Config | None = None) -> str:
    """Resolve evaluation model id: environment overrides config.yaml."""
    value = _env_value(*_EVALUATION_MODEL_ENV)
    if value:
        return value
    if config:
        return config.evaluation_model
    return Config.evaluation_model


def resolve_azure_subscription(config: Config | None = None) -> bool:
    """Resolve Azure mode: environment overrides config.yaml."""
    value = _env_bool(*_AZURE_SUBSCRIPTION_ENV)
    if value is not None:
        return value
    if config:
        return config.azure_subscription
    return False


def resolve_azure_endpoint(config: Config | None = None) -> str | None:
    """Resolve Azure resource endpoint: env azure_endpoint, then api_base_url."""
    value = _env_value(*_AZURE_ENDPOINT_ENV)
    if value:
        return normalize_azure_endpoint(value)
    if config and config.azure_endpoint:
        return normalize_azure_endpoint(config.azure_endpoint)
    base_url = resolve_api_base_url(config)
    if base_url:
        return normalize_azure_endpoint(base_url)
    return None


def resolve_api_version(config: Config | None = None) -> str:
    """Resolve Azure API version: environment overrides config.yaml."""
    value = _env_value(*_API_VERSION_ENV)
    if value:
        return value
    if config and config.api_version:
        return config.api_version
    return Config.api_version


@dataclass
class Config:
    compression_model: str = "gpt-4o-mini"
    routing_model: str = "gpt-4o-mini"
    evaluation_model: str = "gpt-4o-mini"
    api_key: str | None = None
    api_base_url: str | None = None
    base_url: str | None = None  # alias for api_base_url (config.yaml compatibility)
    azure_subscription: bool = False
    azure_endpoint: str | None = None
    api_version: str = "2024-10-21"
    short_description_tokens: int = 40
    min_reference_tokens: int = 30
    min_script_tokens: int = 20
    max_feedback_iterations: int = 2
    max_restore_steps: int = 3
    num_test_queries: int = 8
    num_distractors: int = 4
    include_adversarial: bool = True
    use_llm: bool = True
    tscg_enabled: bool = False
    tscg_model: str = "claude-sonnet"
    tscg_profile: str = "balanced"

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from yaml (optional), then apply env overrides."""
        ensure_dotenv_loaded()
        candidates = [path] if path else DEFAULT_CONFIG_PATHS
        data: dict = {}
        for candidate in candidates:
            if candidate and candidate.exists():
                loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                models = loaded.get("models", {})
                thresholds = loaded.get("thresholds", {})
                oracle = loaded.get("oracle", {})
                tscg = loaded.get("tscg", {})
                api_base = loaded.get("api_base_url") or loaded.get("base_url")
                data = {
                    "compression_model": models.get("compression", cls.compression_model),
                    "routing_model": models.get("routing_oracle", cls.routing_model),
                    "evaluation_model": models.get("evaluation", cls.evaluation_model),
                    "api_key": loaded.get("api_key"),
                    "api_base_url": api_base,
                    "base_url": api_base,
                    "azure_subscription": bool(loaded.get("azure_subscription", False)),
                    "azure_endpoint": loaded.get("azure_endpoint"),
                    "api_version": loaded.get("api_version", cls.api_version),
                    "short_description_tokens": thresholds.get(
                        "short_description_tokens", cls.short_description_tokens
                    ),
                    "min_reference_tokens": thresholds.get(
                        "min_reference_tokens", cls.min_reference_tokens
                    ),
                    "min_script_tokens": thresholds.get(
                        "min_script_tokens", cls.min_script_tokens
                    ),
                    "max_feedback_iterations": thresholds.get(
                        "max_feedback_iterations", cls.max_feedback_iterations
                    ),
                    "max_restore_steps": thresholds.get(
                        "max_restore_steps", cls.max_restore_steps
                    ),
                    "num_test_queries": oracle.get("num_test_queries", cls.num_test_queries),
                    "num_distractors": oracle.get("num_distractors", cls.num_distractors),
                    "include_adversarial": oracle.get("include_adversarial", cls.include_adversarial),
                    "use_llm": loaded.get("use_llm", True),
                    "tscg_enabled": bool(tscg.get("enabled", cls.tscg_enabled)),
                    "tscg_model": tscg.get("model", cls.tscg_model),
                    "tscg_profile": tscg.get("profile", cls.tscg_profile),
                }
                break

        config = cls(**data)
        # Environment overrides yaml.
        env_key = _env_value(*_API_KEY_ENV)
        if env_key:
            config.api_key = env_key

        env_base = _env_value(*_API_BASE_URL_ENV)
        if env_base:
            config.api_base_url = env_base
            config.base_url = env_base
        elif config.api_base_url and not config.base_url:
            config.base_url = config.api_base_url
        elif config.base_url and not config.api_base_url:
            config.api_base_url = config.base_url

        env_compression = _env_value(*_COMPRESSION_MODEL_ENV)
        if env_compression:
            config.compression_model = env_compression

        env_routing = _env_value(*_ROUTING_MODEL_ENV)
        if env_routing:
            config.routing_model = env_routing

        env_evaluation = _env_value(*_EVALUATION_MODEL_ENV)
        if env_evaluation:
            config.evaluation_model = env_evaluation

        env_azure = _env_bool(*_AZURE_SUBSCRIPTION_ENV)
        if env_azure is not None:
            config.azure_subscription = env_azure

        env_azure_endpoint = _env_value(*_AZURE_ENDPOINT_ENV)
        if env_azure_endpoint:
            config.azure_endpoint = normalize_azure_endpoint(env_azure_endpoint)

        env_api_version = _env_value(*_API_VERSION_ENV)
        if env_api_version:
            config.api_version = env_api_version

        env_tscg = _env_bool(*_TSCG_ENABLED_ENV)
        if env_tscg is not None:
            config.tscg_enabled = env_tscg

        env_tscg_model = _env_value(*_TSCG_MODEL_ENV)
        if env_tscg_model:
            config.tscg_model = env_tscg_model

        env_tscg_profile = _env_value(*_TSCG_PROFILE_ENV)
        if env_tscg_profile:
            config.tscg_profile = env_tscg_profile

        return config
