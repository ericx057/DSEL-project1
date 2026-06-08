#!/usr/bin/env python3
"""
DSEL Performance Report Generator
===================================
Runs a timed evaluation over the 250-question UMMDB benchmark and produces
a multi-page PDF report with accuracy, MRR, and latency figures.

Usage:
    python evaluation/generate_report.py [--db PATH] [--out report.pdf]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.run_eval import (
    parse_questions,
    _matches,
    hit_at_k,
    reciprocal_rank,
    SEED_NAMES,
    QUESTIONS_FILE,
)

# ── Palette ──────────────────────────────────────────────────────────────────

BLUE   = "#0a84ff"
GREEN  = "#30d158"
ORANGE = "#ff9f0a"
RED    = "#ff453a"
PURPLE = "#bf5af2"
GRAY   = "#8e8e93"
BG     = "#1c1c1e"
FG     = "#f5f5f7"
GRID   = "#3a3a3c"

SEED_COLORS = [BLUE, GREEN, ORANGE, RED, PURPLE]

plt.rcParams.update({
    "figure.facecolor":  BG,
    "axes.facecolor":    BG,
    "axes.edgecolor":    GRID,
    "axes.labelcolor":   FG,
    "axes.titlecolor":   FG,
    "xtick.color":       GRAY,
    "ytick.color":       GRAY,
    "grid.color":        GRID,
    "grid.linewidth":    0.5,
    "text.color":        FG,
    "font.family":       "sans-serif",
    "font.size":         9,
    "axes.titlesize":    11,
    "axes.labelsize":    9,
    "legend.facecolor":  "#2c2c2e",
    "legend.edgecolor":  GRID,
    "legend.labelcolor": FG,
    "figure.dpi":        150,
})

# ── Timed retrieval ──────────────────────────────────────────────────────────

def load_retrieval_timed(db_path: Path):
    from src.retrieval.database import SQLiteUnifiedStore, HashingEmbeddingProvider
    from src.retrieval.hybrid import HybridSearcher
    from src.retrieval.reranker import LexicalReranker

    provider = HashingEmbeddingProvider()
    store    = SQLiteUnifiedStore(db_path, provider)
    searcher = HybridSearcher(store, lambda_ratio=0.6, vector_top_k=20,
                              graph_depth=3, graph_breadth=50)
    reranker = LexicalReranker()

    # Warm the embedding cache and measure build time
    t0 = time.perf_counter()
    store._ensure_emb_cache()
    cache_build_s = time.perf_counter() - t0
    n_artifacts   = len(store._emb_cache["ids"])

    return searcher, reranker, store, cache_build_s, n_artifacts


def retrieve_timed(
    query: str, searcher, reranker, top_k: int
) -> Tuple[List[str], float, float]:
    """Returns (file_paths, search_ms, rerank_ms)."""
    t0   = time.perf_counter()
    hits = searcher.search(query, user_tier=3)
    search_ms = (time.perf_counter() - t0) * 1000

    t1     = time.perf_counter()
    ranked = reranker.rerank(query, hits, top_m=top_k)
    rerank_ms = (time.perf_counter() - t1) * 1000

    return [h["file_path"] for h in ranked], search_ms, rerank_ms


# ── Evaluation with timing ───────────────────────────────────────────────────

def run_timed_eval(
    questions: List[Dict],
    searcher, reranker,
    k: int = 5,
) -> Dict[str, Any]:
    total       = len(questions)
    hits        = 0
    rr_sum      = 0.0
    per_seed: Dict[int, Dict] = {}
    failures    : List[Dict]  = []
    search_ms_all  : List[float] = []
    rerank_ms_all  : List[float] = []
    total_ms_all   : List[float] = []
    per_seed_lat: Dict[int, List[float]] = {}

    for item in questions:
        s = item["seed"]
        per_seed.setdefault(s, {"hits": 0, "rr": 0.0, "total": 0})
        per_seed_lat.setdefault(s, [])

        t_start = time.perf_counter()
        paths, srch_ms, rnk_ms = retrieve_timed(
            item["query"], searcher, reranker, k
        )
        total_ms = (time.perf_counter() - t_start) * 1000

        search_ms_all.append(srch_ms)
        rerank_ms_all.append(rnk_ms)
        total_ms_all.append(total_ms)
        per_seed_lat[s].append(total_ms)

        h  = hit_at_k(paths, item["expected"], k)
        rr = reciprocal_rank(paths, item["expected"])

        if not h:
            failures.append({
                "query":    item["query"][:80],
                "expected": item["expected"],
                "got":      paths[:3],
                "seed":     s,
            })

        hits             += int(h)
        rr_sum           += rr
        per_seed[s]["hits"]  += int(h)
        per_seed[s]["rr"]    += rr
        per_seed[s]["total"] += 1

    seed_summary = {
        s: {
            "acc": v["hits"] / v["total"],
            "mrr": v["rr"]   / v["total"],
            "n":   v["total"],
            "lat_ms": per_seed_lat[s],
        }
        for s, v in sorted(per_seed.items())
        if v["total"]
    }

    return {
        "total":           total,
        "hits":            hits,
        "accuracy_at_k":   hits / total if total else 0.0,
        "mrr":             rr_sum / total if total else 0.0,
        "k":               k,
        "per_seed":        seed_summary,
        "failures":        failures,
        "search_ms":       search_ms_all,
        "rerank_ms":       rerank_ms_all,
        "total_ms":        total_ms_all,
    }


# ── Figures ──────────────────────────────────────────────────────────────────

def _bar_label(ax, bars, fmt="{:.3f}"):
    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + 0.005, fmt.format(h),
            ha="center", va="bottom", fontsize=8, color=FG,
        )


def fig_accuracy_mrr(results: Dict) -> plt.Figure:
    seeds  = sorted(results["per_seed"].keys())
    names  = [SEED_NAMES.get(s, f"Seed {s}") for s in seeds]
    accs   = [results["per_seed"][s]["acc"] for s in seeds]
    mrrs   = [results["per_seed"][s]["mrr"] for s in seeds]
    mean_acc = results["accuracy_at_k"]
    mean_mrr = results["mrr"]

    x     = np.arange(len(seeds) + 1)
    width = 0.35
    xlabels = names + ["MEAN"]
    acc_vals = accs + [mean_acc]
    mrr_vals = mrrs + [mean_mrr]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    b1 = ax.bar(x - width / 2, acc_vals, width, label="Accuracy@5",
                color=BLUE, alpha=0.9, zorder=3)
    b2 = ax.bar(x + width / 2, mrr_vals, width, label="MRR",
                color=GREEN, alpha=0.9, zorder=3)

    _bar_label(ax, b1)
    _bar_label(ax, b2)

    ax.axhline(0.95, color=ORANGE, linewidth=1, linestyle="--",
               label="Target (0.95)", zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score")
    ax.set_title("Accuracy@5 and MRR per Seed Dataset")
    ax.legend(loc="lower right")
    ax.grid(axis="y", zorder=0)
    fig.tight_layout()
    return fig


def fig_latency_histogram(results: Dict) -> plt.Figure:
    total_ms = results["total_ms"]
    srch_ms  = results["search_ms"]
    rnk_ms   = results["rerank_ms"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    # Histogram
    ax = axes[0]
    ax.hist(total_ms, bins=30, color=BLUE, alpha=0.85, edgecolor="none", zorder=3)
    ax.axvline(statistics.mean(total_ms), color=ORANGE, linewidth=1.5,
               linestyle="--", label=f"Mean {statistics.mean(total_ms):.1f} ms", zorder=4)
    ax.axvline(statistics.median(total_ms), color=GREEN, linewidth=1.5,
               linestyle=":",  label=f"Median {statistics.median(total_ms):.1f} ms", zorder=4)
    ax.set_xlabel("End-to-End Query Latency (ms)")
    ax.set_ylabel("Count")
    ax.set_title("Query Latency Distribution  (n=250)")
    ax.legend()
    ax.grid(axis="y", zorder=0)

    # Box plot per seed
    ax2 = axes[1]
    per_seed = results["per_seed"]
    seeds    = sorted(per_seed.keys())
    data     = [per_seed[s]["lat_ms"] for s in seeds]
    bp = ax2.boxplot(
        data, patch_artist=True, notch=False,
        medianprops={"color": FG, "linewidth": 1.5},
        whiskerprops={"color": GRAY},
        capprops={"color": GRAY},
        flierprops={"marker": "o", "markersize": 2, "markerfacecolor": GRAY,
                    "linestyle": "none"},
    )
    for patch, col in zip(bp["boxes"], SEED_COLORS):
        patch.set_facecolor(col)
        patch.set_alpha(0.8)
    ax2.set_xticks(range(1, len(seeds) + 1))
    ax2.set_xticklabels([SEED_NAMES.get(s, f"S{s}") for s in seeds],
                        rotation=20, ha="right", fontsize=8)
    ax2.set_ylabel("Latency (ms)")
    ax2.set_title("Latency by Seed Dataset")
    ax2.grid(axis="y", zorder=0)

    fig.tight_layout()
    return fig


def fig_retrieval_breakdown(results: Dict) -> plt.Figure:
    srch_ms = results["search_ms"]
    rnk_ms  = results["rerank_ms"]
    total_ms = results["total_ms"]

    mean_srch  = statistics.mean(srch_ms)
    mean_rnk   = statistics.mean(rnk_ms)
    mean_total = statistics.mean(total_ms)
    mean_other = mean_total - mean_srch - mean_rnk

    labels = ["Hybrid\nSearch", "Lexical\nRerank", "Overhead\n(I/O + parse)"]
    values = [mean_srch, mean_rnk, max(0.0, mean_other)]
    colors = [BLUE, GREEN, ORANGE]

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))

    ax = axes[0]
    bars = ax.bar(labels, values, color=colors, alpha=0.9, width=0.5, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                v + 0.1, f"{v:.2f} ms",
                ha="center", va="bottom", fontsize=9, color=FG)
    ax.set_ylabel("Mean time (ms)")
    ax.set_title("Mean Retrieval Stage Breakdown")
    ax.grid(axis="y", zorder=0)

    ax2 = axes[1]
    wedges, texts, autotexts = ax2.pie(
        values, labels=labels, colors=colors,
        autopct="%1.1f%%", startangle=90,
        pctdistance=0.75,
        wedgeprops={"linewidth": 0.5, "edgecolor": BG},
        textprops={"color": FG, "fontsize": 8},
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color(BG)
    ax2.set_title("Latency Composition")

    fig.suptitle(
        f"Total mean latency: {mean_total:.2f} ms / query",
        fontsize=10, color=FG,
    )
    fig.tight_layout()
    return fig


def fig_amortized_encoding(cache_build_s: float, n_artifacts: int) -> plt.Figure:
    us_per_artifact = (cache_build_s / max(n_artifacts, 1)) * 1e6
    batch_sizes     = [100, 500, 1000, 5000, 10000, 50000, 100000]
    batch_times_ms  = [(b * us_per_artifact / 1000) for b in batch_sizes]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax = axes[0]
    ax.plot([str(b) for b in batch_sizes], batch_times_ms,
            color=PURPLE, linewidth=2, marker="o", markersize=5, zorder=3)
    ax.fill_between(range(len(batch_sizes)), batch_times_ms,
                    color=PURPLE, alpha=0.15, zorder=2)
    ax.axvline(
        [str(b) for b in batch_sizes].index(
            str(min(batch_sizes, key=lambda b: abs(b - n_artifacts)))
        ),
        color=ORANGE, linewidth=1.5, linestyle="--",
        label=f"Current corpus (~{n_artifacts:,})", zorder=4,
    )
    ax.set_xlabel("Corpus size (artifacts)")
    ax.set_ylabel("Cache build time (ms)")
    ax.set_title("Amortized Numpy Cache Build Time vs Corpus Size")
    ax.legend()
    ax.grid(zorder=0)
    ax.set_xticks(range(len(batch_sizes)))
    ax.set_xticklabels([str(b) for b in batch_sizes], rotation=30, ha="right")

    ax2 = axes[1]
    ax2.bar(
        ["Cache Build\n(one-shot)", "Per-Query\n(amortized)"],
        [cache_build_s * 1000, us_per_artifact / 1000],
        color=[PURPLE, BLUE], alpha=0.9, width=0.4, zorder=3,
    )
    ax2.set_ylabel("Time (ms)")
    ax2.set_title(
        f"Cache Build: {cache_build_s*1000:.1f} ms  |  "
        f"Amortized: {us_per_artifact:.2f} µs/artifact"
    )
    ax2.grid(axis="y", zorder=0)

    fig.tight_layout()
    return fig


def fig_summary_table(results: Dict, cache_build_s: float, n_artifacts: int) -> plt.Figure:
    total_ms = results["total_ms"]
    srch_ms  = results["search_ms"]
    rnk_ms   = results["rerank_ms"]

    rows = [
        ("Corpus size",           f"{n_artifacts:,} artifacts"),
        ("Benchmark size",        f"{results['total']} questions × 5 seeds"),
        ("",                      ""),
        ("Accuracy@5 (mean)",     f"{results['accuracy_at_k']:.4f}"),
        ("MRR (mean)",            f"{results['mrr']:.4f}"),
        ("",                      ""),
    ]
    for s, v in sorted(results["per_seed"].items()):
        name = SEED_NAMES.get(s, f"Seed {s}")
        rows.append((f"  Seed {s}: {name}", f"Acc={v['acc']:.3f}  MRR={v['mrr']:.3f}"))
    rows += [
        ("",                      ""),
        ("Mean query latency",    f"{statistics.mean(total_ms):.2f} ms"),
        ("Median query latency",  f"{statistics.median(total_ms):.2f} ms"),
        ("P95 query latency",     f"{np.percentile(total_ms, 95):.2f} ms"),
        ("P99 query latency",     f"{np.percentile(total_ms, 99):.2f} ms"),
        ("",                      ""),
        ("  Hybrid search (mean)",   f"{statistics.mean(srch_ms):.2f} ms"),
        ("  Lexical rerank (mean)",  f"{statistics.mean(rnk_ms):.2f} ms"),
        ("",                      ""),
        ("Cache build (one-shot)", f"{cache_build_s*1000:.1f} ms"),
        ("Amortized encode cost",  f"{(cache_build_s/max(n_artifacts,1))*1e6:.2f} µs/artifact"),
        ("Embedding backend",      "SHA-256 hashing (no GPU)"),
        ("Reranker",               "LexicalReranker (term overlap + symbol matching)"),
    ]

    fig, ax = plt.subplots(figsize=(8, len(rows) * 0.32 + 1.2))
    ax.axis("off")

    for i, (label, value) in enumerate(rows):
        y = 1 - (i + 0.5) / len(rows)
        if not label and not value:
            continue
        ax.text(0.02, y, label, transform=ax.transAxes,
                fontsize=9, color=GRAY if label.startswith("  ") else FG,
                va="center")
        ax.text(0.55, y, value, transform=ax.transAxes,
                fontsize=9, color=FG, va="center",
                fontfamily="monospace")
        if i % 2 == 0 and label:
            rect = plt.Rectangle(
                (0, y - 0.4 / len(rows)), 1, 0.8 / len(rows),
                transform=ax.transAxes, color="#2c2c2e", zorder=0,
            )
            ax.add_patch(rect)

    ax.set_title("DSEL Retrieval System — Performance Summary", fontsize=12, pad=12)
    fig.tight_layout()
    return fig


# ── Cover page ────────────────────────────────────────────────────────────────

def fig_cover() -> plt.Figure:
    fig = plt.figure(figsize=(8.5, 11))
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.text(0.5, 0.72, "DSEL",
            ha="center", fontsize=64, color=BLUE, fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.5, 0.63, "Document-Semantic Entity Lookup",
            ha="center", fontsize=16, color=FG, transform=ax.transAxes)
    ax.text(0.5, 0.56, "Retrieval System — Performance Report",
            ha="center", fontsize=13, color=GRAY, transform=ax.transAxes)

    import datetime
    today = datetime.date.today().strftime("%B %d, %Y")
    ax.text(0.5, 0.46, today,
            ha="center", fontsize=11, color=GRAY, transform=ax.transAxes)

    ax.text(0.5, 0.35,
            "FreeCAD codebase  ·  250-question UMMDB benchmark\n"
            "SHA-256 hashing embeddings  ·  SQLite vector store  ·  Lexical reranker",
            ha="center", fontsize=10, color=GRAY, transform=ax.transAxes,
            linespacing=1.8)
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",  default=str(ROOT / ".cis" / "index.db"))
    ap.add_argument("--k",   type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "report.pdf"))
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[report] DB not found: {db}", file=sys.stderr)
        sys.exit(1)

    print("[report] Loading retrieval engine…", flush=True)
    searcher, reranker, store, cache_build_s, n_artifacts = load_retrieval_timed(db)
    print(f"[report] Cache built in {cache_build_s*1000:.1f} ms  "
          f"({n_artifacts:,} artifacts, "
          f"{(cache_build_s/max(n_artifacts,1))*1e6:.2f} µs each)")

    questions = parse_questions(QUESTIONS_FILE)
    print(f"[report] Running timed eval on {len(questions)} questions…", flush=True)
    results = run_timed_eval(questions, searcher, reranker, k=args.k)

    mean_lat = statistics.mean(results["total_ms"])
    p95_lat  = np.percentile(results["total_ms"], 95)
    print(f"[report] Acc@{args.k}={results['accuracy_at_k']:.4f}  "
          f"MRR={results['mrr']:.4f}  "
          f"lat_mean={mean_lat:.1f} ms  lat_p95={p95_lat:.1f} ms")

    out = Path(args.out)
    print(f"[report] Writing PDF to {out}…", flush=True)

    with PdfPages(out) as pdf:
        for fig in [
            fig_cover(),
            fig_summary_table(results, cache_build_s, n_artifacts),
            fig_accuracy_mrr(results),
            fig_latency_histogram(results),
            fig_retrieval_breakdown(results),
            fig_amortized_encoding(cache_build_s, n_artifacts),
        ]:
            pdf.savefig(fig, facecolor=fig.get_facecolor())
            plt.close(fig)

        meta = pdf.infodict()
        meta["Title"]   = "DSEL Retrieval System — Performance Report"
        meta["Author"]  = "DSEL"
        meta["Subject"] = "FreeCAD UMMDB benchmark evaluation"

    print(f"[report] Done — {out}")


if __name__ == "__main__":
    main()
