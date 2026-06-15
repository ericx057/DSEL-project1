# DSEL — Agent Handoff Document

**Project:** Document-Semantic Entity Lookup (DSEL)
**Branch:** `demo`
**Last updated:** 2026-06-08
**Status:** Demo complete. Retrieval at 91.2% Acc@5. LLM generation layer wired (Anthropic + OpenAI).

---

## What This Is

DSEL is a code-intelligence retrieval system demo for the FreeCAD codebase.
Given a natural-language question about FreeCAD internals, it:

1. Retrieves the most relevant source files and code chunks from a local SQLite index.
2. Feeds those chunks as context to an LLM (Claude Haiku or GPT-4o-mini) to generate a technical answer.
3. Displays the ranked file list + streaming LLM response in a floating Spotlight-style GUI.

The retrieval uses **no GPU and no remote embedding service** — a SHA-256 bag-of-words hashing
provider computes 128-dim deterministic embeddings locally.

---

## Quick Start (fresh machine)

```bash
# 1. Clone the repo and switch to the demo branch
git clone <repo-url> DSEL-project1
cd DSEL-project1
git checkout demo

# 2. Run the one-shot setup (creates venv, clones FreeCAD, indexes corpus)
bash setup.sh

# 3. Set at least one LLM API key
export ANTHROPIC_API_KEY=sk-ant-...   # Claude Haiku (preferred)
# OR
export OPENAI_API_KEY=sk-...          # GPT-4o-mini fallback

# 4. Launch the demo
python demo.py
```

`setup.sh` takes 10–20 min on first run (FreeCAD clone + indexing).
Re-runs are fast — it skips steps already completed.

---

## Repository Layout

```
DSEL-project1/
├── demo.py                        # Floating GUI demo (tkinter)
├── setup.sh                       # One-shot machine setup script
├── requirements.txt               # Python dependencies
├── HANDOFF.md                     # This document
├── README.md                      # Architecture overview
│
├── src/
│   ├── ingestion/
│   │   ├── cli.py                 # Ingestion entry point: python -m src.ingestion.cli
│   │   └── indexer.py             # File parser → SQLite artifact writer
│   └── retrieval/
│       ├── database.py            # SQLiteUnifiedStore + HashingEmbeddingProvider
│       ├── hybrid.py              # HybridSearcher (vector + graph + filename)
│       └── reranker.py            # LexicalReranker (term overlap + symbol bonuses)
│
├── evaluation/
│   ├── run_eval.py                # 250-question UMMDB benchmark harness
│   ├── generate_report.py         # Timed eval → PDF report generator
│   └── ummdb_eval_questions.md    # 250 questions across 5 seed datasets
│
└── .cis/
    └── index.db                   # SQLite index (created by setup.sh or ingestion CLI)
```

---

## Architecture

### Retrieval Pipeline

```
query
  │
  ├── filename_search()       SQL LIKE on basenames extracted from query text
  │                           + qualified C++ symbol extraction (Class::method)
  │
  ├── vector_search()         Numpy matrix multiply: (N×128) @ (128,) → top-K cosine
  │                           Cache built once per process (_ensure_emb_cache)
  │
  ├── graph_search()          BFS through co-reference graph edges in SQLite
  │
  └── LexicalReranker         Combines all candidates:
                              score = overlap + exact_symbol + file_score
                                    + impl_bonus + test_penalty + fn_bonus + path_bonus
```

### LLM Generation

The demo tries LLM backends in this priority order:

| Priority | Backend | Env var |
|----------|---------|---------|
| 1 | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) | `ANTHROPIC_API_KEY` |
| 2 | OpenAI GPT-4o-mini | `OPENAI_API_KEY` |

Override with: `DSEL_LLM_BACKEND=anthropic` or `DSEL_LLM_BACKEND=openai`

Top-5 retrieved snippets (up to 1 000 chars each) are sent as context. Responses stream
token-by-token into the right panel of the GUI.

### Embedding Backend

`HashingEmbeddingProvider` — deterministic 128-dim SHA-256 bag-of-words.
No GPU, no model download, ~2 µs/artifact amortized after cache warm-up.

To switch to semantic embeddings (higher accuracy, requires GPU/network):

```bash
CIS_EMBEDDING_BACKEND=nomic python -m src.ingestion.cli index freecad-src
```

---

