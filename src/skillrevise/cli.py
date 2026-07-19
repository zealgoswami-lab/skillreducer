from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from skillrevise.core.agents import MockAgentAdapter
from skillrevise.core.env import get_env
from skillrevise.benchmarks.alfworld import ALFWorldTaskLoader
from skillrevise.method.authoring import (
    FileSkillAuthor,
    LLMSkillAuthor,
    NaiveSkillAuthoringPromptBuilder,
    PriorGuidedSkillAuthor,
    SkillCreatorPromptBuilder,
    SkillAuthoringPromptBuilder,
    TemplateSkillAuthor,
)
from skillrevise.core.artifacts import ArtifactStore
from skillrevise.method.diagnosis import HeuristicDiagnoser, LLMDiagnoser, NoOpDiagnoser
from skillrevise.core.io import load_tasks, to_jsonable, write_json
from skillrevise.llm import CommandLLMClient
from skillrevise.core.loop import HarnessLoop
from skillrevise.core.metrics import UTILITY_PRESETS, utility_weights_for_preset
from skillrevise.core.models import ExecutionTrace, TrajectoryEvent
from skillrevise.method.principles import PrincipleAbsorber, PrincipleBank, PrincipleRetrievalConfig
from skillrevise.core.reporting import summarize_baseline_runs, summarize_results
from skillrevise.method.revision import (
    REVISION_ABLATIONS,
    FreeFormLLMRevisionEngine,
    HeuristicRevisionEngine,
    LLMRevisionEngine,
)
from skillrevise.core.runner import PairedRunner
from skillrevise.benchmarks.skilllearnbench import SkillLearnBenchTaskLoader
from skillrevise.benchmarks.skillsbench import SkillsBenchTaskLoader, build_family_index, select_sibling_tasks
from skillrevise.benchmarks.skillsbench_adapter import CommandAgentHarness, SkillsBenchAgentAdapter
from skillrevise.benchmarks.verifier import CommandVerifier


def _filter_tasks(tasks, *, task_ids=None, families=None, limit=None):
    selected = list(tasks)
    if task_ids:
        wanted = set(task_ids)
        selected = [task for task in selected if task.task_id in wanted]
    if families:
        wanted_families = set(families)
        selected = [task for task in selected if task.family in wanted_families]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise SystemExit("No tasks selected after applying --task-id/--family/--limit filters.")
    return selected


def _apply_budget_override(tasks, budget_seconds: int | None):
    if budget_seconds is None:
        return list(tasks)
    updated = []
    for task in tasks:
        metadata = dict(task.metadata)
        metadata["timeout_seconds"] = budget_seconds
        metadata["budget_seconds"] = budget_seconds
        updated.append(replace(task, metadata=metadata))
    return updated


def _resolve_utility_weights(args: argparse.Namespace):
    weights = utility_weights_for_preset(args.utility_preset)
    overrides = {
        "alpha": args.utility_alpha,
        "beta": args.utility_beta,
        "gamma": args.utility_gamma,
        "lam": args.utility_lambda,
    }
    for field, value in overrides.items():
        if value is not None:
            setattr(weights, field, value)
    return weights


def _apply_ablation_condition(args: argparse.Namespace) -> None:
    condition = getattr(args, "ablation_condition", "full")
    if condition in {"no-principle-memory", "no-principle-memory-no-diagnosis"}:
        args.disable_principle_memory = True
    if condition in {"no-diagnosis", "no-principle-memory-no-diagnosis"}:
        args.diagnosis_mode = "none"


