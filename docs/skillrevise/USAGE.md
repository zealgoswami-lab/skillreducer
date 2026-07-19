# SkillRevise — usage details

CLI and package usage for Liu et al. SkillRevise (vendored at `src/skillrevise/`).  
Beginner: [BEGINNER.md](BEGINNER.md) · Paper: [PAPER.md](PAPER.md) · Package README: [../../src/skillrevise/README.md](../../src/skillrevise/README.md)

---

## Install

```bash
pip install -e .
# optional:
# pip install -e ".[revise-analysis]"
```

Console scripts: `skillrevise`, `skillrevise-llm`, `skillrevise-benchmark`, `skillrevise-convert-skillsbench`.

---

## Everyday revision

```bash
skillrevise --help
skillrevise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
skillrevise path/to/tasks.json --initial-skill path/to/SKILL.md --max-revisions 2

skillrevise-llm --help
```

### Via SkillReducer

`skillreducer revise` only forwards arguments to `skillrevise.cli` — it does **not** change `audit` / `reduce` / `agent`:

```bash
skillreducer revise --skillrevise-help
skillreducer revise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
```

---

## Benchmarks (eval only)

The `benchmarks/` package is for paper/eval harnesses (SkillsBench, SkillLearnBench, ALFWorld). You do **not** need it to revise your own skills.

```bash
skillrevise-benchmark --help
skillrevise-benchmark path/to/tasks.json --manifest-kind skillsbench --limit 1 --output runs/out.json
skillrevise-convert-skillsbench --help
```

Details: [benchmarks/README.md](../../src/skillrevise/benchmarks/README.md)

**Not vendored:** large upstream benchmark `data/` bundles — clone [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise) if needed.

---

## Configuration notes

- **LLM mode:** env vars / flags from `skillrevise --help` / `skillrevise-llm --help` (author / diagnosis / revision modes).
- **Heuristic mode:** many paths work without a remote LLM (`--baseline-only`, heuristic diagnosis/revision).
- **Outputs:** JSON via `--output`; optional `--summary-output` and `--principle-bank-output`.

---

## Python API

```python
import skillrevise
from skillrevise.cli import main as skillrevise_main
from skillrevise.core.loop import HarnessLoop
```

Key modules:

| Module | Role |
|--------|------|
| `core.loop.HarnessLoop` | Orchestrates author → evaluate → diagnose → revise |
| `method.diagnosis` | Heuristic / LLM / no-op diagnosers |
| `method.revision` | Heuristic / LLM / free-form revision engines |
| `method.principles` | Principle bank + absorption across failures |
| `method.authoring` | Template / LLM / prior-guided skill authors |

---

## Separation from reduce / TSCG

| Does | Does not |
|------|----------|
| Live under `src/skillrevise/` | Live under Stages 1–3 |
| Expose `skillrevise` + `skillreducer revise` | Run automatically during `reduce` |
| Improve skill quality from traces | Guarantee token reduction |

Attribution: [LICENSE](../../src/skillrevise/LICENSE) · [VENDOR.md](../../src/skillrevise/VENDOR.md) · [CITATION.md](../../CITATION.md)
