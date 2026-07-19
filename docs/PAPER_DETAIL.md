# Paper details (moved into `docs/`)

All paper write-ups now live under `docs/`, one folder per paper.  
Each paper has a deep **explanation**, a **beginner** guide, and **usage + full flow**.

| Paper | What it does | Explanation | Beginner | Usage + flow |
|-------|----------------|-------------|----------|--------------|
| **SkillReducer** (Gao et al.) | Compress skill `description` + body (+ scripts) | [skillreducer/PAPER.md](skillreducer/PAPER.md) | [BEGINNER](skillreducer/BEGINNER.md) | [USAGE](skillreducer/USAGE.md) |
| **TSCG** (Sakizli) | Compress MCP / tool JSON schemas | [tscg/PAPER.md](tscg/PAPER.md) | [BEGINNER](tscg/BEGINNER.md) | [USAGE](tscg/USAGE.md) |
| **SkillRevise** (Liu et al.) | Improve skill quality from execution traces | [skillrevise/PAPER.md](skillrevise/PAPER.md) | [BEGINNER](skillrevise/BEGINNER.md) | [USAGE](skillrevise/USAGE.md) |

**How all three fit together (full pipeline overview):** [OVERVIEW.md](OVERVIEW.md)  
**Paper index / citations:** [PAPERS.md](PAPERS.md) · [CITATION.md](../CITATION.md)  
**Simple reduce example:** [REDUCTION_FLOW.md](REDUCTION_FLOW.md)

```text
Optional quality   →  SkillRevise   →  skillreducer revise …
Skill text tokens  →  SkillReducer  →  lean SKILL.md + refs + scripts/
Tool schemas       →  TSCG          →  lean mcp_manifest.tscg.*
```

> **Attribution.** Algorithms and empirical results belong to each paper’s authors. This repository is an independent implementation / integration.