def _experiment_config(args: argparse.Namespace, weights) -> dict[str, Any]:
    principle_limit = args.principle_limit if args.principle_limit is not None else 4
    return {
        "ablation_condition": getattr(args, "ablation_condition", "full"),
        "utility_preset": args.utility_preset,
        "utility_weights": {
            "alpha": weights.alpha,
            "beta": weights.beta,
            "gamma": weights.gamma,
            "lambda": weights.lam,
        },
        "max_revisions": args.max_revisions,
        "continue_after_non_improving_revision": getattr(
            args,
            "continue_after_non_improving_revision",
            False,
        ),
        "max_heldout": args.max_heldout,
        "budget_seconds": args.budget_seconds,
        "repeat": args.repeat,
        "author_mode": args.author_mode,
        "authoring_principle_interface": getattr(args, "authoring_principle_interface", "legacy"),
        "diagnosis_mode": args.diagnosis_mode,
        "diagnosis_enabled": args.diagnosis_mode != "none",
        "revision_mode": args.revision_mode,
        "revision_ablation": getattr(args, "revision_ablation", "none"),
        "revision_removed_mechanism": {
            "none": "none",
            "no-execution-anchors": "execution anchors",
            "no-preserve-ledger": "preserve ledger",
        }.get(getattr(args, "revision_ablation", "none"), "unknown"),
        "principle_memory_enabled": not getattr(args, "disable_principle_memory", False),
        "principle_bank": args.principle_bank,
        "principle_limit": principle_limit,
        "principle_retrieval": getattr(args, "principle_retrieval", "hybrid-rrf"),
        "principle_embedding_model": getattr(args, "principle_embedding_model", "qwen/qwen3-embedding-4b"),
        "principle_embedding_url": getattr(args, "principle_embedding_url", None),
        "principle_embedding_cache": getattr(args, "principle_embedding_cache", None),
        "principle_keyword_weight": getattr(args, "principle_keyword_weight", 0.5),
        "principle_semantic_weight": getattr(args, "principle_semantic_weight", 0.5),
        "principle_rrf_k": getattr(args, "principle_rrf_k", 60),
        "principle_dense_content_weight": getattr(args, "principle_dense_content_weight", 0.05),
        "enable_principle_absorption": args.enable_principle_absorption,
        "principle_bank_output": args.principle_bank_output,
        "baseline_only": args.baseline_only,
        "baseline_run": args.baseline_run,
        "strict_llm": args.strict_llm,
        "initial_skill": args.initial_skill,
    }


def _load_baseline_trace_cache(path: str | Path) -> dict[str, ExecutionTrace]:
    payload = json.loads(Path(path).read_text())
    items = payload.get("baseline_results")
    if not isinstance(items, list):
        raise SystemExit("--baseline-run must point to a baseline-only run JSON containing baseline_results.")

    traces: dict[str, ExecutionTrace] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        trace_data = item.get("no_skill")
        if not isinstance(trace_data, dict):
            continue
        trace = _execution_trace_from_json(trace_data)
        traces[trace.task_id] = trace
    if not traces:
        raise SystemExit(f"No reusable no-skill traces found in --baseline-run {path}.")
    return traces


def _execution_trace_from_json(data: dict[str, Any]) -> ExecutionTrace:
    return ExecutionTrace(
        run_id=str(data.get("run_id", "")),
        task_id=str(data["task_id"]),
        skill_version=data.get("skill_version"),
        success=bool(data.get("success", False)),
        status=str(data.get("status", "unknown")),
        started_at=str(data.get("started_at", "")),
        ended_at=str(data.get("ended_at", "")),
        tokens=int(data.get("tokens", 0) or 0),
        tool_calls=int(data.get("tool_calls", 0) or 0),
        steps=int(data.get("steps", 0) or 0),
        latency_seconds=float(data.get("latency_seconds", 0.0) or 0.0),
        outcome_summary=str(data.get("outcome_summary", "")),
        events=[_trajectory_event_from_json(event) for event in data.get("events", []) if isinstance(event, dict)],
        metadata=dict(data.get("metadata", {})),
    )


