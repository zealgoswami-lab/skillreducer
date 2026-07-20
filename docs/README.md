# Documentation

All detailed docs live under `docs/`, grouped by topic.  
**Top-level usage** (install, CLI, config): [`../USAGE.md`](../USAGE.md)

```text
repo/
├── USAGE.md                 ← start here for how to run the toolkit
├── BEGINNER.md              ← beginner hub
├── README.md                ← project overview
├── CITATION.md
└── docs/
    ├── README.md            ← this index
    ├── OVERVIEW.md          ← how the three papers fit
    ├── PAPERS.md            ← paper index + arXiv
    ├── REDUCTION_FLOW.md    ← simple flow + worked example
    ├── skillreducer/        ← SkillReducer (Gao et al.)
    ├── tscg/                ← TSCG (Sakizli)
    └── skillrevise/         ← SkillRevise (Liu et al.)
```

---

## By topic

### SkillReducer — skill token reduction

| Doc | Purpose |
|-----|---------|
| [skillreducer/USAGE.md](skillreducer/USAGE.md) | Stages 1–3 CLI, config, flow |
| [skillreducer/BEGINNER.md](skillreducer/BEGINNER.md) | First audit / reduce |
| [skillreducer/PAPER.md](skillreducer/PAPER.md) | Research explanation |

Code notes: [../skillreducer/stage1/README.md](../skillreducer/stage1/README.md) · [stage2](../skillreducer/stage2/README.md) · [stage3](../skillreducer/stage3/README.md)

### TSCG — tool / MCP schema compression

| Doc | Purpose |
|-----|---------|
| [tscg/USAGE.md](tscg/USAGE.md) | `--tscg`, profiles, outputs |
| [tscg/BEGINNER.md](tscg/BEGINNER.md) | Provide tools JSON, first run |
| [tscg/PAPER.md](tscg/PAPER.md) | Research explanation |

Package folder: [../skillreducer/tscg/README.md](../skillreducer/tscg/README.md)

### SkillRevise — trace-conditioned skill quality

| Doc | Purpose |
|-----|---------|
| [skillrevise/USAGE.md](skillrevise/USAGE.md) | `revise` / `skillrevise` CLI |
| [skillrevise/BEGINNER.md](skillrevise/BEGINNER.md) | First revise run |
| [skillrevise/PAPER.md](skillrevise/PAPER.md) | Research explanation |
| [skillrevise/DEVELOPER.md](skillrevise/DEVELOPER.md) | Internals, algorithms, file map |

Package: [../src/skillrevise/README.md](../src/skillrevise/README.md)

---

## Cross-cutting

| Doc | Purpose |
|-----|---------|
| [OVERVIEW.md](OVERVIEW.md) | How SkillReducer + TSCG + SkillRevise fit |
| [PAPERS.md](PAPERS.md) | Index + citations links |
| [REDUCTION_FLOW.md](REDUCTION_FLOW.md) | Simple reduction flow + one example |
| [../CITATION.md](../CITATION.md) | BibTeX / APA |

---

## Suggested reading order

1. [`USAGE.md`](../USAGE.md) — run the tools  
2. Topic [BEGINNER](skillreducer/BEGINNER.md) for your goal  
3. [OVERVIEW.md](OVERVIEW.md) if you use more than one paper  
4. PAPER / DEVELOPER when you need research or internals  
