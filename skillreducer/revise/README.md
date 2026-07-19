# SkillRevise — vendored separate command

SkillRevise source lives in this repo under **`src/skillrevise/`**  
(from [xuansenpa1/skillrevise](https://github.com/xuansenpa1/skillrevise), MIT).

- Paper: [arXiv:2606.01139](https://arxiv.org/abs/2606.01139) (Liu et al.) — **not** the SkillReducer paper  
- No external git install required — `pip install -e .` includes it  
- Benchmark **`data/`** bundles are **not** vendored (large); clone upstream if you need full eval sets  

SkillRevise improves skill **behavior** (execute → diagnose → revise → re-execute).  
SkillReducer improves skill **token cost** (`audit` / `reduce` / `agent`).  
They stay **separate commands**.

---

## Install

```bash
pip install -e .
# optional SkillRevise analysis plots:
# pip install -e ".[revise-analysis]"
```

---

## Run

Via SkillReducer (args forwarded to SkillRevise CLI):

```bash
skillreducer revise --skillrevise-help
skillreducer revise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
```

Or call the vendored entry points directly:

```bash
skillrevise --help
skillrevise-llm --help
```

Use `--initial-skill path/to/SKILL.md` to revise an existing skill.  
LLM mode uses SkillRevise env vars (see upstream README / `src/skillrevise`).

---

## Layout

```text
src/skillrevise/          ← vendored Python package (import skillrevise)
skillreducer/revise/      ← thin CLI wrapper only
```

| Does | Does not |
|------|----------|
| Ship SkillRevise code in-tree | Change Stage 1–3 or TSCG |
| Expose `skillreducer revise` + `skillrevise` | Vendor upstream `data/` benchmarks |

Attribution: `src/skillrevise/LICENSE` · `src/skillrevise/VENDOR.md`
