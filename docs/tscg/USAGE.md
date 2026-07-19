# TSCG — usage details

Compress MCP / tool JSON schemas with Sakizli’s `@tscg/core` after (or with) SkillReducer.  
Beginner walkthrough: [BEGINNER.md](BEGINNER.md) · Paper: [PAPER.md](PAPER.md)

---

## Prerequisites

| Need | Notes |
|------|--------|
| SkillReducer installed | `pip install -e .` from repo root |
| Node.js 18+ | Runs `@tscg/core` |
| Your tools JSON | `--tools tools.json` **or** `mcp_manifest.json` in the skill folder |

```bash
cd skillreducer/tscg
npm install
cd ../..
```

---

## Commands

```bash
# Skill reduction + TSCG
skillreducer reduce ./my-skill --tscg --tools tools.json

# Manifest already inside the skill folder
skillreducer reduce ./my-skill --tscg

# Via agent command
skillreducer agent ./my-skill --tscg --tools tools.json
```

Without tools JSON, `--tscg` is skipped (`TSCG skipped: no tools`). Skill reduction still runs.

---

## Config (env / YAML)

| Setting | Env | YAML |
|---------|-----|------|
| Enable TSCG | `tscg_enabled` | `tscg.enabled` |
| Profile | `tscg_profile` | `tscg.profile` (`conservative` / `balanced` / `aggressive`) |
| Tokenizer profile name | `tscg_model` | `tscg.model` (e.g. `claude-sonnet` — **not** a remote LLM call) |

Default profile in this repo: **balanced**.

---

## Outputs

Inside `optimized/<skill-name>/`:

| File | Meaning |
|------|---------|
| `mcp_manifest.json` | Your tools (full schemas, saved for review) |
| `mcp_manifest.tscg.txt` | Compressed schemas — use these to save tokens |
| `mcp_manifest.tscg.json` | Before/after token metrics |

Report excerpt:

```text
TSCG (tool schemas)
  Tools: N | before -> after tokens (X% savings)
```

---

## Implementation map

| Piece | Path |
|-------|------|
| Normalize OpenAI / MCP shapes | `skillreducer/tscg/manifest.py` |
| Node bridge | `skillreducer/tscg/bridge.mjs` → `@tscg/core` |
| Python entrypoint | `skillreducer/tscg/compress.py` (`compress_tools`) |
| Package folder README | `skillreducer/tscg/README.md` |

---

## Troubleshooting

| Message | Fix |
|---------|-----|
| `TSCG skipped: no tools` | Pass `--tools` or add `mcp_manifest.json` |
| `Node.js not found` | Install Node 18+ |
| `TSCG dependency missing` | `npm install` in `skillreducer/tscg` |

**Privacy:** compiling schemas is local stdin/stdout after `npm install`. It does not upload your MCP JSON to a remote LLM.