## Benchmark Results (2026-06-08)

| Metric | Value |
|--------|-------|
| Accuracy@5 (mean) | **91.2%** |
| MRR (mean) | **75.3%** |
| Seed 1 — Call-chain tracing | Acc=0.960, MRR=0.898 |
| Seed 2 — Event/property propagation | Acc=0.940, MRR=0.838 |
| Seed 3 — Class hierarchy | Acc=0.840, MRR=0.570 |
| Seed 4 — Serialization & I/O | Acc=0.940, MRR=0.781 |
| Seed 5 — Algorithm internals | Acc=0.880, MRR=0.678 |

**Latency** (454,005-artifact corpus, cold SQLite page cache):

| Metric | Value |
|--------|-------|
| Mean query latency | 4,508 ms |
| P95 query latency | 6,455 ms |
| Cache build (one-shot) | 4,617 ms |
| Amortized encode cost | 10.17 µs / artifact |

Note: Cold-cache latency is dominated by SQLite I/O across 454k rows.
Warm-cache (repeated queries in the same process) is significantly faster.

Target: 95% Acc@5. Gap is ~8 questions, concentrated in:
- `Feature` namespace collision (Part vs PartDesign)
- `Constraint` base class (planegcs vs Sketcher)
- `Observer.h` flooding selection-related queries

### Generating the Performance Report

```bash
python evaluation/generate_report.py --out report.pdf
```

Produces a 6-page PDF: cover, summary table, accuracy/MRR chart,
latency histogram, retrieval stage breakdown, amortized encoding figure.

### Running the Benchmark

```bash
python evaluation/run_eval.py
```

---

## Ingestion

Re-index the FreeCAD corpus:

```bash
CIS_EMBEDDING_BACKEND=hashing \
CIS_DATA_DIR=.cis \
CIS_REPOSITORY_PATH=./freecad-src \
CIS_REPOSITORY_NAME=freecad \
python -m src.ingestion.cli index freecad-src
```

Indexed artifacts are stored in `.cis/index.db`. The ingestion CLI
auto-detects file types and creates one artifact per function/class/chunk.

---

## Known Failure Cases

| Query type | Root cause | Fix path |
|------------|-----------|----------|
| Part `Feature` vs PartDesign `Feature` | Same class name, different namespaces. Hashing embeddings can't distinguish. | Semantic embeddings (nomic) or namespace-aware indexing |
| `planegcs/Constraints.h` vs `Sketcher/Constraint.h` | fn_bonus (5) for Constraint.h overwhelms path_bonus (3) for planegcs dir. | Boost path_bonus or index qualified `planegcs::Constraint` symbol |
| `Observer.h` flooding | SHA-256 bag-of-words creates high cosine similarity to many files mentioning observers. | Increase fn_bonus threshold or add Observer.h to a demotion list |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Claude Haiku generation |
| `OPENAI_API_KEY` | — | Required for GPT-4o-mini generation |
| `DSEL_LLM_BACKEND` | auto | Force `anthropic` or `openai` |
| `CIS_DATA_DIR` | `.cis` | Directory for SQLite index |
| `CIS_REPOSITORY_PATH` | — | Path to FreeCAD source during ingestion |
| `CIS_REPOSITORY_NAME` | — | Repository name tag stored in index |
| `CIS_EMBEDDING_BACKEND` | `hashing` | `hashing` or `nomic` |
| `FREECAD_CLONE_DIR` | `./freecad-src` | Where setup.sh clones FreeCAD |

---

## Dependencies

Python 3.11+. Key packages:

| Package | Purpose |
|---------|---------|
| `anthropic>=0.30` | Claude Haiku streaming |
| `openai>=1.30` | GPT-4o-mini streaming |
| `numpy` | Fast matrix multiply for vector search |
| `networkx` | Co-reference graph traversal |
| `matplotlib` | PDF report generation |
| `tree-sitter` | C++/Python AST parsing during ingestion |
| `tkinter` | GUI (ships with Python on macOS/Linux) |

Install: `pip install -r requirements.txt`

---

## Git Branches

| Branch | Purpose |
|--------|---------|
| `master` | Stable retrieval core |
| `demo` | Demo GUI + LLM layer + setup.sh + this handoff doc |

The `demo` branch is the handoff target. Never merge demo back to master without
reviewing the LLM generation code for API key exposure.
