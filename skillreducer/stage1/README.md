# Stage 1 — Routing layer

Code for **Stage 1** of SkillReducer: optimize the YAML `description` field in `SKILL.md` so agents route correctly with fewer tokens.

Paper reference: Gao et al. 2026, Algorithm 1 ([arXiv:2603.29919](https://arxiv.org/abs/2603.29919)). For the research background see [docs/skillreducer/PAPER.md](../../docs/skillreducer/PAPER.md).

## What Stage 1 does

| Input | Output |
|-------|--------|
| `SKILL.md` frontmatter `description` (missing, short, or verbose) | Minimally sufficient routing description |

Two jobs:

1. **Generate** — if description is empty or ≤ `short_description_tokens` (default 40), build one from the skill body.
2. **Compress** — segment into clauses, run DDMIN with routing oracle, paraphrase, validate, recover if needed.

## Code flow

```
Stage1RoutingAgent.run()          # agent.py — Agno entry point
  or
pipeline.reduce_skill(stage=1)    # pipeline.py — OpenAI entry point

  ├─ generate_description()       # generate.py
  ├─ build_stage1_oracle()        # oracle.py — Q, distractors, s_adv
  └─ compress_description()       # compress.py
       ├─ segment_description()  # segment.py
       ├─ ddmin()                  # ddmin.py  (oracle callback)
       ├─ paraphrase_clauses_gated()
       ├─ polish_description()
       └─ selective_restore()      # Phase 2 validation on Q_val
```

## Files

| File | Purpose |
|------|---------|
| `oracle.py` | **New.** Simulated routing oracle O(d,Q,C), TF-IDF distractors, adversarial skill, test queries Q, Q_val |
| `compress.py` | **Updated.** DDMIN wired to real oracle; gated paraphrase; Phase 2 restore/fallback |
| `agent.py` | **Updated.** `Stage1RoutingAgent` uses oracle through full pipeline |
| `generate.py` | **Updated.** Generated descriptions validated via oracle |
| `segment.py` | Semantic clause split (LLM + heuristic fallback) |
| `ddmin.py` | Delta debugging minimization |
| `prompts.py` | Stage 1 LLM prompts (routing select, adversarial, test queries, polish) |
| `__init__.py` | Public exports |

## Code changes (vs earlier MVP)

| Before | After |
|--------|-------|
| `_simulated_oracle_pass()` — token overlap heuristic only | `simulated_oracle()` — routing model over pool **C** with **Q** |
| No distractor pool | `select_tfidf_distractors()` — 4 siblings by cosine similarity |
| No adversarial skill | `generate_adversarial_skill()` — LLM shadow skill s_adv |
| No test queries in DDMIN | `build_test_queries()` + `route_query()` per query |
| Paraphrase without oracle check | `paraphrase_clauses_gated()` — accept only if O(d,Q,C) passes |
| Selective restore on heuristic | `selective_restore()` on **Q_val** via simulated oracle |
| `routing_oracle()` post-check only (no recovery) | Oracle drives DDMIN + Phase 2 fallback to original |
| `config.example.yaml` oracle keys unused | `num_distractors`, `include_adversarial` loaded in `Config` |
| No docstrings on stage1 functions | All public functions document their Stage 1 role |

## Key types and functions

### `oracle.py`

```python
@dataclass
class CandidateSkill:      # one entry in pool C
class Stage1Oracle:          # target + Q + distractors + s_adv + Q_val

build_test_queries(skill, llm) -> list[str]
select_tfidf_distractors(target, library, k=4) -> list[CandidateSkill]
generate_adversarial_skill(name, description, llm) -> CandidateSkill | None
simulated_oracle(description, ctx, llm) -> bool   # O(d, Q, C)
build_stage1_oracle(skill, llm, config) -> Stage1Oracle
load_skill_library(skill) -> list[Skill]            # siblings for TF-IDF
```

### `compress.py`

```python
compress_description(description, llm, skill=..., oracle_ctx=...) -> (str, notes)
paraphrase_clauses_gated(clauses, ctx, llm, original) -> list[str]
polish_description(description, llm) -> str
selective_restore(minimal, deleted, ctx, llm) -> (str, notes)
```

### `agent.py`

```python
class Stage1RoutingAgent:
    run(skill) -> Stage1Result          # full Stage 1
    build_oracle(skill) -> Stage1Oracle
    generate(skill, ctx) -> str
    compress(description, skill) -> (str, notes)
```

## Configuration

From [`config.example.yaml`](../../config.example.yaml):

```yaml
models:
  routing_oracle: gpt-4o-mini

thresholds:
  short_description_tokens: 40
  max_restore_steps: 3

oracle:
  num_test_queries: 8
  num_distractors: 4
  include_adversarial: true
```

Distractors come from **sibling skills** in the same parent folder (`load_skill_library`). Put skills under a shared directory (e.g. `data/`) for meaningful pool **C**.

## How to run

```bash
skillreducer reduce path/to/skill --stage 1          # OpenAI LLMClient
skillreducer agent path/to/skill --stage 1           # Agno Stage1RoutingAgent
skillreducer reduce path/to/skill --stage 1 --no-llm # heuristic fallback
```

```python
from skillreducer.stage1 import Stage1RoutingAgent
from skillreducer.parser import parse_skill_md

result = Stage1RoutingAgent().run(parse_skill_md("path/to/skill"))
print(result.description, result.notes)
```

## Implementation status

| Paper component | Code | Status |
|-----------------|------|--------|
| Semantic segmentation | `segment.py` | Done |
| DDMIN | `ddmin.py` | Done |
| O(d, Q, C) simulated oracle | `oracle.py` | Done |
| TF-IDF distractors | `oracle.py` | Done |
| Adversarial s_adv | `oracle.py` | Done (LLM; skipped with `--no-llm`) |
| Gated paraphrase | `compress.py` | Done |
| Polish | `compress.py` | Done (LLM; string join fallback) |
| Q_val + selective restore | `oracle.py`, `compress.py` | Done (simulated oracle) |
| Real agent runtime validation | — | Not implemented |

## Tests

```bash
pytest tests/test_oracle.py tests/test_ddmin.py tests/test_stage1_agent.py
```

## Related changes outside this folder

- `pipeline.py` — passes `skill_library` and `oracle_ctx` into Stage 1
- `config.py` — `num_distractors`, `include_adversarial`
- `tests/test_oracle.py` — oracle and TF-IDF tests
