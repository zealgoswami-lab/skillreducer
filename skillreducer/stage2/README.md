# Stage 2 — Body restructuring (progressive disclosure)

Classify the `SKILL.md` body, keep actionable **core rules** always loaded, and move examples / templates / background into on-demand reference files.

Paper: Gao et al. 2026, Algorithm 2 ([arXiv:2603.29919](https://arxiv.org/abs/2603.29919)). Background: [docs/skillreducer/PAPER.md](../../docs/skillreducer/PAPER.md) sections 7–8.

## What it does

| Input | Output |
|-------|--------|
| Monolithic body (and optional existing `*.md` references) | Slim core body + `examples.md` / `templates.md` / `background.md` with `when` / `topics` metadata |

| Type | Destination |
|------|-------------|
| `core_rule` | Always-loaded body (`b*`) |
| `example` | `examples.md` (if ≥ `min_reference_tokens`) |
| `template` | `templates.md` |
| `background` | `background.md` (summarized) |
| `redundant` | Discarded |

Unclassified paragraphs default to **core rule**.

## Code flow

```
restructure_body()                 # disclose.py
  ├─ split_paragraphs()            # classify.py
  ├─ classify_paragraphs()         # classify.py (LLM or heuristic)
  ├─ compress_core()               # compress.py
  ├─ compress_examples()
  ├─ compress_templates()
  ├─ compress_background()
  └─ token gate: keep original if new body is not shorter

deduplicate_existing_references()  # disclose.py + dedup.py
write_reference_file()             # annotate when/topics, write *.md
```

Algorithm 2 also specifies **Gate 1**, **Gate 2**, and a **feedback loop** — not implemented; see [Missing gaps](#missing-gaps).

## Files

| File | Purpose |
|------|---------|
| `disclose.py` | Classify → compress → reference split; annotate/write refs; dedup existing refs |
| `classify.py` | Paragraph split; taxonomy classification (LLM + heuristic fallback) |
| `compress.py` | Type-specific compression |
| `dedup.py` | Line-level overlap removal between a reference and body text |
| `__init__.py` | Package marker (no public exports yet) |

Prompts used here: `CLASSIFY_PARAGRAPHS`, `SUMMARIZE_BACKGROUND`, `GEN_REFERENCE_META` in `llm/prompts.py`. Types: `ContentType`, `ContentItem`, `ReferenceFile` in `models.py`.

## Key functions

### `classify.py`

```python
split_paragraphs(body) -> list[str]
classify_paragraphs(paragraphs, llm) -> list[ContentItem]
# heuristic: heading/keyword rules; unknown → CORE_RULE
```

### `compress.py`

```python
compress_core(items) -> str              # bullets + exact-line dedupe
compress_examples(items) -> str          # group by heading key; keep one per group
compress_templates(items) -> str         # same as examples
compress_background(items, llm) -> str   # LLM summary or first 3 sentences
```

### `disclose.py`

```python
restructure_body(body, llm, min_reference_tokens=30) -> (new_body, refs, notes)
annotate_reference(content, llm) -> (annotated, when, topics)
write_reference_file(path, content, llm) -> None
deduplicate_existing_references(references, body, min_reference_tokens) -> dict[str, str]
```

### `dedup.py`

```python
remove_overlap(reference, body, min_tokens=30) -> str | None
# drop lines matching body exactly or word-overlap > 0.85
# return None if result is below min_tokens
```

## Configuration (Stage 2 keys)

```yaml
thresholds:
  min_reference_tokens: 30       # wired — drop refs shorter than this
  max_feedback_iterations: 2     # unused — intended for Gate 2 feedback

models:
  compression: ...               # classify, background summary, reference meta
  evaluation: ...                # unused — intended for Gate 2
```

## Run Stage 2 only

```bash
skillreducer reduce path/to/skill --stage 2
skillreducer reduce path/to/skill --stage 2 --no-llm
skillreducer agent path/to/skill --stage 2
```

```python
from skillreducer.stage2.disclose import restructure_body

body, refs, notes = restructure_body(skill_body, llm=None)
```

## Implementation status

| Paper component | Code | Status |
|-----------------|------|--------|
| Paragraph split | `classify.py` | Done |
| Taxonomy classification (5 types) | `classify.py` | Done |
| Conservative fallback → core | `classify.py` | Done |
| Core → bullets in `b*` | `compress.py` | Partial (no semantic merge) |
| Examples → `examples.md` | `compress.py`, `disclose.py` | Partial (heading-key grouping) |
| Templates → `templates.md` | `compress.py` | Partial (aliases examples) |
| Background summary | `compress.py` | Done |
| Discard redundant | `disclose.py` | Done |
| Progressive disclosure links | `disclose.py` | Done |
| Reference `when` / `topics` | `disclose.py` | Done |
| Cross-file dedup | `dedup.py`, `disclose.py` | Partial |
| Token gate (keep original if not shorter) | `disclose.py` | Done |
| Gate 1 faithfulness | — | **Missing** |
| Gate 2 task eval (D / A / C) | — | **Missing** |
| Feedback loop (promote to core) | — | **Missing** |
| Fallback after failed feedback | — | **Missing** |

## Missing gaps

Stage 2 only — vs Algorithm 2.

### Quality safeguards

1. **Gate 1 — Faithfulness** — LLM check that operational concepts from the original body are preserved in core ∪ references, with per-type rollback. Only a token-count gate exists.
2. **Gate 2 — Task eval** — 5 tasks, conditions D / A / C, retention metric. `models.evaluation` is never used.
3. **Feedback loop** — on Gate 2 failure, promote needed non-core items into core (original form), recompress the rest, retry up to `max_feedback_iterations` (config loaded, never read).
4. **Post-feedback fallback** — keep best compression (most promoted items) if feedback still fails.

### Compression fidelity

5. **Core: no semantic merge** — paper merges by semantic similarity into concise bullets; code only bulletizes and exact-line-dedupes.
6. **Examples: weak concept grouping** — paper groups by concept and strips comments; code groups by first-line heading key only.
7. **Templates: no dedicated logic** — `compress_templates` aliases `compress_examples`.

### Deduplication

8. **New references not deduped** — `remove_overlap` runs only on pre-existing refs, not generated `examples.md` / `templates.md` / `background.md`.
9. **Overlap vs original body only** — paper also checks body-derived modules; code does not compare against compressed core or sibling generated refs.

### Recovery / packaging

10. **Misclassification is irreversible** — without Gate 1 / feedback, wrong `redundant` or non-core labels (e.g. example-as-specification) stay out of core.
11. **No `Stage2Result` / agent entrypoint** — only free functions; `__init__.py` exports nothing.
12. **No unit tests** for classify / compress / disclose / dedup.
