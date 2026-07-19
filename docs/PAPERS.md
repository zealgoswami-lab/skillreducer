# Papers used in this repository

This repo implements **token reduction** for agent skills and (optionally) MCP tool schemas,  
plus an **optional separate command** for execution-grounded skill revision.  
Design and results belong to the paper authors — cite them, not only this GitHub project.

| Paper | What it covers | In this repo | Detail doc |
|-------|----------------|--------------|------------|
| **SkillReducer** | Compress skill descriptions + bodies | Stages 1–2 (+ optional Stage 3) | [PAPER_DETAIL.md](../PAPER_DETAIL.md) |
| **TSCG** *(separate paper)* | Compress MCP / tool JSON schemas | Optional `--tscg` via `@tscg/core` | [TSCG_PAPER_DETAIL.md](TSCG_PAPER_DETAIL.md) · also [PAPER_DETAIL.md §20](../PAPER_DETAIL.md#20-another-paper-tscg-tool-schema-compression) |
| **TSCG + Agentic RAG** | Why schema compression unlocks tight context budgets | Motivation for tool-schema step | [TSCG_PAPER_DETAIL.md](TSCG_PAPER_DETAIL.md#companion-paper-agentic-rag) |
| **SkillRevise** *(separate paper)* | Trace-conditioned skill revision (quality) | Vendored `src/skillrevise/` + `skillreducer revise` | [src/skillrevise/README.md](../src/skillrevise/README.md) · [VENDOR.md](../src/skillrevise/VENDOR.md) |

**How they fit together**

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
| SkillReducer arXiv | https://arxiv.org/abs/2603.29919 |
| TSCG arXiv | https://arxiv.org/abs/2605.04107 |
| TSCG RAG companion | https://arxiv.org/abs/2605.26165 |
| SkillRevise arXiv | https://arxiv.org/abs/2606.01139 |
| SkillRevise code | https://github.com/xuansenpa1/skillrevise |
| Citations / BibTeX | [CITATION.md](../CITATION.md) |
| Beginner usage | [BEGINNER.md](../BEGINNER.md) |
| Flow + one example | [REDUCTION_FLOW.md](REDUCTION_FLOW.md) |
| TSCG setup | [skillreducer/tscg/README.md](../skillreducer/tscg/README.md) |
| SkillRevise docs | [src/skillrevise/README.md](../src/skillrevise/README.md) |
