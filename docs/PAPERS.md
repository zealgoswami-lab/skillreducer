# Papers used in this repository

This repo implements **token reduction** for agent skills and (optionally) MCP tool schemas,  
plus an **optional separate command** for execution-grounded skill revision.  
Design and results belong to the paper authors — cite them, not only this GitHub project.

**How they fit together:** [OVERVIEW.md](OVERVIEW.md)

| Paper | What it covers | In this repo | Docs |
|-------|----------------|--------------|------|
| **SkillReducer** | Compress skill descriptions + bodies | Stages 1–3 | [PAPER](skillreducer/PAPER.md) · [BEGINNER](skillreducer/BEGINNER.md) · [USAGE](skillreducer/USAGE.md) |
| **TSCG** *(separate)* | Compress MCP / tool JSON schemas | Optional `--tscg` via `@tscg/core` | [PAPER](tscg/PAPER.md) · [BEGINNER](tscg/BEGINNER.md) · [USAGE](tscg/USAGE.md) |
| **TSCG + Agentic RAG** | Why schema compression unlocks tight budgets | Motivation for tool-schema step | [PAPER § companion](tscg/PAPER.md#companion-paper-agentic-rag) |
| **SkillRevise** *(separate)* | Trace-conditioned skill revision (quality) | Vendored `src/skillrevise/` + `skillreducer revise` | [PAPER](skillrevise/PAPER.md) · [BEGINNER](skillrevise/BEGINNER.md) · [USAGE](skillrevise/USAGE.md) |

```text
Skill quality (optional)  →  SkillRevise (Liu et al.)   →  skillreducer revise …
Skill tokens              →  SkillReducer (Gao et al.)  →  lean SKILL.md
Tool schemas              →  TSCG (Sakizli)             →  lean mcp_manifest.tscg.*
```

`revise` does **not** run inside `reduce`. SkillRevise code is vendored at `src/skillrevise/` (included in `pip install -e .`).

Flow diagrams (simple + one example): [REDUCTION_FLOW.md](REDUCTION_FLOW.md)

You provide the skill folder. For TSCG you also provide MCP/tools JSON.  
Neither paper’s compression requires sending your data to a cloud LLM for the TSCG step; SkillReducer Stage 1–2 may call an LLM unless you use `--no-llm`.

## Quick links

| Resource | Link |
|----------|------|
| Overview (all three) | [OVERVIEW.md](OVERVIEW.md) |
| SkillReducer arXiv | https://arxiv.org/abs/2603.29919 |
| TSCG arXiv | https://arxiv.org/abs/2605.04107 |
| TSCG RAG companion | https://arxiv.org/abs/2605.26165 |
| SkillRevise arXiv | https://arxiv.org/abs/2606.01139 |
| SkillRevise code | https://github.com/xuansenpa1/skillrevise |
| Citations / BibTeX | [CITATION.md](../CITATION.md) |
