#!/usr/bin/env python3
"""
Semantic Re-ranking Probe
==========================
Tests the quality ceiling of semantic embeddings WITHOUT re-indexing.

Strategy:
  1. Run hashing retrieval to get top-K candidates (wide net, e.g. K=50)
  2. Re-score each candidate with a semantic model (MiniLM or nomic)
  3. Blend: final_score = alpha * semantic + (1-alpha) * lexical
  4. Compare Acc@5 / MRR against baseline (hashing + lexical reranker only)

This tells us how much semantic embeddings improve retrieval before committing
to a full re-index (which takes ~8 min for MiniLM on MPS).

Usage:
    python evaluation/semantic_probe.py                     # MiniLM, alpha=0.5
    python evaluation/semantic_probe.py --model nomic       # nomic-embed
    python evaluation/semantic_probe.py --alpha 0.8         # more semantic weight
    python evaluation/semantic_probe.py --seed 3            # class hierarchy only
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.run_eval import (
    parse_questions,
    load_retrieval,
    _matches,
    hit_at_k,
    reciprocal_rank,
    SEED_NAMES,
    QUESTIONS_FILE,
)


# ── Semantic scorer ──────────────────────────────────────────────────────────

def load_semantic_model(model_name: str):
    """Returns (embed_query_fn, embed_doc_fn)."""
    if model_name == "nomic":
        from src.retrieval.embeddings import make_nomic_provider
        print("[probe] Loading nomic-embed-text-v1.5…", flush=True)
        p = make_nomic_provider(local_files_only=False)
        return p.embed_query, p.embed_doc
    else:
        from src.retrieval.embeddings import SentenceTransformersProvider
        mn = model_name if "/" in model_name else f"sentence-transformers/{model_name}"
        print(f"[probe] Loading {mn}…", flush=True)
        p = SentenceTransformersProvider(model_name=mn)
        return p.embed, p.embed


def cosine(a: List[float], b: List[float]) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Evaluation ───────────────────────────────────────────────────────────────

def run_probe(
    questions: List[Dict],
    searcher,
    reranker,
    embed_query,
    embed_doc,
    wide_k: int = 50,
    top_k: int  = 5,
    alpha: float = 0.5,
    seed_filter: Optional[int] = None,
) -> Tuple[Dict, Dict]:
    """Returns (baseline_results, semantic_results)."""
    if seed_filter is not None:
        questions = [q for q in questions if q["seed"] == seed_filter]

    base_hits = base_rr = sem_hits = sem_rr = 0.0
    base_per: Dict[int, Dict] = {}
    sem_per:  Dict[int, Dict] = {}
    total = len(questions)

    for i, item in enumerate(questions, 1):
        if i % 25 == 0:
            print(f"  {i}/{total}…", flush=True)

        q      = item["query"]
        exp    = item["expected"]
        seed   = item["seed"]
        for d in (base_per, sem_per):
            d.setdefault(seed, {"hits": 0, "rr": 0.0, "total": 0})

        # ── Hashing + lexical baseline ──────────────────────────────────────
        raw    = searcher.search(q, user_tier=3)
        ranked = reranker.rerank(q, raw, top_m=wide_k)
        base_paths = [h["file_path"] for h in ranked[:top_k]]

        bh = int(hit_at_k(base_paths, exp, top_k))
        br = reciprocal_rank(base_paths, exp)
        base_hits += bh;  base_rr += br
        base_per[seed]["hits"]  += bh
        base_per[seed]["rr"]    += br
        base_per[seed]["total"] += 1

        # ── Semantic re-scoring ──────────────────────────────────────────────
        q_vec = embed_query(q)
        texts = [h.get("text") or h.get("file_path", "") for h in ranked]
        doc_vecs = [embed_doc(t) for t in texts]

        blended = []
        for h, dv in zip(ranked, doc_vecs):
            sem_score = cosine(q_vec, dv)
            lex_score = h.get("rerank_score", 0.0)
            # Normalise lexical score to [0,1] range roughly (max ~20)
            lex_norm  = min(lex_score / 20.0, 1.0)
            final     = alpha * sem_score + (1 - alpha) * lex_norm
            blended.append((final, h["file_path"]))

        blended.sort(reverse=True)
        sem_paths = [fp for _, fp in blended[:top_k]]

        sh = int(hit_at_k(sem_paths, exp, top_k))
        sr = reciprocal_rank(sem_paths, exp)
        sem_hits += sh;  sem_rr += sr
        sem_per[seed]["hits"]  += sh
        sem_per[seed]["rr"]    += sr
        sem_per[seed]["total"] += 1

    def _summary(hits, rr, per):
        return {
            "accuracy_at_k": hits / total if total else 0.0,
            "mrr":           rr   / total if total else 0.0,
            "per_seed": {
                s: {"acc": v["hits"] / v["total"], "mrr": v["rr"] / v["total"], "n": v["total"]}
                for s, v in sorted(per.items()) if v["total"]
            },
        }

    return _summary(base_hits, base_rr, base_per), _summary(sem_hits, sem_rr, sem_per)


# ── Report ────────────────────────────────────────────────────────────────────

def print_comparison(baseline: Dict, semantic: Dict, k: int = 5, alpha: float = 0.5):
    print()
    print("=" * 70)
    print("  Semantic Re-ranking Probe Results")
    print("=" * 70)
    print(f"  {'Metric':<30} {'Baseline':>12}  {'Semantic':>12}  {'Delta':>10}")
    print(f"  {'-'*30} {'-'*12}  {'-'*12}  {'-'*10}")

    def row(label, bv, sv):
        delta = sv - bv
        sign  = "+" if delta >= 0 else ""
        color = "\033[92m" if delta > 0.005 else ("\033[91m" if delta < -0.005 else "")
        rst   = "\033[0m"
        print(f"  {label:<30} {bv:>12.4f}  {sv:>12.4f}  {color}{sign}{delta:>+.4f}{rst}")

    row(f"Accuracy@{k} (mean)", baseline["accuracy_at_k"], semantic["accuracy_at_k"])
    row("MRR (mean)",           baseline["mrr"],           semantic["mrr"])
    print()

    all_seeds = sorted(set(baseline["per_seed"]) | set(semantic["per_seed"]))
    for s in all_seeds:
        name = SEED_NAMES.get(s, f"Seed {s}")
        bv = baseline["per_seed"].get(s, {})
        sv = semantic["per_seed"].get(s, {})
        if not bv or not sv:
            continue
        print(f"  Seed {s}  {name}")
        row(f"    Acc@{k}", bv["acc"], sv["acc"])
        row(f"    MRR",     bv["mrr"], sv["mrr"])

    print()
    print(f"  (semantic weight alpha={alpha})")
    print("=" * 70)
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",    default=str(ROOT / ".cis" / "index.db"))
    ap.add_argument("--k",     type=int,   default=5)
    ap.add_argument("--wide",  type=int,   default=50,  help="hashing candidate pool size")
    ap.add_argument("--alpha", type=float, default=0.5, help="semantic blend weight [0,1]")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2",
                    help="'nomic', a sentence-transformers model name, or HF repo id")
    ap.add_argument("--seed",  type=int,   default=None, help="restrict to one seed (1-5)")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[probe] DB not found: {db}", file=sys.stderr)
        sys.exit(1)

    print("[probe] Loading retrieval engine…", flush=True)
    searcher, reranker = load_retrieval(db)
    embed_query, embed_doc = load_semantic_model(args.model)

    questions = parse_questions(QUESTIONS_FILE)
    label = f"seed {args.seed}" if args.seed else "all seeds"
    print(f"[probe] Running {len(questions)} questions ({label}), wide_k={args.wide}…",
          flush=True)

    baseline, semantic = run_probe(
        questions, searcher, reranker,
        embed_query, embed_doc,
        wide_k=args.wide,
        top_k=args.k,
        alpha=args.alpha,
        seed_filter=args.seed,
    )

    print_comparison(baseline, semantic, k=args.k, alpha=args.alpha)


if __name__ == "__main__":
    main()
