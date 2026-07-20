# SkillRevise — Beginner guide

SkillRevise improves skill **behavior** from execution traces. It does **not** replace SkillReducer token compression.

Related: [PAPER.md](PAPER.md) · [USAGE.md](USAGE.md) · [DEVELOPER.md](DEVELOPER.md) · [../../USAGE.md](../../USAGE.md) (top-level) · [../OVERVIEW.md](../OVERVIEW.md) · [../PAPERS.md](../PAPERS.md)

---

## What is this?

| Concern | Tool | Command |
|---------|------|---------|
| Fewer tokens in `SKILL.md` | SkillReducer | `skillreducer reduce` |
| Fewer tokens in tool JSON | TSCG | `skillreducer reduce … --tscg` |
| Better skill quality from failures | **SkillRevise** | `skillreducer revise` / `skillrevise` |

LLM-authored skills often look fine but fail at runtime. SkillRevise:

1. Runs the skill on a task  
2. Diagnoses problems from the **trace**  
3. Revises the skill  
4. Re-runs and keeps improvements  

```text
tasks.json + optional SKILL.md
        │
        ▼
  execute → diagnose → revise → re-execute
        │
        ▼
  output JSON (results + summary)
```

---

## What you need

| Tool | Required? |
|------|-----------|
| Python 3.11+ + `pip install -e .` | Yes |
| A `tasks.json` (or benchmark tasks) | Yes |
| Optional initial `SKILL.md` | `--initial-skill` |
| API key | For LLM diagnosis/revision modes; heuristic / `--baseline-only` can run without |

Large upstream benchmark `data/` bundles are **not** vendored — clone [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise) if you need full eval sets.

---

## Install

From the SkillReducer repo root:

```bash
pip install -e .
# optional analysis plots:
# pip install -e ".[revise-analysis]"
```

---

## First run

```bash
skillreducer revise --skillrevise-help
# or
skillrevise --help

skillrevise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
skillrevise path/to/tasks.json --initial-skill path/to/SKILL.md --max-revisions 2
```

Via SkillReducer (thin forward — does **not** run inside `reduce`):

```bash
skillreducer revise path/to/tasks.json --limit 1 --output runs/out.json
```

---

## Mental model vs reduce

| `reduce` | `revise` |
|----------|----------|
| Shrinks tokens | Improves behavior |
| Stages 1–3 (+ optional TSCG) | Execute / diagnose / revise loop |
| Writes `optimized/` | Writes run JSON / revised skill artifacts |
| Always available after install | Same install; separate command |

---

## Next steps

| Goal | Doc |
|------|-----|
| How the paper works | [PAPER.md](PAPER.md) |
| Full CLI / benchmarks | [USAGE.md](USAGE.md) |
| Internals / algorithms / file map | [DEVELOPER.md](DEVELOPER.md) |
| Package layout | [src/skillrevise/README.md](../../src/skillrevise/README.md) |
| Token reduction instead | [SkillReducer BEGINNER](../skillreducer/BEGINNER.md) |
