from __future__ import annotations

import re

from skillrevise.core.models import Skill


SECTION_ALIASES = {
    "skill name": "name",
    "name": "name",
    "purpose": "purpose",
    "when to use": "when_to_use",
    "when_to_use": "when_to_use",
    "procedure": "procedure",
    "steps": "procedure",
    "constraints": "constraints",
    "constraints / pitfalls": "constraints",
    "constraints/pitfalls": "constraints",
    "pitfalls": "constraints",
}


def parse_skill_markdown(
    text: str,
    *,
    default_name: str,
    version: str = "v0",
    metadata: dict[str, object] | None = None,
) -> Skill:
    cleaned = _strip_outer_fence(text)
    sections = _collect_sections(cleaned)

    name = _section_text(sections, "name") or _first_h1(cleaned) or default_name
    purpose = _section_text(sections, "purpose")
    when_to_use = _section_text(sections, "when_to_use")
    procedure = _section_list(sections, "procedure")
    constraints = _section_list(sections, "constraints")

    if not purpose or not when_to_use or not procedure or not constraints:
        missing = [
            label
            for label, value in (
                ("Purpose", purpose),
                ("When to Use", when_to_use),
                ("Procedure", procedure),
                ("Constraints / Pitfalls", constraints),
            )
            if not value
        ]
        raise ValueError(f"LLM skill output is missing required section(s): {', '.join(missing)}")

    return Skill(
        name=name.strip(),
        purpose=purpose.strip(),
        when_to_use=when_to_use.strip(),
        procedure=procedure,
        constraints=constraints,
        version=version,
        metadata=dict(metadata or {}),
    )


def _strip_outer_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def _collect_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = _parse_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        key_value = _parse_key_value(line)
        if key_value:
            key, value = key_value
            sections.setdefault(key, []).append(value)
            current = key
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_heading(line: str) -> str | None:
    match = re.match(r"^\s{0,3}#{1,4}\s+(.+?)\s*$", line)
    if not match:
        return None
    title = _normalize_title(match.group(1))
    return SECTION_ALIASES.get(title)


def _parse_key_value(line: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(?:\*\*)?([A-Za-z][A-Za-z _/-]+?)(?:\*\*)?\s*:\s*(.*?)\s*$", line)
    if not match:
        return None
    key = SECTION_ALIASES.get(_normalize_title(match.group(1)))
    if not key:
        return None
    return key, match.group(2).strip()


def _normalize_title(title: str) -> str:
    title = re.sub(r"[*_`#]", "", title)
    title = re.sub(r"\s+", " ", title).strip().lower()
    return title


def _section_text(sections: dict[str, list[str]], key: str) -> str:
    lines = [line.strip() for line in sections.get(key, []) if line.strip()]
    return " ".join(_strip_bullet(line) for line in lines).strip()


def _section_list(sections: dict[str, list[str]], key: str) -> list[str]:
    items: list[str] = []
    for line in sections.get(key, []):
        clean = line.strip()
        if not clean:
            continue
        if _looks_like_numbered_item(clean) or clean.startswith(("-", "*")):
            items.append(_strip_bullet(clean))
        elif items:
            items[-1] = f"{items[-1]} {clean}"
        else:
            items.append(clean)
    return [item for item in items if item]


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()


def _looks_like_numbered_item(line: str) -> bool:
    return bool(re.match(r"^\d+[.)]\s+", line))


def _first_h1(text: str) -> str | None:
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#\s+(.+?)\s*$", line)
        if match:
            title = match.group(1).strip()
            if _normalize_title(title) not in SECTION_ALIASES:
                return title
    return None
