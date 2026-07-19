# SkillRevise benchmarks (eval only)

This folder is **only for paper / benchmark evaluation** (SkillsBench, SkillLearnBench, ALFWorld).

It is **not** required to revise your own skills.

| Use case | Command |
|----------|---------|
| Revise your own skill / tasks | `skillrevise path/to/tasks.json …` or `skillreducer revise …` |
| Run a **benchmark** eval | `skillrevise-benchmark … --manifest-kind skillsbench` |
| Convert SkillsBench task dirs | `skillrevise-convert-skillsbench …` |

Paper: [arXiv:2606.01139](https://arxiv.org/abs/2606.01139) · Parent docs: [../README.md](../README.md)

---

## What lives here

| File | Role |
|------|------|
| `run_benchmark.py` | CLI entry `skillrevise-benchmark` (benchmark kinds only) |
| `skillsbench.py` | SkillsBench-style task manifest loader |
| `skillsbench_adapter.py` | Real harness / agent adapter for SkillsBench |
| `skilllearnbench.py` | SkillLearnBench loader |
| `alfworld.py` | ALFWorld loader |
| `convert_skillsbench.py` | Convert SkillsBench `task.toml` trees → JSON |
| `verifier.py` | External verifier command wrapper |
| `task_selection.py` | Family / held-out task selection helpers |

Large upstream **`data/`** bundles are **not** vendored. Clone [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise) if you need full eval datasets.

---

## Run a benchmark

```bash
pip install -e .

# Show benchmark-only help
skillrevise-benchmark --help

# SkillsBench-style manifest
skillrevise-benchmark path/to/tasks.json \
  --manifest-kind skillsbench \
  --workspace-root path/to/repos \
  --limit 1 \
  --baseline-only \
  --output runs/bench_out.json

# Convert SkillsBench directories first (optional)
skillrevise-convert-skillsbench --help
```

`--manifest-kind` must be one of: `skillsbench` | `skilllearnbench` | `alfworld`.  
`generic` is rejected here — use `skillrevise` for that.

---

## Not for production skill editing

`skillreducer reduce` / Stages 1–3 and normal `skillrevise` on your own `tasks.json` do **not** need this folder’s harnesses. Keep benchmark deps and datasets out of day-to-day SkillReducer workflows.
