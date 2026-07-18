# TSCG Papers — Detailed Explanation

**Primary paper:** TSCG: Deterministic Tool-Schema Compilation for Agentic LLM Deployments  
**Author:** Furkan Sakizli  
**arXiv:** [2605.04107](https://arxiv.org/abs/2605.04107)  
**Code / package:** [SKZL-AI/tscg](https://github.com/SKZL-AI/tscg) · [`@tscg/core`](https://www.npmjs.com/package/@tscg/core)

**Companion paper:** Tool-Schema Compression Enables Agentic RAG Under Constrained Context Budgets  
**arXiv:** [2605.26165](https://arxiv.org/abs/2605.26165)

This document summarizes the papers for SkillReducer users.  
**All TSCG algorithms, operators, and empirical results are by Furkan Sakizli (2026).**  
This repository only *calls* `@tscg/core` after SkillReducer; it is not the TSCG research project.

See [CITATION.md](../CITATION.md) for BibTeX and [PAPERS.md](PAPERS.md) for how SkillReducer + TSCG fit together.  
Beginner-style summary also lives in [PAPER_DETAIL.md §20](../PAPER_DETAIL.md#20-another-paper-tscg-tool-schema-compression) (clearly marked as **another paper**, not Gao et al.).

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [The problem: tool-schema / “MCP tax”](#2-the-problem-tool-schema--mcp-tax)
3. [What TSCG is](#3-what-tscg-is)
4. [How compression works (operators)](#4-how-compression-works-operators)
5. [Key results](#5-key-results)
6. [Companion paper: Agentic RAG](#companion-paper-agentic-rag)
7. [Privacy / offline behavior](#7-privacy--offline-behavior)
8. [How this repository uses TSCG](#8-how-this-repository-uses-tscg)
9. [Glossary](#9-glossary)

---

## 1. Executive summary

Agent frameworks (OpenAI function calling, Anthropic tool use, **MCP**) send **tool schemas as JSON**. JSON is great for machines, but verbose for LLMs — especially when dozens of tools are injected every turn.

**TSCG** is a **deterministic compiler** at the API boundary:

- Input: tool definitions (OpenAI or Anthropic / MCP-style JSON)
- Output: compact structured text (fewer tokens)
- **No** model API calls, **no** fine-tuning, **no** runtime search
- Formal claim: **≥ 51%** savings on well-formed schemas (paper)
- Practical range often **~50–72%** depending on catalog and profile

**Why SkillReducer cares:** skills and tools burn **different** token budgets. SkillReducer shrinks `SKILL.md`; TSCG shrinks tool schemas. Together they cut more context cost than either alone.

---

## 2. The problem: tool-schema / “MCP tax”

| Issue | Effect |
|-------|--------|
| Full JSON Schema per tool | Thousands of tokens per turn |
| Many MCP servers at once | Context filled with schemas, not the user task |
| Small models (4B–14B) | JSON format mismatch → tool-use failures |
| Agentic RAG | Schemas compete with retrieved documents for the same window |

The companion RAG paper shows a **binary** failure mode at tight budgets (e.g. 8K): verbose JSON can overflow so RAG accuracy collapses; compressed schemas restore usability.

---

## 3. What TSCG is

| Property | Detail |
|----------|--------|
| Type | Deterministic schema **compiler** |
| Language | TypeScript (`@tscg/core`, zero runtime deps) |
| Speed | Sub-millisecond for typical catalogs |
| Profiles | `conservative` / `balanced` / `aggressive` |
| Model option | Tokenizer **profile** name (e.g. `claude-sonnet`) — **not** a remote LLM call |

TSCG does **not** rewrite your `server.py`. It transforms the **schema text** that would be shown to the model (or saved for later use).

---

## 4. How compression works (operators)

The paper describes eight composable operators (names vary slightly across docs; idea is the same): shorten types, drop redundant keys/words, restructure for attention, align to tokenizers, optionally reinforce critical params (SAD, Claude-oriented).

**Intuition (before → after):**

```text
BEFORE (JSON — many tokens)
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get the current weather for a location",
    "parameters": {
      "type": "object",
      "properties": {
        "location": { "type": "string", "description": "City name" }
      },
      "required": ["location"]
    }
  }
}

AFTER (TSCG — fewer tokens)
get_weather(location:str!) -> weather data
```

Profiles:

| Profile | Use when |
|---------|----------|
| `conservative` | Max compatibility; milder savings |
| `balanced` | Default in this repo — good savings/accuracy tradeoff |
| `aggressive` | Max compression (includes stronger operators; model-sensitive) |

The paper also reports **model archetypes** (e.g. Opus “operator-hungry”, Sonnet “operator-robust”, GPT-5.2 “operator-sensitive”) — pick profile per deployment model when accuracy matters.

---

## 5. Key results

From the primary TSCG paper / benchmarks (approximate; see arXiv for tables):

| Finding | Result |
|---------|--------|
| Token savings | Often ~50–72% on schemas; formal ≥51% bound on well-formed schemas |
| Small models | Can recover from near-zero tool accuracy to high accuracy at larger catalogs |
| BFCL / TAB | Accuracy often retained or improved vs verbose JSON (ARR can be >1) |
| Real MCP schemas | Synthetic gains transfer closely to production-like MCP schemas |
| Speed | Compile catalogs in milliseconds locally |

Exact numbers depend on model, tool count, and profile — always check your own `mcp_manifest.tscg.json` metrics after `--tscg`.

---

## Companion paper: Agentic RAG

**Title:** Tool-Schema Compression Enables Agentic RAG Under Constrained Context Budgets  
**arXiv:** [2605.26165](https://arxiv.org/abs/2605.26165)

**Claim:** Tool schemas and retrieved context fight for the same window. With TSCG (conservative, ~44–50% schema savings):

- At **8K** with many tools, JSON can **overflow** → ~0% useful RAG  
- Compressed schemas **enable** RAG again (+~20 pp EM average in their 8K study; larger lifts on some setups)  
- At **32K** where both fit, accuracy deltas shrink → effect is **budget-driven**, not magic quality boost  
- Scaling: JSON may overflow hundreds of tools sooner than compressed forms  

**Takeaway for this repo:** if your agent loads many MCP tools, schema compression is not optional polish — it can be what keeps the task in context.

---

## 7. Privacy / offline behavior

| Step | Network? |
|------|----------|
| `npm install` `@tscg/core` | Yes — download package once from npm |
| `compress()` / our `bridge.mjs` | **No** — local stdin/stdout only |
| SkillReducer `--no-llm` | No LLM calls for skill stages |
| SkillReducer with API key | Yes — only for Stage 1/2 LLM features |

TSCG does **not** upload your MCP JSON to Sakizli’s servers or to a model API.

---

## 8. How this repository uses TSCG

```text
You provide:  skill folder + tools.json (or mcp_manifest.json)
                    │
                    ▼
skillreducer reduce --tscg --tools tools.json
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  SkillReducer              Node bridge
  (Gao et al.)              + @tscg/core (Sakizli)
  lean SKILL.md             mcp_manifest.tscg.txt
```

Setup and beginner steps: [skillreducer/tscg/README.md](../skillreducer/tscg/README.md)  
Pipeline flag: `--tscg` / config `tscg.enabled`

---

## 9. Glossary

| Term | Meaning |
|------|---------|
| **Tool schema** | Name, description, parameters JSON for one tool |
| **MCP tax / tools tax** | Tokens spent injecting schemas every turn |
| **TSCG** | Token-Context Semantic Grammar / deterministic schema compiler |
| **Profile** | conservative / balanced / aggressive operator set |
| **ARR** | Accuracy-Retained Ratio (TSCG accuracy ÷ baseline) |
| **SAD** | Selective Anchor Duplication (aggressive / Claude-oriented) |

---

## Attribution

Please cite Sakizli (2026) when discussing TSCG methods or numbers.  
Please cite Gao et al. (2026) for SkillReducer skill debloating.  
This GitHub repo is an integration, not a substitute for those papers.