def _trajectory_event_from_json(data: dict[str, Any]) -> TrajectoryEvent:
    return TrajectoryEvent(
        step_index=int(data.get("step_index", 0) or 0),
        kind=str(data.get("kind", "unknown")),
        summary=str(data.get("summary", "")),
        evidence=str(data.get("evidence", "")),
        metadata=dict(data.get("metadata", {})),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SkillRevise skill generation, diagnosis, and revision.")
    parser.add_argument("tasks", help="Path to a JSON file containing task specs.")
    parser.add_argument("--output", default="skillrevise_run.json", help="Where to save the run artifact.")
    parser.add_argument("--summary-output", help="Optional path for a compact summary JSON artifact.")
    parser.add_argument("--task-id", action="append", help="Run only the given task id. Can be repeated.")
    parser.add_argument("--family", action="append", help="Run only tasks from the given family. Can be repeated.")
    parser.add_argument("--limit", type=int, help="Run at most this many tasks after filtering.")
    parser.add_argument("--max-revisions", type=int, default=1, help="Maximum number of revise/re-evaluate rounds.")
    parser.add_argument(
        "--continue-after-non-improving-revision",
        action="store_true",
        help=(
            "Exploration mode: continue revising from a candidate even when it does "
            "not beat the incumbent; final selection still uses the best utility."
        ),
    )
    parser.add_argument("--repeat", type=int, default=1, help="Repeat each selected task this many times.")
    parser.add_argument("--budget-seconds", type=int, help="Override each task timeout/budget in seconds.")
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Run only the no-skill baseline for each selected task and skip skill generation/revision.",
    )
    parser.add_argument(
        "--baseline-run",
        help="Reuse no-skill traces from a previous baseline-only run JSON instead of rerunning them.",
    )
    parser.add_argument(
        "--utility-preset",
        choices=tuple(sorted(UTILITY_PRESETS)),
        default="full",
        help="Utility weighting preset for selection and reporting.",
    )
    parser.add_argument("--utility-alpha", type=float, help="Override same-task reward/success gain weight.")
    parser.add_argument("--utility-beta", type=float, help="Override efficiency gain weight.")
    parser.add_argument("--utility-gamma", type=float, help="Override transfer gain weight.")
    parser.add_argument("--utility-lambda", type=float, help="Override interference penalty weight.")
    parser.add_argument(
        "--manifest-kind",
        choices=("generic", "skillsbench", "skilllearnbench", "alfworld"),
        default="generic",
        help="How to interpret the task manifest.",
    )
    parser.add_argument("--workspace-root", help="Workspace root used to resolve relative repo paths.")
    parser.add_argument("--harness-command", help="External harness command for real benchmark execution.")
    parser.add_argument("--verifier-command", help="Optional verifier command override.")
    parser.add_argument(
        "--disable-verifier",
        action="store_true",
        help="Use harness status directly and skip the separate verifier step.",
    )
    parser.add_argument("--artifacts-root", help="Optional artifact directory for real benchmark runs.")
    parser.add_argument("--max-heldout", type=int, default=None, help="Maximum number of sibling tasks used for transfer.")
    parser.add_argument(
        "--author-mode",
        choices=(
            "template",
            "prior",
            "llm",
            "llm-principle",
            "llm-principle-bank",
            "llm-naive",
            "llm-skill-creator",
        ),
        default="template",
        help="How to generate the initial skill.",
    )
    parser.add_argument(
        "--ablation-condition",
        choices=("full", "no-principle-memory", "no-diagnosis", "no-principle-memory-no-diagnosis"),
        default="full",
        help=(
            "Convenience 2x2 ablation switch. full keeps principle memory and diagnosis; "
            "no-principle-memory disables principle-bank retrieval/absorption in authoring and revision; "
            "no-diagnosis withholds diagnosis while still allowing revision; the combined condition disables both."
        ),
    )
    parser.add_argument(
        "--diagnosis-mode",
        choices=("heuristic", "llm", "none"),
        default="heuristic",
        help="How to diagnose skill failures.",
    )
    parser.add_argument(
        "--authoring-principle-interface",
        choices=("legacy", "action-map"),
        default=get_env(os.environ, "SKILL_REVISE_AUTHORING_PRINCIPLE_INTERFACE", "legacy"),
        help=(
            "How v0 direct skill authoring turns retrieved principles into the initial skill. "
            "Use legacy to restore the previous prompt behavior."
        ),
    )
    parser.add_argument(
        "--revision-mode",
        choices=("heuristic", "llm", "llm-structured", "llm-principle-bank", "llm-freeform"),
        default="heuristic",
        help="How to revise skills.",
    )
    parser.add_argument(
        "--revision-ablation",
        choices=tuple(sorted(REVISION_ABLATIONS)),
        default="none",
        help=(
            "Structured-revision ablation switch. no-execution-anchors removes execution-anchor "
            "requirements and trace fields; no-preserve-ledger removes preserve ledger/risk fields."
        ),
    )
    parser.add_argument("--principle-bank", help="Optional JSON repair-principle bank for structured LLM revision.")
    parser.add_argument(
        "--principle-limit",
        type=int,
        help="Maximum number of retrieved repair principles injected into structured LLM revision.",
    )
    parser.add_argument(
        "--principle-retrieval",
        choices=("legacy", "bm25", "dense", "hybrid-rrf"),
        default="hybrid-rrf",
        help=(
            "Principle-bank retrieval backend. hybrid-rrf follows the SkillsBench-style "
            "BM25 + dense embedding + reciprocal-rank-fusion setup."
        ),
    )
    parser.add_argument(
        "--principle-embedding-model",
        default="qwen/qwen3-embedding-4b",
        help="Embedding model name used by dense/hybrid principle retrieval.",
    )
    parser.add_argument(
        "--principle-embedding-url",
        help=(
            "OpenAI-compatible embeddings endpoint or base URL. If omitted, dense retrieval "
            "uses SKILL_REVISE_PRINCIPLE_EMBEDDING_URL from the environment or local config."
        ),
    )
    parser.add_argument(
        "--principle-embedding-cache",
        help="Optional JSON cache file for principle/query embeddings.",
    )
    parser.add_argument("--principle-keyword-weight", type=float, default=0.5, help="RRF weight for BM25 retrieval.")
    parser.add_argument(
        "--principle-semantic-weight",
        type=float,
        default=0.5,
        help="RRF weight for dense embedding retrieval.",
    )
    parser.add_argument("--principle-rrf-k", type=int, default=60, help="RRF fusion constant.")
    parser.add_argument(
        "--principle-dense-content-weight",
        type=float,
        default=0.05,
        help="Dense retrieval weight for full principle content versus metadata.",
    )
    parser.add_argument(
        "--enable-principle-absorption",
        action="store_true",
        help="Absorb outcome-improving, utility-positive revision experience back into the principle bank.",
    )
    parser.add_argument(
        "--disable-principle-memory",
        action="store_true",
        help=(
            "Ablation switch: do not inject retrieved principle-bank entries into v0 authoring or revision, "
            "and do not absorb new principles."
        ),
    )
    parser.add_argument(
        "--principle-bank-output",
        help="Optional path to write the updated principle bank after absorption.",
    )
    parser.add_argument("--llm-command", help="External LLM command that reads prompt from stdin and writes response to stdout.")
    parser.add_argument("--llm-timeout", type=int, default=600, help="Timeout for each LLM command call.")
    parser.add_argument("--initial-skill", help="Optional Markdown skill file to use as the initial skill.")
    parser.add_argument(
        "--initial-skill-version",
        default="v0",
        help="Version label to assign to --initial-skill before revision numbering continues.",
    )
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="Fail instead of falling back to a heuristic skill when LLM skill authoring fails.",
    )
    args = parser.parse_args()
    _apply_ablation_condition(args)

    if args.manifest_kind == "skillsbench":
        tasks = SkillsBenchTaskLoader(args.workspace_root).load(args.tasks)
    elif args.manifest_kind == "skilllearnbench":
        tasks = SkillLearnBenchTaskLoader(args.workspace_root).load(args.tasks)
    elif args.manifest_kind == "alfworld":
        tasks = ALFWorldTaskLoader(args.workspace_root).load(args.tasks)
    else:
        tasks = load_tasks(args.tasks)
    tasks = _filter_tasks(tasks, task_ids=args.task_id, families=args.family, limit=args.limit)
    tasks = _apply_budget_override(tasks, args.budget_seconds)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    families = build_family_index(tasks)
    weights = _resolve_utility_weights(args)
    experiment_config = _experiment_config(args, weights)

    if args.harness_command:
        artifact_store = ArtifactStore(args.artifacts_root) if args.artifacts_root else None
        verifier = CommandVerifier(args.verifier_command) if args.verifier_command else None
        adapter = SkillsBenchAgentAdapter(
            harness=CommandAgentHarness(args.harness_command),
            artifact_store=artifact_store,
            verifier=verifier,
            disable_verifier=args.disable_verifier,
        )
    else:
        adapter = MockAgentAdapter()

    if args.baseline_only:
        baseline_items = []
        for repeat_index in range(args.repeat):
            for task in tasks:
                trace = adapter.run(task, None)
                trace.metadata["repeat_index"] = repeat_index
                baseline_items.append((task, trace))
                summary = summarize_baseline_runs(baseline_items)
                write_json(
                    args.output,
                    {
                        "experiment_config": experiment_config,
                        "completed": False,
                        "num_completed": len(baseline_items),
                        "num_expected": len(tasks) * args.repeat,
                        "summary": summary,
                        "baseline_results": [
                            {"task": to_jsonable(item_task), "no_skill": to_jsonable(item_trace)}
                            for item_task, item_trace in baseline_items
                        ],
                    },
                )
                if args.summary_output:
                    write_json(args.summary_output, summary | {"completed": False})
                score = trace.metadata.get("reward")
                print(
                    f"{task.task_id}: repeat={repeat_index} "
                    f"no-skill success={trace.success} reward={score} status={trace.status}"
                )

        summary = summarize_baseline_runs(baseline_items)
        write_json(
            args.output,
            {
                "experiment_config": experiment_config,
                "completed": True,
                "num_completed": len(baseline_items),
                "num_expected": len(tasks) * args.repeat,
                "summary": summary,
                "baseline_results": [
                    {"task": to_jsonable(task), "no_skill": to_jsonable(trace)} for task, trace in baseline_items
                ],
            },
        )
        if args.summary_output:
            write_json(args.summary_output, summary | {"completed": True})
        print(f"Wrote {len(baseline_items)} baseline task reports to {args.output}")
        if args.summary_output:
            print(f"Wrote compact baseline summary to {args.summary_output}")
        return

    llm = CommandLLMClient(args.llm_command, timeout_seconds=args.llm_timeout) if args.llm_command else None
    if (
        args.author_mode
        in {"llm", "llm-principle", "llm-principle-bank", "llm-naive", "llm-skill-creator"}
        or args.diagnosis_mode == "llm"
        or args.revision_mode in {"llm", "llm-structured", "llm-principle-bank", "llm-freeform"}
    ) and llm is None:
        parser.error("--llm-command is required when any mode is set to llm")

    principle_path = args.principle_bank
    principle_limit = args.principle_limit if args.principle_limit is not None else 4
    principle_retrieval_config = PrincipleRetrievalConfig(
        method=args.principle_retrieval,
        embedding_model=args.principle_embedding_model,
        embedding_url=args.principle_embedding_url,
        embedding_cache=args.principle_embedding_cache,
        keyword_weight=args.principle_keyword_weight,
        semantic_weight=args.principle_semantic_weight,
        rrf_k=args.principle_rrf_k,
        dense_content_weight=args.principle_dense_content_weight,
    )
    principle_bank = (
        PrincipleBank.from_json(principle_path, retrieval_config=principle_retrieval_config)
        if principle_path
        else PrincipleBank.with_seed_principles(retrieval_config=principle_retrieval_config)
    )

    if args.initial_skill:
        author = FileSkillAuthor(args.initial_skill, version=args.initial_skill_version)
    elif args.author_mode in {"llm", "llm-principle", "llm-principle-bank"}:
        authoring_principle_bank = (
            principle_bank
            if args.author_mode == "llm-principle-bank" and not args.disable_principle_memory
            else None
        )
        author = LLMSkillAuthor(
            llm,
            prompt_builder=SkillAuthoringPromptBuilder(
                principle_bank=authoring_principle_bank,
                principle_limit=principle_limit,
                principle_interface=args.authoring_principle_interface,
            ),
            allow_fallback=not args.strict_llm,
        )  # type: ignore[arg-type]
    elif args.author_mode == "llm-naive":
        author = LLMSkillAuthor(
            llm,
            prompt_builder=NaiveSkillAuthoringPromptBuilder(),
            fallback_author=TemplateSkillAuthor(),
            allow_fallback=not args.strict_llm,
        )  # type: ignore[arg-type]
    elif args.author_mode == "llm-skill-creator":
        author = LLMSkillAuthor(
            llm,
            prompt_builder=SkillCreatorPromptBuilder(),
            fallback_author=TemplateSkillAuthor(),
            allow_fallback=not args.strict_llm,
        )  # type: ignore[arg-type]
    elif args.author_mode == "prior":
        author = PriorGuidedSkillAuthor()
    else:
        author = TemplateSkillAuthor()

    if args.diagnosis_mode == "llm":
        diagnoser = LLMDiagnoser(llm)  # type: ignore[arg-type]
    elif args.diagnosis_mode == "none":
        diagnoser = NoOpDiagnoser()
    else:
        diagnoser = HeuristicDiagnoser()
    if args.revision_mode == "llm-freeform":
        reviser = FreeFormLLMRevisionEngine(
            llm,
            allow_fallback=not args.strict_llm,
        )  # type: ignore[arg-type]
    elif args.revision_mode in {"llm", "llm-structured", "llm-principle-bank"}:
        reviser = LLMRevisionEngine(
            llm,
            principle_bank=principle_bank,
            principle_limit=principle_limit,
            allow_fallback=not args.strict_llm,
            use_principle_memory=not args.disable_principle_memory,
            revision_ablation=args.revision_ablation,
        )  # type: ignore[arg-type]
    else:
        reviser = HeuristicRevisionEngine()
    principle_absorber = (
        PrincipleAbsorber(principle_bank)
        if args.enable_principle_absorption and not args.disable_principle_memory
        else None
    )

    loop = HarnessLoop(
        author=author,
        runner=PairedRunner(
            adapter,
            weights=weights,
            baseline_traces=_load_baseline_trace_cache(args.baseline_run) if args.baseline_run else None,
        ),
        diagnoser=diagnoser,
        reviser=reviser,
        max_revisions=args.max_revisions,
        principle_absorber=principle_absorber,
        continue_after_non_improving_revision=args.continue_after_non_improving_revision,
        require_diagnosis_for_revision=args.diagnosis_mode != "none",
    )

    results = []
    for repeat_index in range(args.repeat):
        for task in tasks:
            heldout = select_sibling_tasks(task, families, max_tasks=args.max_heldout)
            result = loop.run_task(task, heldout_tasks=heldout)
            result.selected_evaluation.with_skill.metadata["repeat_index"] = repeat_index
            result.selected_evaluation.no_skill.metadata["repeat_index"] = repeat_index
            results.append(result)
            print(
                f"{task.task_id}: repeat={repeat_index} selected {result.selected_skill.version} "
                f"score={result.selected_evaluation.utility.overall_score:.3f} "
                f"success={result.selected_evaluation.with_skill.success}"
            )

    summary = summarize_results(results)
    write_json(
        args.output,
        {
            "experiment_config": experiment_config,
            "summary": summary,
            "absorbed_principles": to_jsonable(loop.absorbed_principles),
            "results": [to_jsonable(result) for result in results],
        },
    )
    if args.summary_output:
        write_json(args.summary_output, summary)
    if args.principle_bank_output and not args.disable_principle_memory:
        principle_bank.write_json(args.principle_bank_output)
    print(f"Wrote {len(results)} task reports to {args.output}")
    if args.summary_output:
        print(f"Wrote compact summary to {args.summary_output}")
    if args.principle_bank_output and not args.disable_principle_memory:
        print(f"Wrote principle bank to {args.principle_bank_output}")


if __name__ == "__main__":
    main()
