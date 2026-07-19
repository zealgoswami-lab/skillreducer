# SkillReducer — Beginner guide

This guide is for people who are new to SkillReducer.  
You do **not** need to read the research paper first.

---

## What is this?

**SkillReducer** makes agent **skills** cheaper to run by cutting **tokens**.

A skill is usually a folder with a `SKILL.md` file (instructions for an AI agent).  
Long skills cost more money and can confuse the model. This tool:

1. **Audits** — shows how many tokens a skill uses  
2. **Reduces** — shortens the skill while keeping what matters  
3. **Optional TSCG** — if **you provide an MCP tools JSON**, also compresses tool schemas  

---

## How reduction works (big picture)

Tokens come from **two places**. SkillReducer handles skills; TSCG handles tools **only if you give it JSON**.

```text
┌─────────────────────────────────────────────────────────────┐
│  YOU PROVIDE                                                │
│    1) Skill folder with SKILL.md     (required)             │
│    2) MCP tools JSON                 (required for --tscg)  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP A — SkillReducer (always)                             │
│    Stage 1: shorten routing `description`                   │
│    Stage 2: move long examples/background into ref files    │
│    → fewer tokens when the skill is loaded                  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP B — TSCG (only with --tscg + your MCP JSON)           │
│    Reads your tools.json / mcp_manifest.json                │
│    Compresses verbose JSON schemas → compact text           │
│    → fewer tokens when tools are injected into the model    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
                   optimized/<skill>/
```

| What you want | What you must provide | What gets smaller |
|---------------|----------------------|-------------------|
| Lean skill only | `SKILL.md` folder | Skill text |
| Lean skill **+** lean tools | Skill folder **+ MCP JSON** | Skill text **and** tool schemas |

**Important:** SkillReducer does **not** invent your MCP tools. For tool compression you **must provide** the MCP/tools JSON yourself (`--tools tools.json` or `mcp_manifest.json` in the skill folder).

---

## What you need

| Tool | Required? | Why |
|------|-----------|-----|
| **Python 3.11+** | Yes | Runs SkillReducer |
| **Skill folder** (`SKILL.md`) | Yes | What gets reduced |
| **API key** (OpenAI-compatible) | Optional | Better compression; without it use `--no-llm` |
| **MCP tools JSON** | Required for `--tscg` | Your tool schemas to compress |
| **Node.js 18+** | Only for TSCG | Runs `@tscg/core` |

---

## Install (5 minutes)

Open a terminal in this folder (`skillreducer/`):

```bash
# Create a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

# Install SkillReducer
pip install -e .
```

Optional — for smarter compression, copy env and add your key:

```bash
copy .env.example .env
# Edit .env and set:
#   api_key=sk-...
#   api_base_url=https://api.openai.com/v1
```

---

## Your first run (skills only, no API key)

Sample skills are in `data/`. Try:

```bash
# 1) See token usage
python run.py audit data/pdf-processing

# 2) Compress without calling an LLM
python run.py reduce data/pdf-processing --no-llm

# Result folder:
#   optimized/pdf-processing/
```

Or after install:

```bash
skillreducer audit data/pdf-processing
skillreducer reduce data/pdf-processing --no-llm
```

This only reduces **skill** tokens. No MCP JSON needed yet.

---

## How skill reduction works (detail)

| Stage | What it does | Token effect |
|-------|--------------|--------------|
| **Stage 1** | Compresses or generates the YAML `description` (routing text) | Smaller always-on skill menu |
| **Stage 2** | Keeps core rules in `SKILL.md`; moves examples/background to separate files | Smaller body when skill activates; refs load on demand |
| **Stage 3** (optional) | Pulls large code blocks into `scripts/` | Less code pasted inside markdown |

**Before → after (idea):**

```text
BEFORE:  one huge SKILL.md (description + rules + examples + code)
AFTER:   short description + lean SKILL.md + examples.md + scripts/
```

---

## Reduce skills + MCP tools (you provide JSON)

### 1) You must provide MCP JSON

Create a file like `tools.json` with your tool schemas.  
Copy them from your MCP server (`list_tools` / tool definitions in `server.py`).

Minimal example:

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "extract_pdf",
        "description": "Extract text from a PDF file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": { "type": "string", "description": "Path to the PDF" }
          },
          "required": ["path"]
        }
      }
    }
  ]
}
```

| How you pass it | Command |
|-----------------|---------|
| Separate file | `--tools path/to/tools.json` |
| Inside skill folder | Put `mcp_manifest.json` in the skill, then `--tscg` |

Without one of these, `--tscg` is skipped with: `TSCG skipped: no tools`.

### 2) Install TSCG once

```bash
cd skillreducer/tscg
npm install
cd ../..
```

### 3) Run both reductions

```bash
skillreducer reduce ./my-skill --tscg --tools tools.json
```

### How tool reduction works

```text
YOUR mcp JSON (verbose)
  name, long descriptions, full JSON Schema...
        │
        ▼
     TSCG (@tscg/core)
        │
        ▼
