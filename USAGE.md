# Usage

Install, CLI, configuration, and common workflows for this toolkit.  
New here? Start with [BEGINNER.md](BEGINNER.md). Project overview: [README.md](README.md).

**Deeper docs by topic** (papers, beginners, internals): [docs/README.md](docs/README.md)

| You want… | Command / flag | Detail doc |
|-----------|----------------|------------|
| Audit skill tokens | `skillreducer audit …` | below |
| Compress `SKILL.md` | `skillreducer reduce` / `agent` | [docs/skillreducer/USAGE.md](docs/skillreducer/USAGE.md) |
| Compress tool JSON | `reduce … --tscg --tools …` | [docs/tscg/USAGE.md](docs/tscg/USAGE.md) |
| Improve skill quality | `skillreducer revise` / `skillrevise` | [docs/skillrevise/USAGE.md](docs/skillrevise/USAGE.md) |

```text
Optional quality   →  skillreducer revise …
Skill text tokens  →  skillreducer reduce / agent   →  lean SKILL.md + refs + scripts/
Tool schemas       →  reduce … --tscg --tools …     →  mcp_manifest.tscg.*
```

---

## Install

### Binary (recommended)

Download the latest `skillreducer` / `skillreducer.exe` from [GitHub Releases](https://github.com/zealgoswami-lab/skillreducer/releases), or build locally:

```bash
pip install -e ".[build]"
python build_binary.py
# Output: dist/skillreducer  (or dist/skillreducer.exe on Windows)
```

```bash
./dist/skillreducer audit path/to/my-skill
./dist/skillreducer agent path/to/my-skill
```

### From source

```bash
pip install -e .
# optional: pip install -e ".[dev]"
# SkillRevise analysis plots: pip install -e ".[revise-analysis]"
```

Copy `.env.example` to `.env` and set credentials:

```bash
cp .env.example .env
# api_key=sk-...
# api_base_url=https://api.openai.com/v1
```

```bash
python run.py audit data --recursive
python run.py reduce data/pdf-processing
python run.py agent data/marketing-strategy --stage 1

# or after pip install -e .
python -m skillreducer reduce data/pdf-processing
skillreducer reduce data/pdf-processing
```

---

## Quick start

Sample skills live in [`data/`](data/). See [data/README.md](data/README.md).

```bash
# 1) Token report
skillreducer audit data/pdf-processing

# 2) Compress without an API key
skillreducer reduce data/pdf-processing --no-llm

# Result: optimized/pdf-processing/
```

```bash
python run.py audit data --recursive
python run.py reduce data/pdf-processing --no-llm
python run.py agent data/marketing-strategy --output optimized/
```

Worked example + diagrams: [docs/REDUCTION_FLOW.md](docs/REDUCTION_FLOW.md).

---

## CLI — SkillReducer (`audit` / `reduce` / `agent`)

### Audit

```bash
skillreducer audit path/to/my-skill
skillreducer audit ./skills --recursive
```

### Reduce — Stages 1–3

Writes to `optimized/` by default (never in-place):

```bash
# All stages
skillreducer reduce path/to/my-skill
skillreducer reduce path/to/my-skill --output ./optimized --dry-run

# Single stage
skillreducer reduce path/to/my-skill --stage 1   # description only
skillreducer reduce path/to/my-skill --stage 2   # body disclosure only
skillreducer reduce path/to/my-skill --stage 3   # script extraction only

# Heuristic mode (no API calls)
skillreducer reduce path/to/my-skill --no-llm

# Batch
skillreducer reduce ~/.claude/skills --recursive
skillreducer reduce ./my-skill-library --recursive
```

| Stage | What it does |
|-------|----------------|
| **1** | Compress / generate YAML `description` (routing) |
| **2** | Keep core rules in `SKILL.md`; move examples/background to refs |
| **3** | Extract approved Python/bash fences into `scripts/` |

More: [docs/skillreducer/USAGE.md](docs/skillreducer/USAGE.md) · stages: [stage1](skillreducer/stage1/README.md) · [stage2](skillreducer/stage2/README.md) · [stage3](skillreducer/stage3/README.md)

### Agent — same pipeline via Agno

```bash
skillreducer agent path/to/my-skill
skillreducer agent path/to/my-skill --output ./optimized --stage 2
skillreducer agent ./skills --recursive
```

Python API:

```python
from pathlib import Path
from skillreducer.agent import SkillReducerAgent

agent = SkillReducerAgent()
result = agent.optimize(Path("path/to/my-skill"), output_dir=Path("optimized"))

print(result.skill_md)
print(result.reference_files)
print(result.agent_summary)
```

---

## Optional — TSCG (tool / MCP schemas)

Needs Node ≥ 18 and a one-time install. **You must provide** tools JSON.

```bash
cd skillreducer/tscg && npm install && cd ../..
skillreducer reduce path/to/my-skill --tscg --tools tools.json
# or: mcp_manifest.json inside the skill folder, then --tscg
```

Writes `mcp_manifest.json`, `mcp_manifest.tscg.txt`, and `mcp_manifest.tscg.json` into the optimized skill folder.

Without tools JSON: `TSCG skipped: no tools` (skill reduction still runs).

Full guide: [docs/tscg/USAGE.md](docs/tscg/USAGE.md) · [docs/tscg/BEGINNER.md](docs/tscg/BEGINNER.md)

---

## Optional — SkillRevise (quality from traces)

**Separate command** — does **not** run inside `reduce`:

```bash
skillreducer revise --skillrevise-help
skillrevise path/to/tasks.json --limit 1 --baseline-only --output runs/out.json
skillrevise path/to/tasks.json --initial-skill path/to/SKILL.md --max-revisions 2

# Benchmark / paper evals only:
skillrevise-benchmark --help
skillrevise-benchmark path/to/tasks.json --manifest-kind skillsbench --limit 1
```

Full guide: [docs/skillrevise/USAGE.md](docs/skillrevise/USAGE.md) · internals: [docs/skillrevise/DEVELOPER.md](docs/skillrevise/DEVELOPER.md)

---

## CLI reference

| Command / flag | Description |
|----------------|-------------|
| `skillreducer audit <path>` | Token report + F1/F2/F3 issue flags |
| `skillreducer reduce <path>` | Stages 1–3 |
| `skillreducer agent <path>` | Same pipeline via Agno |
| `skillreducer revise …` | SkillRevise — quality, not compression |
| `--stage 1` / `2` / `3` | Run a single SkillReducer stage |
| `--tscg` / `--tools <json>` | Compress tool schemas with TSCG after reduce |
| `--recursive` | Process all skills under a directory |
| `--dry-run` | Report savings without writing files |
| `--no-llm` | Heuristic mode (no API calls) |
| `--output` / `-o` | Output directory (default: `optimized`) |

---

## Configuration

Credentials and model ids are read from `.env` (auto-loaded on startup) or the environment. Env vars override `config.yaml`.

`.env` discovery: package root → parent directories of cwd → cwd (later paths win among `.env` files).

| Setting | Env name | YAML key |
|---------|----------|----------|
| **API key** | `api_key` | — |
| **API base URL** | `api_base_url` | `api_base_url` / `base_url` |
| **Compression model** (Stage 2 / general LLM) | `compression_model` | `models.compression` |
| **Routing model** (Stage 1 oracle) | `routing_model` | `models.routing_oracle` |
| **Evaluation model** (Gate 2, planned) | `evaluation_model` | `models.evaluation` |
| **TSCG enabled** | `tscg_enabled` | `tscg.enabled` |
| **TSCG model / profile** | `tscg_model` / `tscg_profile` | `tscg.model` / `tscg.profile` |

```bash
# .env (recommended)
api_key=sk-...
api_base_url=https://api.openai.com/v1
compression_model=gpt-4o-mini
routing_model=gpt-4o-mini
evaluation_model=gpt-4o-mini
```

Optional YAML (`config.example.yaml` → `config.yaml`):

```yaml
models:
  compression: gpt-4o-mini
  routing_oracle: gpt-4o-mini
  evaluation: gpt-4o-mini

thresholds:
  short_description_tokens: 40
  min_reference_tokens: 30
  min_script_tokens: 20
  max_restore_steps: 3
  max_feedback_iterations: 2

oracle:
  num_test_queries: 8
  num_distractors: 4
  include_adversarial: true

tscg:
  enabled: false
  model: claude-sonnet
  profile: balanced

use_llm: true
```

Without an API key, LLM features are disabled and heuristics are used. Use `--no-llm` to force heuristic-only mode.

---

## Standard skill layout

```text
my-skill/
├── SKILL.md          # frontmatter + compressed core body (always loaded)
├── examples.md       # on-demand (Stage 2)
├── templates.md      # on-demand (Stage 2)
├── background.md     # on-demand (Stage 2)
├── mcp_manifest.json # optional; or pass --tools
└── scripts/          # executable tools (Stage 3; not context-injected)
    ├── extract.py
    └── batch.sh
```

After optimization, reference files include routing metadata (`when`, `topics`) so the agent can load them selectively.

---

## Issue codes (audit)

| Code | Meaning |
|------|---------|
| `F1_MISSING_DESCRIPTION` | No routing description in frontmatter |
| `F1_SHORT_DESCRIPTION` | Description too short for reliable routing |
| `F1_VERBOSE_DESCRIPTION` | Description likely contains non-routing filler |
| `F2_LARGE_BODY` / `F2_LONG_BODY` | Body too large; use progressive disclosure |
| `F2_MONOLITHIC` | Examples/templates embedded in SKILL.md |
| `F3_HEAVY_REFERENCES` | Reference files consume excessive tokens |

---

## Safety & development

- Never modifies skills in-place by default; output goes to `--output`.

```bash
pytest
ruff check skillreducer tests
```

---

## Docs map

| Path | Contents |
|------|----------|
| [USAGE.md](USAGE.md) | **This file** — top-level usage |
| [BEGINNER.md](BEGINNER.md) | Beginner hub by paper |
| [docs/README.md](docs/README.md) | Full documentation index |
| [docs/skillreducer/](docs/skillreducer/) | SkillReducer PAPER · BEGINNER · USAGE |
| [docs/tscg/](docs/tscg/) | TSCG PAPER · BEGINNER · USAGE |
| [docs/skillrevise/](docs/skillrevise/) | SkillRevise PAPER · BEGINNER · USAGE · DEVELOPER |
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | How the three papers fit |
| [docs/PAPERS.md](docs/PAPERS.md) | Paper index + arXiv links |
| [CITATION.md](CITATION.md) | BibTeX / APA |
