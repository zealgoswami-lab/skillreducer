# SkillReducer — usage details

CLI, install, and configuration for skill token reduction (Gao et al.).  
New here? Start with [BEGINNER.md](BEGINNER.md). Research background: [PAPER.md](PAPER.md).

Optional add-ons:
- Tool schemas → [TSCG USAGE](../tscg/USAGE.md)
- Quality from traces → [SkillRevise USAGE](../skillrevise/USAGE.md)

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

## Usage

### Quick start (sample skills in [`data/`](data/))

```bash
python run.py audit data --recursive
python run.py reduce data/pdf-processing --no-llm
python run.py agent data/marketing-strategy --output optimized/
```

See [../../data/README.md](../../data/README.md) for what each sample skill demonstrates.

### Audit (token report + issue flags)

```bash
skillreducer audit path/to/my-skill
skillreducer audit ./skills --recursive
```

### Reduce — full SkillReducer pipeline (Stages 1–3)

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

print(result.skill_md)           # optimized SKILL.md path
print(result.reference_files)    # examples.md, templates.md, etc.
print(result.agent_summary)      # token savings summary
```

### Optional TSCG (paper 2) — compress tool schemas

Needs Node ≥ 18 and a one-time install:

```bash
cd skillreducer/tscg && npm install
skillreducer reduce path/to/my-skill --tscg --tools tools.json
```

Writes `mcp_manifest.json`, `mcp_manifest.tscg.txt`, and `mcp_manifest.tscg.json` into the optimized skill folder.

### Optional SkillRevise (paper 3) — quality from traces

**Separate command** — does not run inside `reduce`:

```bash
skillreducer revise --skillrevise-help
skillrevise path/to/tasks.json --limit 1 --output runs/out.json

# Benchmark / paper evals only (SkillsBench, etc.):
skillrevise-benchmark --help
skillrevise-benchmark path/to/tasks.json --manifest-kind skillsbench --limit 1
```

Docs: [../skillrevise/USAGE.md](../skillrevise/USAGE.md) · benchmarks: [../../src/skillrevise/benchmarks/README.md](../../src/skillrevise/benchmarks/README.md)
### CLI reference

| Command / flag | Description |
|----------------|-------------|
| `skillreducer audit <path>` | Token report + F1/F2/F3 issue flags |
| `skillreducer reduce <path>` | Stages 1–3 (OpenAI / configured LLM client) |
| `skillreducer agent <path>` | Same pipeline via Agno agent |
| `skillreducer revise …` | SkillRevise (Liu et al.) — quality, not compression |
| `--stage 1` / `2` / `3` | Run a single SkillReducer stage |
| `--tscg` / `--tools <json>` | Compress tool schemas with TSCG after reduce |
| `--recursive` | Process all skills under a directory |
| `--dry-run` | Report savings without writing files |
| `--no-llm` | Heuristic mode (no API calls) |
| `--output` / `-o` | Output directory (default: `optimized`) |

Simple flow + worked example: [../REDUCTION_FLOW.md](../REDUCTION_FLOW.md)

---

## Configuration

### API key, base URL, and models (from env)

Credentials and model ids are read from `.env` (auto-loaded on startup) or the environment. Env vars override `config.yaml`.

`.env` is discovered automatically: package root → parent directories of cwd → cwd (later paths win among `.env` files).

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
  short_description_tokens: 40   # Stage 1: generate if description ≤ this
  min_reference_tokens: 30       # Stage 2: drop tiny reference files
  min_script_tokens: 20          # Stage 3: heuristic / LLM size hint
  max_restore_steps: 3           # Stage 1 Phase 2 restore
  max_feedback_iterations: 2     # Stage 2 Gate 2 (config only; not wired yet)

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

```
my-skill/
├── SKILL.md          # frontmatter + compressed core body (always loaded)
├── examples.md       # on-demand (Stage 2)
├── templates.md      # on-demand (Stage 2)
├── background.md     # on-demand (Stage 2)
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

## Safety

- Never modifies skills in-place by default; output goes to `--output`.

## Development

```bash
pytest
ruff check skillreducer tests
```

## Research & citation

| Resource | Description |
|----------|-------------|
| [../PAPERS.md](../PAPERS.md) | Paper index |
| [../OVERVIEW.md](../OVERVIEW.md) | How the three papers fit |
| [PAPER.md](PAPER.md) | SkillReducer explanation |
| [../tscg/PAPER.md](../tscg/PAPER.md) | TSCG explanation |
| [../skillrevise/PAPER.md](../skillrevise/PAPER.md) | SkillRevise explanation |
| [../../CITATION.md](../../CITATION.md) | BibTeX / APA |
| [../../skill_reducer.pdf](../../skill_reducer.pdf) | SkillReducer paper (local copy) |

If you use this tool in research, please cite the **SkillReducer paper** (Gao et al., 2026) for skill debloating, the **TSCG papers** (Sakizli, 2026) when discussing `--tscg`, and **SkillRevise** (Liu et al., 2026) for `revise` — not this repository alone.