Compact schema text (mcp_manifest.tscg.txt)
  → fewer tokens when the agent sees the tool list
```

### Example: how a JSON file is reduced

**Before — what you provide (`tools.json`):**

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "extract_pdf",
        "description": "Extract text from a PDF file at the given path",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Path to the PDF file on disk"
            },
            "pages": {
              "type": "string",
              "description": "Optional page range, e.g. 1-3"
            }
          },
          "required": ["path"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "merge_pdfs",
        "description": "Merge multiple PDF files into one output file",
        "parameters": {
          "type": "object",
          "properties": {
            "inputs": {
              "type": "array",
              "items": { "type": "string" },
              "description": "List of PDF paths to merge"
            },
            "output": {
              "type": "string",
              "description": "Destination path for the merged PDF"
            }
          },
          "required": ["inputs", "output"]
        }
      }
    }
  ]
}
```

**After — what TSCG writes (`mcp_manifest.tscg.txt`):**

```text
extract_pdf(path:str!, pages?:str) -> text
merge_pdfs(inputs:str[]!, output:str!) -> file
```

| Piece | Meaning |
|-------|---------|
| `path:str!` | required string (`!` = required) |
| `pages?:str` | optional string |
| `inputs:str[]!` | required array of strings |
| `-> text` | short result hint from the description |

Same tools, far fewer tokens: verbose JSON keys (`type`, `function`, `parameters`, `properties`, `description`, …) are dropped; types and required flags stay.

Typical savings on schemas: about **50–70%** (TSCG paper/benchmarks).  
Skill savings: about **~48% description / ~39% body** (SkillReducer paper) when LLM mode works well.

Full beginner steps for tools: [`skillreducer/tscg/README.md`](skillreducer/tscg/README.md).

---

## What just happened?

| Command | Meaning |
|---------|---------|
| `audit` | Count skill tokens and flag common problems |
| `reduce` | Write a smaller skill into `optimized/` |
| `reduce --tscg --tools …` | Same + compress **your** MCP JSON schemas |
| `revise …` | **Optional** SkillRevise (separate paper) — does **not** change reduce |

**Important:** originals are not overwritten. Output goes to `optimized/` by default.

Optional quality pass (vendored under `src/skillrevise/`):

```bash
skillreducer revise --skillrevise-help
```

Details: [`src/skillrevise/README.md`](src/skillrevise/README.md).

---

## Simple mental model

```text
YOU:  skill folder  +  (optional) MCP JSON you provide
              │
              ▼
        audit / reduce
              │
    ┌─────────┴─────────┐
    ▼                   ▼
 SkillReducer         TSCG (if --tscg + JSON)
 lean SKILL.md        lean tool schemas
    │                   │
    └─────────┬─────────┘
              ▼
     optimized/<skill-name>/
```

Full simple flow + one example: [docs/REDUCTION_FLOW.md](docs/REDUCTION_FLOW.md).

---

## Common questions

**Do I need to provide MCP JSON every time?**  
Only when you use `--tscg`. Skill-only reduce does not need it.

**Does SkillReducer talk to my live MCP `server.py`?**  
No. You export or copy schemas into JSON and pass that file.

**Do I need Stage 3?**  
No. Stages 1–2 are enough for most skills.

**Where do I put my own skill?**  

```text
my-skill/
  SKILL.md
  mcp_manifest.json   ← optional; or use --tools instead
```

**Something failed with “API key”?**  
Use `--no-llm`, or set `api_key` in `.env`.

---

## Next steps

| Goal | Go here |
|------|---------|
| Full docs | [README.md](README.md) |
| MCP JSON + TSCG for beginners | [skillreducer/tscg/README.md](skillreducer/tscg/README.md) |
| **Papers (SkillReducer + TSCG)** | [docs/PAPERS.md](docs/PAPERS.md) |
| **Flow + one example** | [docs/REDUCTION_FLOW.md](docs/REDUCTION_FLOW.md) |
| SkillReducer paper detail | [PAPER_DETAIL.md](PAPER_DETAIL.md) |
| TSCG paper detail | [docs/TSCG_PAPER_DETAIL.md](docs/TSCG_PAPER_DETAIL.md) |
| Sample skills | [data/README.md](data/README.md) |
| Citations | [CITATION.md](CITATION.md) |

---

## One-line cheat sheet

```bash
pip install -e .
skillreducer audit path/to/skill
skillreducer reduce path/to/skill --no-llm

# Skills + tools (YOU provide MCP JSON):
cd skillreducer/tscg && npm install && cd ../..
skillreducer reduce path/to/skill --tscg --tools tools.json
```
