#!/usr/bin/env python3
"""
UMMDB Retrieval Evaluation Harness
===================================
Measures Accuracy@K and MRR for the hybrid retrieval system against
the 5-seed FreeCAD benchmark defined in ummdb_eval_questions.md.

Usage:
    python evaluation/run_eval.py [--db PATH] [--k 5] [--seed 1-5]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUESTIONS_FILE = Path(__file__).parent / "ummdb_eval_questions.md"


# ── Question parser ────────────────────────────────────────────────────────

def parse_questions(md_path: Path) -> List[Dict[str, Any]]:
    text  = md_path.read_text()
    items: List[Dict[str, Any]] = []
    seed_idx = 0

    for block in re.split(r"^## Seed \d+", text, flags=re.MULTILINE):
        if "### Q" not in block:
            continue
        seed_idx += 1
        for entry in re.split(r"^### Q\d+", block, flags=re.MULTILINE)[1:]:
            q_m = re.search(r"\*\*Query\*\*:\s*(.+?)(?=\n\*\*|\Z)", entry, re.DOTALL)
            f_m = re.findall(r"`(src/[^`]+)`", entry)
            d_m = re.search(r"\*\*Difficulty\*\*:\s*(\d)", entry)
            h_m = re.search(r"\*\*Hops\*\*:\s*(.+)", entry)
            if not q_m or not f_m:
                continue
            items.append({
                "query":      q_m.group(1).strip().replace("\n", " "),
                "expected":   [f.strip() for f in f_m],
                "difficulty": int(d_m.group(1)) if d_m else 2,
                "hops":       h_m.group(1).strip() if h_m else "",
                "seed":       seed_idx,
            })
    return items


# ── Retrieval ──────────────────────────────────────────────────────────────

def load_retrieval(db_path: Path):
    from src.retrieval.database import SQLiteUnifiedStore, HashingEmbeddingProvider
    from src.retrieval.hybrid import HybridSearcher
    from src.retrieval.reranker import LexicalReranker

    store    = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider())
    searcher = HybridSearcher(store, lambda_ratio=0.6, vector_top_k=20,
                              graph_depth=3, graph_breadth=50)
    reranker = LexicalReranker()
    return searcher, reranker


def retrieve(query: str, searcher, reranker, top_k: int) -> List[str]:
    hits   = searcher.search(query, user_tier=3)
    ranked = reranker.rerank(query, hits, top_m=top_k)
    return [h["file_path"] for h in ranked]


# ── Metrics ────────────────────────────────────────────────────────────────

def _matches(retrieved_path: str, expected_path: str) -> bool:
    """Flexible path match: exact, substring, or filename equality."""
    return (
        expected_path in retrieved_path
        or retrieved_path in expected_path
        or Path(retrieved_path).name == Path(expected_path).name
    )


def hit_at_k(retrieved: List[str], expected: List[str], k: int) -> bool:
    return any(
        _matches(ret, exp)
        for ret in retrieved[:k]
        for exp in expected
    )


def reciprocal_rank(retrieved: List[str], expected: List[str]) -> float:
    for rank, ret in enumerate(retrieved, start=1):
        if any(_matches(ret, exp) for exp in expected):
            return 1.0 / rank
    return 0.0


# ── Evaluation loop ────────────────────────────────────────────────────────

def evaluate(
    questions: List[Dict],
    searcher,
    reranker,
    k: int = 5,
    seed_filter: Optional[int] = None,
) -> Dict[str, Any]:
    if seed_filter is not None:
        questions = [q for q in questions if q["seed"] == seed_filter]

    total    = len(questions)
    hits     = 0
    rr_sum   = 0.0
    per_seed: Dict[int, Dict] = {}
    failures: List[Dict]      = []

    for item in questions:
        s = item["seed"]
        per_seed.setdefault(s, {"hits": 0, "rr": 0.0, "total": 0})

        retrieved = retrieve(item["query"], searcher, reranker, k)
        h  = hit_at_k(retrieved, item["expected"], k)
        rr = reciprocal_rank(retrieved, item["expected"])

        if not h:
            failures.append({"query": item["query"][:80], "expected": item["expected"],
                             "got": retrieved[:3], "seed": s})

        hits              += int(h)
        rr_sum            += rr
        per_seed[s]["hits"]  += int(h)
        per_seed[s]["rr"]    += rr
        per_seed[s]["total"] += 1

    seed_summary = {
        s: {"acc": v["hits"] / v["total"], "mrr": v["rr"] / v["total"], "n": v["total"]}
        for s, v in sorted(per_seed.items())
        if v["total"]
    }

    return {
        "total":         total,
        "hits":          hits,
        "accuracy_at_k": hits / total if total else 0.0,
        "mrr":           rr_sum / total if total else 0.0,
        "k":             k,
        "per_seed":      seed_summary,
        "failures":      failures,
    }


# ── Report ─────────────────────────────────────────────────────────────────

SEED_NAMES = {
    1: "Call-chain tracing",
    2: "Event/property propagation",
    3: "Class hierarchy",
    4: "Serialization & I/O",
    5: "Algorithm internals",
}


def print_report(results: Dict, acc_baseline: float = 0.95, mrr_baseline: float = 0.95) -> bool:
    GREEN, RED, RST = "\033[92m", "\033[91m", "\033[0m"

    def pf(v, t):
        return f"{GREEN}PASS{RST}" if v >= t else f"{RED}FAIL{RST}"

    k, acc, mrr, n = results["k"], results["accuracy_at_k"], results["mrr"], results["total"]
    print()
    print("=" * 60)
    print("  UMMDB Retrieval Evaluation Report")
    print("=" * 60)
    print(f"  Questions   : {n}")
    print(f"  K           : {k}")
    print(f"  Accuracy@{k}  : {acc:.4f}  {pf(acc, acc_baseline)}  (need ≥ {acc_baseline})")
    print(f"  MRR         : {mrr:.4f}  {pf(mrr, mrr_baseline)}  (need ≥ {mrr_baseline})")
    print()
    print("  Per-seed breakdown:")
    for s, v in sorted(results["per_seed"].items()):
        name = SEED_NAMES.get(s, f"Seed {s}")
        print(f"    Seed {s}  {name:<30} Acc@{k}={v['acc']:.3f}  MRR={v['mrr']:.3f}  n={v['n']}")
    if results["failures"]:
        print()
        print(f"  Failures ({len(results['failures'])}):")
        for f in results["failures"][:5]:
            print(f"    [Seed {f['seed']}] {f['query']}")
            print(f"      expected : {f['expected']}")
            print(f"      got      : {f['got']}")
    overall = acc >= acc_baseline and mrr >= mrr_baseline
    print()
    print(f"  Verdict: {'PASS' if overall else 'FAIL'}")
    print("=" * 60)
    print()
    return overall


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",  default=str(ROOT / ".cis" / "index.db"))
    ap.add_argument("--k",   type=int, default=5)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--acc-baseline", type=float, default=0.95)
    ap.add_argument("--mrr-baseline", type=float, default=0.95)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[eval] DB not found: {db}\n       Run: python -m src.ingestion.cli index <repo>",
              file=sys.stderr)
        sys.exit(1)

    questions = parse_questions(QUESTIONS_FILE)
    print(f"[eval] {len(questions)} questions parsed from {QUESTIONS_FILE.name}")

    searcher, reranker = load_retrieval(db)
    results = evaluate(questions, searcher, reranker, k=args.k, seed_filter=args.seed)
    passed  = print_report(results, args.acc_baseline, args.mrr_baseline)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
