# TSCG integration (optional)

Compresses MCP / tool JSON schemas with [@tscg/core](https://www.npmjs.com/package/@tscg/core) after SkillReducer writes a tool manifest.

## Setup

Requires Node.js ≥ 18:

```bash
cd skillreducer/tscg
npm install
```

## CLI

```bash
# Compress tools from a JSON file while reducing a skill
skillreducer reduce ./my-skill --tscg --tools tools.json

# Or set in config.yaml / env
# tscg.enabled: true
```

## Outputs (when TSCG runs)

| File | Purpose |
|------|---------|
| `mcp_manifest.json` | Full tool schemas (source) |
| `mcp_manifest.tscg.txt` | Compressed schema text for agents |
| `mcp_manifest.tscg.json` | Metrics + compressed string |

Stage 3 is optional. Pass `--tools` or place `mcp_manifest.json` in the skill folder.
