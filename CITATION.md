# Citation

Please cite the **original research papers** when referring to frameworks, algorithms, or empirical findings. This repository is a community implementation / integration inspired by that work.

---

## SkillReducer (skill token reduction)

**Title:** SkillReducer: Optimizing LLM Agent Skills for Token Efficiency

**Authors:** Yudong Gao, Zongjie Li, Yuanyuan Yuan, Zimo Ji, Pingchuan Ma, Shuai Wang

**Affiliations:** The Hong Kong University of Science and Technology; Tsinghua University; Zhejiang University of Technology

**arXiv:** [2603.29919](https://arxiv.org/abs/2603.29919) (v2, June 2026)

### BibTeX

```bibtex
@article{gao2026skillreducer,
  title   = {SkillReducer: Optimizing LLM Agent Skills for Token Efficiency},
  author  = {Gao, Yudong and Li, Zongjie and Yuan, Yuanyuan and Ji, Zimo and Ma, Pingchuan and Wang, Shuai},
  journal = {arXiv preprint arXiv:2603.29919},
  year    = {2026},
  url     = {https://arxiv.org/abs/2603.29919}
}
```

### APA

Gao, Y., Li, Z., Yuan, Y., Ji, Z., Ma, P., & Wang, S. (2026). *SkillReducer: Optimizing LLM agent skills for token efficiency*. arXiv. https://arxiv.org/abs/2603.29919

### What to attribute

| Use case | Cite |
|----------|------|
| Two-stage debloating pipeline | Gao et al. (2026) |
| DDMIN description compression | Gao et al. (2026) |
| Five-category body taxonomy | Gao et al. (2026) |
| Progressive disclosure restructuring | Gao et al. (2026) |
| Empirical findings (55K skills study) | Gao et al. (2026) |

**Key results (from the paper):** ~48% description / ~39% body token reduction; 86% functional pass rate; +2.8% quality (less-is-more); 0.965 cross-model retention.

Full write-up: [PAPER_DETAIL.md](PAPER_DETAIL.md)

---

## TSCG (tool-schema token reduction)

Optional `--tscg` path in this repo uses [`@tscg/core`](https://www.npmjs.com/package/@tscg/core). Cite the TSCG papers for schema compilation methods and benchmarks.

### Primary paper

**Title:** TSCG: Deterministic Tool-Schema Compilation for Agentic LLM Deployments

**Author:** Furkan Sakizli

**arXiv:** [2605.04107](https://arxiv.org/abs/2605.04107)

```bibtex
@article{sakizli2026tscg,
  title   = {TSCG: Deterministic Tool-Schema Compilation for Agentic LLM Deployments},
  author  = {Sakizli, Furkan},
  journal = {arXiv preprint arXiv:2605.04107},
  year    = {2026},
  url     = {https://arxiv.org/abs/2605.04107}
}
```

### Companion paper (Agentic RAG)

**Title:** Tool-Schema Compression Enables Agentic RAG Under Constrained Context Budgets

**Author:** Furkan Sakizli

**arXiv:** [2605.26165](https://arxiv.org/abs/2605.26165)

```bibtex
@article{sakizli2026tscgrag,
  title   = {Tool-Schema Compression Enables Agentic RAG Under Constrained Context Budgets},
  author  = {Sakizli, Furkan},
  journal = {arXiv preprint arXiv:2605.26165},
  year    = {2026},
  url     = {https://arxiv.org/abs/2605.26165}
}
```

### What to attribute

| Use case | Cite |
|----------|------|
| Deterministic tool-schema compilation / operators | Sakizli (2026) TSCG |
| ≥51% formal savings bound / TAB–BFCL results | Sakizli (2026) TSCG |
| Tool–context trade-off for agentic RAG | Sakizli (2026) TSCG-RAG |
| This repo’s `--tscg` CLI wiring | Optional: this GitHub repository |

Full write-up: [docs/TSCG_PAPER_DETAIL.md](docs/TSCG_PAPER_DETAIL.md)

---

## SkillRevise (execution-grounded skill revision)

`skillreducer revise` uses the **vendored** package under [`src/skillrevise/`](src/skillrevise/)  
(from [`xuansenpa1/skillrevise`](https://github.com/xuansenpa1/skillrevise)).  
**Separate command** — does not change `audit` / `reduce` / `agent`.

**Title:** SkillRevise: Improving LLM-Authored Agent Skills via Trace-Conditioned Skill Revision

**Authors:** Yuxuan Liu, Zhaochen Su, Lingyun Xie, Yuhao Zhang, Qing Zong, Jiahe Guo, Zhongwei Xie, Yiyan Ji, Yauwai Yim, Hongyu Luo, Xiyu Ren, Ruan Chenyu, Haoran Li, Yangqiu Song

**arXiv:** [2606.01139](https://arxiv.org/abs/2606.01139)

```bibtex
@misc{liu2026skillrevise,
  title         = {SkillRevise: Improving LLM-Authored Agent Skills via Trace-Conditioned Skill Revision},
  author        = {Liu, Yuxuan and Su, Zhaochen and Xie, Lingyun and Zhang, Yuhao and Zong, Qing and Guo, Jiahe and Xie, Zhongwei and Ji, Yiyan and Yim, Yauwai and Luo, Hongyu and Ren, Xiyu and Ruan, Chenyu and Li, Haoran and Song, Yangqiu},
  year          = {2026},
  eprint        = {2606.01139},
  archivePrefix = {arXiv},
  url           = {https://arxiv.org/abs/2606.01139}
}
```

### What to attribute

| Use case | Cite |
|----------|------|
| Trace-conditioned skill revision / diagnosis / principle memory | Liu et al. (2026) SkillRevise |
| SkillsBench revision results in that paper | Liu et al. (2026) |
| This repo’s `skillreducer revise` CLI forwarding | Optional: this GitHub repository |

Docs: [src/skillrevise/README.md](src/skillrevise/README.md)

---

## This repository

| Use case | Cite |
|----------|------|
| CLI / Python integration only | Optional: this GitHub repository |
| SkillReducer algorithms or numbers | Gao et al. (2026) |
| TSCG algorithms or numbers | Sakizli (2026) |
| SkillRevise algorithms or numbers | Liu et al. (2026) |

Paper index: [docs/PAPERS.md](docs/PAPERS.md)

## Acknowledgment

The `skillreducer` package implements ideas from Gao et al. (2026), optionally integrates `@tscg/core` from Sakizli (2026), and vendors SkillRevise from Liu et al. (2026) under `src/skillrevise/`. We thank the authors for publishing their work. This project is **not** affiliated with or endorsed by the paper authors unless stated otherwise.
