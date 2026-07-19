from __future__ import annotations

from collections.abc import Mapping, MutableMapping


NEW_ENV_PREFIX = "SKILL_REVISE_"
LEGACY_ENV_PREFIX = "SKILL_HARNESS_"


def legacy_env_name(name: str) -> str:
    if name.startswith(NEW_ENV_PREFIX):
        return LEGACY_ENV_PREFIX + name[len(NEW_ENV_PREFIX) :]
    return name


def env_names(name: str) -> tuple[str, ...]:
    legacy = legacy_env_name(name)
    return (name,) if legacy == name else (name, legacy)


def get_env(env: Mapping[str, str], name: str, default: str | None = None) -> str | None:
    for candidate in env_names(name):
        value = env.get(candidate)
        if value not in {None, ""}:
            return str(value)
    return default


def set_env_with_legacy(env: MutableMapping[str, str], name: str, value: str) -> None:
    env[name] = value
    legacy = legacy_env_name(name)
    if legacy != name:
        env.setdefault(legacy, value)


def env_flag_enabled(env: Mapping[str, str], name: str) -> bool:
    return str(get_env(env, name, "") or "").lower() in {"1", "true", "yes", "on"}
