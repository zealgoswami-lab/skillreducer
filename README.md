# skillreducer

Open-source tool implementing the **SkillReducer** debloating framework for LLM agent skills, based on the research paper:

> **SkillReducer: Optimizing LLM Agent Skills for Token Efficiency**  
> Yudong Gao, Zongjie Li, Yuanyuan Yuan, Zimo Ji, Pingchuan Ma, Shuai Wang  
> [arXiv:2603.29919](https://arxiv.org/abs/2603.29919) · [PDF](skill_reducer.pdf) · [Detailed explanation](PAPER_DETAIL.md)

This repository implements the paper's two-stage pipeline (routing compression + progressive disclosure). The algorithm design, empirical study, and evaluation are from the original authors; see [CITATION.md](CITATION.md) for how to cite the paper.

Works with **any agent platform** that uses the standard `SKILL.md` + YAML frontmatter convention (Claude Code, Windsurf, OpenCode, SkillHub, GitHub community skills, and similar).

Every token in a skill description and body competes for context window space. SkillReducer debloats skills in two stages:

1. **Stage 1 — Routing layer:** compress or generate YAML `description` fields so agents route correctly with fewer tokens. See [stage1/README.md](skillreducer/stage1/README.md).
2. **Stage 2 — Body restructuring:** classify content (core rules, examples, templates, background), keep essentials in `SKILL.md`, and move the rest into on-demand reference files.

## Install

### Binary (recommended)

Download the latest `skillreducer` / `skillreducer.exe` from [GitHub Releases](https://github.com/zealgoswami-lab/skillreducer/releases), or build locally:

```bash
check python version and if it is not 3.12 then create venv before running pip commnad.
python -m venv venv
pip install -e ".[build]"
python build_binary.py
# Output: dist/skillreducer  (or dist/skillreducer.exe on Windows)
```

Then run directly — no Python required on the target machine:

```bash
./dist/skillreducer audit path/to/my-skill
./dist/skillreducer agent path/to/my-skill
```

### From source (no binary)

```bash
pip install -e .
# optional: pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set credentials:

```bash
cp .env.example .env
# edit .env:
#   api_key=sk-...
#   api_base_url=https://api.openai.com/v1
```

Run without building a binary (loads `.env` automatically):

```bash
python run.py audit data --recursive
python run.py reduce data/pdf-processing --stage 1
python run.py agent data/marketing-strategy --stage 1

# or after pip install -e .
python -m skillreducer reduce data/pdf-processing --stage 1
skillreducer reduce data/pdf-processing --stage 1
```

## Quick start

Sample skills are in [`data/`](data/) — run SkillReducer against them immediately:

```bash
python run.py audit data --recursive
python run.py reduce data/pdf-processing --no-llm
python run.py agent data/marketing-strategy --output optimized/
```


See [data/README.md](data/README.md) for what each sample skill demonstrates.

Audit a skill:

```bash
skillreducer audit path/to/my-skill
```

Reduce a skill (writes to `optimized/` by default):

```bash
skillreducer reduce path/to/my-skill
skillreducer reduce path/to/my-skill --output ./optimized --dry-run
```

Batch mode across a skill library:

```bash
skillreducer audit ./skills --recursive
skillreducer reduce ~/.claude/skills --recursive
skillreducer reduce ./my-skill-library --recursive
```

## Configuration

### API key, base URL, and models (from env)

Credentials and model ids are read from `.env` (auto-loaded on startup) or the environment. Env vars override `config.yaml`.

`.env` is discovered automatically: package root, parent directories of the current working directory, then cwd (later paths win among `.env` files).

| Setting | Env name | YAML key (`models.*`) |
|---------|----------|------------------------|
| **API key** | `api_key` | — |
| **API base URL** | `api_base_url` | `api_base_url` / `base_url` |
| **Compression model** (Stage 2, general LLM) | `compression_model` | `compression` |
| **Routing model** (Stage 1 oracle) | `routing_model` | `routing_oracle` |
| **Evaluation model** (Gate 2, planned) | `evaluation_model` | `evaluation` |

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
api_key: sk-...
api_base_url: https://api.openai.com/v1
models:
  compression: gpt-4o-mini
  routing_oracle: gpt-4o-mini
  evaluation: gpt-4o-mini
```

Without an API key, LLM features are disabled and heuristics are used. Use `--no-llm` to force heuristic-only mode.


See **[skillreducer/stage1/README.md](skillreducer/stage1/README.md)** for Stage 1 architecture (Algorithm 1), module map, oracle configuration, and Python API.

## Agno agent (recommended)

The Agno-powered agent accepts a **skill folder** and returns **optimized skill files**:

```bash
skillreducer agent path/to/my-skill
skillreducer agent path/to/my-skill --output ./optimized
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

- [`model.py`](skillreducer/model.py) — Agno `OpenAIChat` client factory from config
- [`agent.py`](skillreducer/agent.py) — `SkillReducerAgent` orchestrator + `AgnoLLMClient` for pipeline LLM steps

Requires `api_key` in `.env` (or `config.yaml`).

## Standard skill layout

```
my-skill/
├── SKILL.md          # frontmatter + compressed core body (always loaded)
├── examples.md       # on-demand (created by Stage 2)
├── templates.md      # on-demand
├── background.md     # on-demand
└── scripts/          # executable tools (not context-injected)
```

After optimization, reference files include routing metadata (`when`, `topics`) so the agent can load them selectively.

## CLI

| Command | Description |
|---------|-------------|
| `skillreducer audit <path>` | Token report + F1/F2/F3 issue flags |
| `skillreducer reduce <path>` | Run Stage 1 + Stage 2 optimization (OpenAI client) |
| `skillreducer agent <path>` | Same pipeline via Agno agent (skill folder → updated files) |
| `--stage 1` / `--stage 2` | Run a single stage |
| `--recursive` | Process all skills under a directory |
| `--dry-run` | Report savings without writing files |
| `--no-llm` | Heuristic mode (no API calls) |

## Issue codes (audit)

| Code | Meaning |
|------|---------|
| `F1_MISSING_DESCRIPTION` | No routing description in frontmatter |
| `F1_SHORT_DESCRIPTION` | Description too short for reliable routing |
| `F1_VERBOSE_DESCRIPTION` | Description likely contains non-routing filler |
| `F2_LARGE_BODY` / `F2_LONG_BODY` | Body too large; use progressive disclosure |
| `F2_MONOLITHIC` | Examples/templates embedded in SKILL.md |
| `F3_HEAVY_REFERENCES` | Reference files consume excessive tokens |

## Safety

- Never modifies skills in-place by default; output goes to `--output`.

## Development

```bash
pytest
ruff check src tests
```

## Research & citation

| Resource | Description |
|----------|-------------|
| [CITATION.md](CITATION.md) | BibTeX and APA citation for the paper |
| [PAPER_DETAIL.md](PAPER_DETAIL.md) | In-depth explanation of the paper |
| [skill_reducer.pdf](skill_reducer.pdf) | Original paper (local copy) |

If you use this tool in research, please cite the **SkillReducer paper** (Gao et al., 2026), not this repository alone.

## License

MIT — see [LICENSE](LICENSE). The SkillReducer research paper is © its authors; this repo is an independent implementation.
