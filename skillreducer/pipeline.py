from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from skillreducer.audit import audit_skill
from skillreducer.config import Config
from skillreducer.llm.client import LLMClient
from skillreducer.models import ReduceReport, TokenStats, TscgStats
from skillreducer.parser import parse_skill_md, write_skill_md
from skillreducer.stage1.compress import compress_description
from skillreducer.stage1.agent import Stage1RoutingAgent
from skillreducer.stage1.generate import generate_description
from skillreducer.stage1.oracle import build_stage1_oracle, load_skill_library
from skillreducer.stage2.disclose import (
    deduplicate_existing_references,
    restructure_body,
    write_reference_file,
)
from skillreducer.stage3.extract import extract_scripts_from_markdown
from skillreducer.tokenizer import count_tokens
from skillreducer.tscg import (
    TscgError,
    compress_tools,
    find_existing_manifest,
    load_tools_json,
    tools_from_scripts,
    write_mcp_manifest,
    write_tscg_outputs,
)


def reduce_skill(
    path: Path,
    output_dir: Path,
    config: Config | None = None,
    stage: int | None = None,
    dry_run: bool = False,
    llm: Any | None = None,
    stage1_agent: Stage1RoutingAgent | None = None,
    *,
    tscg: bool | None = None,
    tools_path: Path | None = None,
) -> ReduceReport:
    config = config or Config.load()

    skill = parse_skill_md(path)
    llm_client = llm if llm is not None else LLMClient(config)
    original = audit_skill(path, config)
    notes: list[str] = []

    description = skill.description
    body = skill.body
    new_references: dict[str, str] = {}
    extracted_scripts: dict[str, str] = {}

    run_stage1 = stage in (None, 1)
    run_stage2 = stage in (None, 2)
    run_stage3 = stage in (None, 3)

    if run_stage1:
        skill_library = load_skill_library(skill)
        if stage1_agent is not None:
            stage1_result = stage1_agent.run(skill, skill_library=skill_library)
            description = stage1_result.description
            notes.extend(stage1_result.notes)
        else:
            llm_for_stage1 = llm_client if llm_client.enabled else None
            oracle_ctx = (
                build_stage1_oracle(skill, llm_for_stage1, config, skill_library)
                if llm_for_stage1
                else None
            )

            if not description.strip() or count_tokens(description) <= config.short_description_tokens:
                description = generate_description(
                    skill,
                    llm_for_stage1,
                    oracle_ctx=oracle_ctx,
                    config=config,
                )
                notes.append("Stage 1: generated description from body")
                if oracle_ctx:
                    oracle_ctx.original_description = description

            if description.strip():
                description, stage1_notes = compress_description(
                    description,
                    llm_for_stage1,
                    skill=skill,
                    oracle_ctx=oracle_ctx,
                    skill_library=skill_library,
                    max_restore_steps=config.max_restore_steps,
                    config=config,
                )
                notes.extend(stage1_notes)

    if run_stage2 and body.strip():
        body, generated_refs, stage2_notes = restructure_body(
            body,
            llm_client if llm_client.enabled else None,
            min_reference_tokens=config.min_reference_tokens,
        )
        notes.extend(stage2_notes)
        new_references.update(generated_refs)

        existing_refs = deduplicate_existing_references(
            skill.references,
            skill.body,
            config.min_reference_tokens,
        )
        for name, content in existing_refs.items():
            if name not in new_references:
                new_references[name] = content

    if run_stage3:
        md_files: dict[str, str] = {"SKILL.md": body}
        for name, content in new_references.items():
            if name.lower().endswith(".md"):
                md_files[name] = content
        for ref in skill.references:
            if ref.path.name not in md_files and ref.path.suffix.lower() == ".md":
                md_files[ref.path.name] = ref.content

        stage3_result = extract_scripts_from_markdown(
            md_files,
            llm_client if llm_client.enabled else None,
            config,
        )
        notes.extend(stage3_result.notes)
        body = stage3_result.files.get("SKILL.md", body)
        for name, content in stage3_result.files.items():
            if name == "SKILL.md":
                continue
            new_references[name] = content
        extracted_scripts = stage3_result.scripts

    out_skill_dir = output_dir / skill.skill_dir.name
    files_written: list[str] = []

    if not dry_run:
        if out_skill_dir.exists():
            shutil.rmtree(out_skill_dir)
        out_skill_dir.mkdir(parents=True, exist_ok=True)

        frontmatter = dict(skill.frontmatter)
        frontmatter["description"] = description
        skill_md_path = out_skill_dir / "SKILL.md"
        write_skill_md(skill_md_path, frontmatter, body)
        files_written.append("SKILL.md")

        scripts_src = skill.skill_dir / "scripts"
        scripts_out = out_skill_dir / "scripts"
        if scripts_src.exists() and scripts_src.is_dir():
            shutil.copytree(scripts_src, scripts_out)
            files_written.append("scripts/")

        for rel_path, script_content in extracted_scripts.items():
            script_path = out_skill_dir / rel_path
            script_path.parent.mkdir(parents=True, exist_ok=True)
            if script_path.exists():
                stem = script_path.stem
                suffix = 2
                while script_path.exists():
                    script_path = script_path.with_name(f"{stem}_{suffix}.py")
                    suffix += 1
            script_path.write_text(script_content, encoding="utf-8")
            files_written.append(str(script_path.relative_to(out_skill_dir)).replace("\\", "/"))

        for filename, content in new_references.items():
            ref_path = out_skill_dir / filename
            write_reference_file(ref_path, content, llm_client if llm_client.enabled else None)
            files_written.append(filename)

    tscg_stats: TscgStats | None = None
    run_tscg = config.tscg_enabled if tscg is None else tscg
    if run_tscg:
        tscg_stats, tscg_files, tscg_notes = _run_tscg_step(
            skill_dir=skill.skill_dir,
            out_skill_dir=out_skill_dir,
            extracted_scripts=extracted_scripts,
            tools_path=tools_path,
            config=config,
            dry_run=dry_run,
        )
        notes.extend(tscg_notes)
        files_written.extend(tscg_files)

    optimized_stats = TokenStats(
        description=count_tokens(description),
        body=count_tokens(body),
        references=sum(count_tokens(c) for c in new_references.values()),
    )

    return ReduceReport(
        source=skill.path,
        output=out_skill_dir,
        original_stats=original.stats,
        optimized_stats=optimized_stats,
        description_changed=description != skill.description,
        files_written=files_written,
        stage_notes=notes,
        tscg_stats=tscg_stats,
    )


