# TSCG folder — Beginner guide

This folder is **optional**.  
Use it only if you want to cut tokens from **MCP / tool schemas**, not from `SKILL.md` text.

SkillReducer (Python) already reduces skills.  
**TSCG** reduces the JSON that describes tools — and **you must provide that JSON**.

---

## You must provide the MCP JSON

SkillReducer / TSCG **do not** connect to your live MCP `server.py` over stdio.  
They only compress a **file you supply**.

| You provide | How |
|-------------|-----|
| `tools.json` | `skillreducer reduce ./my-skill --tscg --tools tools.json` |
| `mcp_manifest.json` inside the skill folder | `skillreducer reduce ./my-skill --tscg` |

If you pass `--tscg` without either, you get:

```text
TSCG skipped: no tools (pass --tools, add mcp_manifest.json, or extract scripts)
```

Your MCP server can keep using stdio as usual. The JSON is only an **offline copy of tool schemas** for compression.

---

## How reduction works here

Two different reductions, one command:

```text
skillreducer reduce ./my-skill --tscg --tools tools.json
        │
        ├─► A) SkillReducer
        │      Shortens SKILL.md (description + body / refs)
        │      → less skill text in context
        │
        └─► B) TSCG (this folder)
               Reads YOUR tools.json
               Compresses verbose JSON Schema → compact text
               → less tool-definition text in context
```

### A) Skill reduction (SkillReducer)

| Stage | Job |
|-------|-----|
| 1 | Smaller routing `description` |
| 2 | Core rules stay in `SKILL.md`; extras → on-demand files |
| 3 (optional) | Big code fences → `scripts/` |

### B) Tool-schema reduction (TSCG) — needs your JSON

**Example 1 — one simple tool**

```text
BEFORE (what you provide — verbose):
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get the current weather for a location …",
      "parameters": {
        "type": "object",
        "properties": {
          "location": { "type": "string", "description": "City name or coordinates" }
        },
        "required": ["location"]
      }
    }
  }]
}

AFTER (TSCG output — compact, fewer tokens):
get_weather(location:str!) -> weather data
```

**Example 2 — two tools with optional + array params**

```text
BEFORE (tools.json excerpt):
extract_pdf  → path (required string), pages (optional string)
merge_pdfs   → inputs (required string[]), output (required string)

AFTER (mcp_manifest.tscg.txt):
extract_pdf(path:str!, pages?:str) -> text
merge_pdfs(inputs:str[]!, output:str!) -> file
```

| Compact piece | Meaning |
|---------------|---------|
| `name(...)` | tool name |
| `param:str!` | required string |
| `param?:str` | optional string |
| `param:str[]!` | required array of strings |
| `-> …` | short result hint |

Typical schema savings: about **50–70%**. Exact number is printed in the reduce report and in `mcp_manifest.tscg.json`.

---

## Plain English

| Thing | What it is |
|-------|------------|
| **Skill** | Markdown instructions (`SKILL.md`) |
| **MCP tools** | Functions the agent can call (often from `server.py` over stdio) |
| **MCP JSON (you provide)** | Export/copy of tool name + description + parameters |
| **TSCG** | Compresses that JSON so tool lists use fewer tokens |

---

## Do I need this?

| Your case | Need this folder? | Need MCP JSON? |
|-----------|-------------------|----------------|
| Only shortening `SKILL.md` | **No** | No |
| Skills + MCP tools, lower tool-token cost | **Yes** | **Yes — you must provide it** |

---

## What you need

1. SkillReducer installed (`pip install -e .` from the repo root)
2. **Node.js 18+** — [https://nodejs.org](https://nodejs.org)
3. **Your MCP tools JSON** (`tools.json` or `mcp_manifest.json`)

```bash
node -v
# should print v18.x or higher
```

---

## Install (once)

From the **repo root** (`skillreducer/`):

```bash
cd skillreducer/tscg
npm install
```

That installs `@tscg/core` into `node_modules/` here (npm package — not a separate git clone).

---

## Create your MCP JSON (required for --tscg)

### Example `tools.json`

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City name"
            }
          },
          "required": ["location"]
        }
      }
    }
  ]
}
```

Also accepted:

- Bare array: `[ { "type": "function", "function": { ... } } ]`
- MCP-style: `{ "name", "description", "inputSchema" }` inside `"tools"`

### How to build it from `server.py` (stdio)

Stdio MCP servers expose tools via `list_tools` — they do **not** write this file for you.

1. **Copy** each tool’s name, description, and parameters from your server into `tools.json`
2. **Export** once with an MCP inspector / client that dumps `list_tools`
3. Save as `mcp_manifest.json` in the skill folder if you prefer not to use `--tools`

---

## Run it

From the **repo root**:

```bash
# YOU provide the MCP JSON via --tools
skillreducer reduce path/to/my-skill --tscg --tools path/to/tools.json
```

Or:

```bash
# YOU put mcp_manifest.json inside the skill folder
skillreducer reduce path/to/my-skill --tscg
```

---

## What you get

Inside `optimized/<skill-name>/`:

| File | Meaning |
|------|---------|
| `SKILL.md` (+ refs) | Skill reduction (SkillReducer) |
| `mcp_manifest.json` | Your tools (full schemas, saved for review) |
| `mcp_manifest.tscg.txt` | **Compressed** schemas — use these to save tokens |
| `mcp_manifest.tscg.json` | Before/after token metrics |

Report also shows:

```text
TSCG (tool schemas)
  Tools: N | before -> after tokens (X% savings)
```

---

## If something goes wrong

| Message | Fix |
|---------|-----|
| `TSCG skipped: no tools` | **Provide** `--tools tools.json` or add `mcp_manifest.json` |
| `Node.js not found` | Install Node 18+ and reopen the terminal |
| `TSCG dependency missing` | Run `npm install` inside `skillreducer/tscg` |
| Reduce works but TSCG skipped | Skill still reduced; only tool compression failed |

---

## Files in this directory

| File | Role |
|------|------|
| `bridge.mjs` | Node script that calls `@tscg/core` |
| `package.json` | Declares `@tscg/core` |
| `compress.py` | Python wrapper SkillReducer uses |
| `manifest.py` | Loads **your** MCP JSON |

---

## Related

- Main beginner guide (includes how reduction works): [../../BEGINNER.md](../../BEGINNER.md)
- Full project README: [../../README.md](../../README.md)
- **TSCG paper details:** [../../docs/TSCG_PAPER_DETAIL.md](../../docs/TSCG_PAPER_DETAIL.md)
- **Flow diagrams:** [../../docs/REDUCTION_FLOW.md](../../docs/REDUCTION_FLOW.md)
- All papers index: [../../docs/PAPERS.md](../../docs/PAPERS.md)
- Citations: [../../CITATION.md](../../CITATION.md)
- Package: [@tscg/core on npm](https://www.npmjs.com/package/@tscg/core)
