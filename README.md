# DSEL — Code Intelligence Demo

Spotlight-style semantic code search over the FreeCAD codebase. Ask natural-language questions, get the exact source files back ranked by relevance.

## Architecture

```
query
  │
  ├─ filename_search  (SQL — extracts file/symbol names from query text)
  ├─ vector_search    (numpy dot-product against 128-dim hashing embeddings)
  └─ graph_search     (BFS over call-graph edges)
         │
         └─ LexicalReranker  (overlap + symbol + file + fn_bonus scores)
                │
                └─ top-5 artifacts
```

**Embedding backend:** `HashingEmbeddingProvider` — deterministic 128-dim bag-of-words via SHA-256. No GPU, no model download, fully offline. Swap in `nomic-ai/nomic-embed-text-v1.5` via `CIS_EMBEDDING_BACKEND=nomic` for better accuracy.

**Corpus:** FreeCAD (~454 K artifacts from 12 K source files across C++, Python, and headers).

**Eval benchmark:** 250-question UMMDB suite across 5 categories (call-chain tracing, event propagation, class hierarchy, serialization, algorithm internals). Current Acc@5: **~92%**.

## Setup (fresh machine)

Run once. Clones FreeCAD and builds the index — no GPU or internet access needed after this.

```bash
git clone <this-repo> && cd DSEL-project1
./setup.sh
```

What `setup.sh` does:
1. Creates `./venv` and installs core Python deps
2. Shallow-clones FreeCAD into `./freecad-src` (~200 MB)
3. Indexes all source files into `.cis/index.db` (~760 MB, takes 5–15 min)

### Options

| Env var | Default | Description |
|---|---|---|
| `FREECAD_CLONE_DIR` | `./freecad-src` | Where to clone FreeCAD |
| `CIS_DATA_DIR` | `./.cis` | Where to write `index.db` |
| `PYTHON` | `python3` | Python binary to use |

```bash
# Example: custom paths
FREECAD_CLONE_DIR=/tmp/freecad CIS_DATA_DIR=/tmp/cis ./setup.sh
```

## Run the demo

```bash
source venv/bin/activate
python demo.py
```

A floating Spotlight-style window appears. Type a natural-language question about FreeCAD internals and the top matching source files are returned with ranked snippets.

## Run the eval

```bash
source venv/bin/activate
python -m evaluation.run_eval
```

Runs 250 questions against the indexed corpus and reports Acc@5 and MRR per category.

## Manually re-index

If you want to re-index after a FreeCAD update or to change the embedding backend:

```bash
# Hashing backend (fast, no GPU)
CIS_EMBEDDING_BACKEND=hashing \
CIS_DATA_DIR=./.cis \
CIS_REPOSITORY_PATH=./freecad-src \
CIS_REPOSITORY_NAME=freecad \
    python -m src.ingestion.cli

# Nomic backend (better accuracy, requires torch)
pip install torch sentence-transformers
CIS_EMBEDDING_BACKEND=nomic \
CIS_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5 \
CIS_EMBEDDING_TRUST_REMOTE_CODE=true \
CIS_DATA_DIR=./.cis \
CIS_REPOSITORY_PATH=./freecad-src \
CIS_REPOSITORY_NAME=freecad \
    python -m src.ingestion.cli
```

## Project layout

```
src/
  retrieval/
    database.py     — SQLiteUnifiedStore: vector/filename/graph search, numpy cache
    hybrid.py       — HybridSearcher: combines filename + vector + graph results
    reranker.py     — LexicalReranker: scores candidates by term overlap + symbol match
    embeddings.py   — embedding provider protocols
  ingestion/
    indexer.py      — RepositoryIndexer: walks source tree, calls UMMDB parser
    cli.py          — entry point for indexing (env-var driven)
  UMMDB/
    parser/         — CascadingParser: extracts artifacts from C++/Python/headers

evaluation/
  run_eval.py              — 250-question benchmark runner
  ummdb_eval_questions.md  — question bank (5 seeds × 50 questions)

demo.py      — Tkinter floating search UI
setup.sh     — one-shot machine setup script
```