def _run_tscg_step(
    *,
    skill_dir: Path,
    out_skill_dir: Path,
    extracted_scripts: dict[str, str],
    tools_path: Path | None,
    config: Config,
    dry_run: bool,
) -> tuple[TscgStats | None, list[str], list[str]]:
    notes: list[str] = []
    files_written: list[str] = []
    tools = None

    if tools_path is not None:
        try:
            tools = load_tools_json(Path(tools_path))
            notes.append(f"TSCG: loaded {len(tools)} tools from {tools_path}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            notes.append(f"TSCG skipped: failed to load tools ({exc})")
            return None, files_written, notes
    else:
        existing = find_existing_manifest(skill_dir)
        if existing is not None:
            try:
                tools = load_tools_json(existing)
                notes.append(f"TSCG: loaded {len(tools)} tools from {existing.name}")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                notes.append(f"TSCG skipped: failed to load {existing.name} ({exc})")
                return None, files_written, notes
        elif extracted_scripts:
            tools = tools_from_scripts(extracted_scripts)
            notes.append(
                f"TSCG: built {len(tools)} tool stubs from Stage 3 scripts"
            )
        else:
            scripts_dir = skill_dir / "scripts"
            if scripts_dir.is_dir():
                script_rels = [
                    f"scripts/{p.name}"
                    for p in sorted(scripts_dir.iterdir())
                    if p.is_file() and p.suffix.lower() in {".py", ".sh", ".bash"}
                ]
                if script_rels:
                    tools = tools_from_scripts(script_rels)
                    notes.append(
                        f"TSCG: built {len(tools)} tool stubs from scripts/"
                    )

    if not tools:
        notes.append(
            "TSCG skipped: no tools (pass --tools, add mcp_manifest.json, or extract scripts)"
        )
        return None, files_written, notes

    try:
        result = compress_tools(
            tools,
            model=config.tscg_model,
            profile=config.tscg_profile,
        )
    except TscgError as exc:
        notes.append(f"TSCG skipped: {exc}")
        if not dry_run:
            write_mcp_manifest(out_skill_dir / "mcp_manifest.json", tools)
            files_written.append("mcp_manifest.json")
            notes.append("TSCG: wrote mcp_manifest.json without compression")
        return None, files_written, notes

    notes.extend(result.notes)
    stats = TscgStats(
        original_tokens=result.original_tokens,
        compressed_tokens=result.compressed_tokens,
        tool_count=len(tools),
    )
    if not dry_run:
        files_written.extend(write_tscg_outputs(out_skill_dir, tools, result))
    return stats, files_written, notes
