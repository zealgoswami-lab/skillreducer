from __future__ import annotations

import re
from pathlib import Path

import yaml

from skillreducer.models import ReferenceFile, Skill
from skillreducer.tokenizer import count_tokens

SKILL_FILENAMES = ("SKILL.md", "skill.md")
REFERENCE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml"}
SKIP_DIRS = {"scripts", "__pycache__", ".git", "node_modules", "skillreducer_results"}


def resolve_skill_md(path: Path) -> Path:
    """Resolve the main skill file (SKILL.md or skill.md) for a skill directory."""
    path = path.resolve()
    if path.is_file():
        if path.name.lower() == "skill.md":
            return path
        return path / SKILL_FILENAMES[0]
    for name in SKILL_FILENAMES:
        candidate = path / name
        if candidate.exists():
            return candidate
    return path / SKILL_FILENAMES[0]


def parse_skill_md(path: Path) -> Skill:
    path = resolve_skill_md(path)
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found at {path} (expected SKILL.md or skill.md)")

    raw = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw)
    name = str(frontmatter.get("name", path.parent.name))
    description = str(frontmatter.get("description", "")).strip()
    references = _load_references(path.parent)

    return Skill(
        path=path,
        name=name,
        description=description,
        body=body.strip(),
        frontmatter=frontmatter,
        references=references,
    )


def write_skill_md(
    path: Path,
    frontmatter: dict,
    body: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _dump_frontmatter(frontmatter)
    content = f"{serialized}\n{body.strip()}\n" if body.strip() else f"{serialized}\n"
    path.write_text(content, encoding="utf-8")


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
    if not match:
        return {}, raw
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = raw[match.end() :]
    return frontmatter, body


def _dump_frontmatter(frontmatter: dict) -> str:
    dumped = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---"


def _load_references(skill_dir: Path) -> list[ReferenceFile]:
    refs: list[ReferenceFile] = []
    for child in sorted(skill_dir.iterdir()):
        if not child.is_file():
            continue
        if child.name.lower() == "skill.md":
            continue
        if child.suffix.lower() not in REFERENCE_EXTENSIONS:
            continue
        content = child.read_text(encoding="utf-8")
        refs.append(
            ReferenceFile(
                path=child,
                content=content,
                token_count=count_tokens(content),
            )
        )
    return refs


def find_skill_paths(root: Path, recursive: bool) -> list[Path]:
    root = root.resolve()
    if root.is_file() and root.name.lower() == "skill.md":
        return [root.parent]
    if resolve_skill_md(root).exists():
        return [root]

    paths: list[Path] = []
    skill_names = {n.lower() for n in SKILL_FILENAMES}
    if recursive:
        for skill_md in root.rglob("*"):
            if skill_md.is_file() and skill_md.name.lower() in skill_names:
                if any(part in SKIP_DIRS for part in skill_md.parts):
                    continue
                paths.append(skill_md.parent)
    else:
        for child in root.iterdir():
            if child.is_dir() and resolve_skill_md(child).exists():
                paths.append(child)
    return sorted(set(paths))
