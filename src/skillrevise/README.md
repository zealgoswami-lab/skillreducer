# SkillRevise

Vendored implementation of **SkillRevise** (Liu et al.) — execution-grounded skill revision.

| | |
|--|--|
| **Paper** | [SkillRevise: Improving LLM-Authored Agent Skills via Trace-Conditioned Skill Revision](https://arxiv.org/abs/2606.01139) |
| **Authors** | Yuxuan Liu, Zhaochen Su, Lingyun Xie, Yuhao Zhang, Qing Zong, Jiahe Guo, Zhongwei Xie, Yiyan Ji, Yauwai Yim, Hongyu Luo, Xiyu Ren, Ruan Chenyu, Haoran Li, Yangqiu Song |
| **arXiv** | [2606.01139](https://arxiv.org/abs/2606.01139) |
| **Upstream** | [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise) (MIT) |
| **Import name** | `skillrevise` |
| **Location in this repo** | `src/skillrevise/` |

This package is **not** SkillReducer (Gao et al.) and **not** TSCG (Sakizli).  
SkillRevise improves skill **behavior** from execution traces. SkillReducer improves skill **token cost**.

| Concern | Tool | Command |
|---------|------|---------|
| Token cost of `SKILL.md` | SkillReducer | `skillreducer reduce` / `agent` |
| Tool JSON schemas | TSCG | `skillreducer reduce … --tscg` |
| Skill quality from traces | **SkillRevise** (this package) | `skillrevise` or `skillreducer revise` |

See also: [PAPER_DETAIL.md §21](../../PAPER_DETAIL.md#21-skillrevise--trace-conditioned-skill-revision) · [CITATION.md](../../CITATION.md) · [docs/PAPERS.md](../../docs/PAPERS.md)

---

## What it does

LLM-authored skills often look correct but fail at runtime. SkillRevise runs a **trace-conditioned** loop:

1. **Author / load** an initial skill (or `--initial-skill path/to/SKILL.md`)
2. **Execute** on a task (paired evaluation with / without skill)
3. **Diagnose** failures from the execution trace
4. **Revise** the skill conditioned on that diagnosis (optional principle memory)
5. **Re-execute** and keep revisions that improve outcomes (up to `--max-revisions`)

```text
tasks.json + optional SKILL.md
        │
        ▼
  author / load skill
        │
        ▼
  execute ──► diagnose ──► revise ──► re-execute
        │                      ▲
        └──────────────────────┘  (until stop / max revisions)
        │
        ▼
  output JSON (results + summary)
```

---

## Benchmarks (eval only)

The `benchmarks/` package is **only for paper/eval harnesses** (SkillsBench, SkillLearnBench, ALFWorld).  
You do **not** need it to revise your own skills.

| Command | Purpose |
|---------|---------|
| `skillrevise <tasks.json> …` | Everyday revision (generic tasks) |
| `skillrevise-benchmark … --manifest-kind skillsbench` | Benchmark eval runner |
| `skillrevise-convert-skillsbench …` | Convert SkillsBench task dirs → JSON |

```bash
skillrevise-benchmark --help
skillrevise-benchmark path/to/tasks.json --manifest-kind skillsbench --limit 1 --output runs/out.json
```

Details: [benchmarks/README.md](benchmarks/README.md)

**Not vendored:** large upstream benchmark `data/` bundles. Clone [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise) if you need full eval datasets.

---

## Install

From the SkillReducer repo root:

```bash
pip install -e .
# optional analysis plots:
# pip install -e ".[revise-analysis]"
```

This installs the vendored package (`src/skillrevise`) and console scripts.  
No separate `git clone` of upstream is required for the library/CLI.

**Not vendored:** large upstream benchmark `data/` bundles — see [Benchmarks (eval only)](#benchmarks-eval-only).

---

## Run

### Direct CLIs (preferred)

```bash
skillrevise --help
skillrevise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
skillrevise path/to/tasks.json --initial-skill path/to/SKILL.md --max-revisions 2

skillrevise-llm --help
skillrevise-benchmark --help
skillrevise-convert-skillsbench --help
```

### Via SkillReducer (thin forward)

`skillreducer revise` only forwards arguments to `skillrevise.cli` — it does **not** change `audit` / `reduce` / `agent`:

```bash
skillreducer revise --skillrevise-help
skillreducer revise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
```

---

## Package layout

```text
src/skillrevise/
├── README.md              ← this file
├── LICENSE                ← MIT (upstream)
├── VENDOR.md              ← vendor notes
├── __init__.py            ← public exports
├── cli.py                 ← main harness CLI (skillrevise)
├── core/                  ← loop, models, metrics, runner, reporting, io
│   ├── loop.py            ← HarnessLoop (execute / diagnose / revise)
│   ├── runner.py          ← PairedRunner
│   ├── models.py
│   ├── metrics.py
│   ├── reporting.py
│   ├── agents.py
│   ├── artifacts.py
│   ├── env.py
│   └── io.py
├── method/                ← authoring, diagnosis, revision, principles
│   ├── authoring.py
│   ├── diagnosis.py
│   ├── revision.py
│   ├── principles.py
│   └── skill_parser.py
├── llm/                   ← LLM clients + skillrevise-llm command
│   ├── client.py
│   └── command.py
└── benchmarks/            ← EVAL ONLY (SkillsBench / ALFWorld / …)
    ├── README.md
    ├── run_benchmark.py   ← skillrevise-benchmark entry
    ├── skillsbench.py
    ├── skillsbench_adapter.py
    ├── skilllearnbench.py
    ├── alfworld.py
    ├── task_selection.py
    ├── verifier.py
    └── convert_skillsbench.py
```

### Key modules

| Module | Role |
|--------|------|
| `core.loop.HarnessLoop` | Orchestrates author → evaluate → diagnose → revise |
| `method.diagnosis` | Heuristic / LLM / no-op diagnosers |
| `method.revision` | Heuristic / LLM / free-form revision engines |
| `method.principles` | Principle bank + absorption across failures |
| `method.authoring` | Template / LLM / prior-guided skill authors |
| `benchmarks.skillsbench*` | SkillsBench loaders and agent harness |

Python imports:

```python
import skillrevise
from skillrevise.cli import main as skillrevise_main
from skillrevise.core.loop import HarnessLoop
```

---

## Configuration notes

- **LLM mode:** use SkillRevise env vars / flags documented by upstream and `skillrevise --help` / `skillrevise-llm --help` (e.g. author/diagnosis/revision modes).
- **Heuristic mode:** works without a remote LLM for many paths (`--baseline-only`, heuristic diagnosis/revision).
- **Outputs:** JSON reports via `--output`, optional `--summary-output` and `--principle-bank-output`.

---

## Separation from SkillReducer

| Does | Does not |
|------|----------|
| Live only under `src/skillrevise/` | Live under `skillreducer/revise/` (removed) |
| Expose `skillrevise` + `skillreducer revise` | Change Stages 1–3 or TSCG |
| Improve skill quality from traces | Guarantee token reduction |
| Ship MIT LICENSE + VENDOR.md | Vendor upstream `data/` benchmarks |

Attribution: [LICENSE](LICENSE) · [VENDOR.md](VENDOR.md)
