#!/usr/bin/env python3
"""
Nomic Semantic Re-index Script
================================
Re-indexes a repository using nomic-embed-text-v1.5 (768-dim semantic embeddings)
into a separate SQLite database, leaving the hashing index untouched.

The nomic model weights (~274 MB) are downloaded automatically from HuggingFace
on the first run and cached in ~/.cache/huggingface/. Subsequent runs use the cache.

Hardware: uses MPS on Apple Silicon, CUDA on NVIDIA, CPU otherwise.

Usage:
    python scripts/reindex_nomic.py                        # default paths
    python scripts/reindex_nomic.py --src ./freecad-src    # repo to index
    python scripts/reindex_nomic.py --db .cis-nomic/index.db
    python scripts/reindex_nomic.py --batch 32             # smaller batch if OOM

After completion, point the desktop app or eval at the new index:
    DSEL_INDEX=.cis-nomic/index.db python -m src.desktop
    python evaluation/run_eval.py --db .cis-nomic/index.db
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _device_label() -> str:
    try:
        import torch
        if torch.backends.mps.is_available():
            return "MPS (Apple Silicon)"
        if torch.cuda.is_available():
            return f"CUDA ({torch.cuda.get_device_name(0)})"
    except Exception:
        pass
    return "CPU"


def _download_nomic() -> None:
    """Download nomic-embed-text-v1.5 weights if not already cached."""
    from huggingface_hub import snapshot_download, scan_cache_dir

    model_id = "nomic-ai/nomic-embed-text-v1.5"

    # Check if the full model (not just metadata) is already cached
    try:
        info = scan_cache_dir()
        for repo in info.repos:
            if repo.repo_id == model_id and repo.size_on_disk > 50 * 1024 * 1024:
                print(f"[nomic] Model already cached ({repo.size_on_disk // (1024**2)} MB)")
                return
    except Exception:
        pass

    print(f"[nomic] Downloading {model_id} (~274 MB)…", flush=True)
    snapshot_download(
        repo_id=model_id,
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
    )
    print("[nomic] Download complete.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src",   default=str(ROOT / "freecad-src"),
                    help="Path to repository source tree")
    ap.add_argument("--db",    default=str(ROOT / ".cis-nomic" / "index.db"),
                    help="Output SQLite database path")
    ap.add_argument("--name",  default="freecad",
                    help="Repository name tag stored in index")
    ap.add_argument("--batch", type=int, default=64,
                    help="Embedding batch size (reduce if OOM, e.g. --batch 16)")
    ap.add_argument("--skip-download", action="store_true",
                    help="Skip model download check (assumes weights are already cached)")
    args = ap.parse_args()

    src = Path(args.src)
    db  = Path(args.db)

    if not src.exists() or not src.is_dir():
        print(f"[nomic] Source not found: {src}", file=sys.stderr)
        print(f"        Run setup.sh first, or set --src to your FreeCAD clone.",
              file=sys.stderr)
        return 1

    print(f"[nomic] Device      : {_device_label()}")
    print(f"[nomic] Source      : {src}")
    print(f"[nomic] Output DB   : {db}")
    print(f"[nomic] Batch size  : {args.batch}")
    print()

    if not args.skip_download:
        _download_nomic()

    # Load embedding provider
    print("[nomic] Loading nomic-embed-text-v1.5…", flush=True)
    from src.retrieval.embeddings import make_nomic_provider
    from src.retrieval.database import SQLiteUnifiedStore

    provider = make_nomic_provider(local_files_only=False)

    # Warm the model with a dummy call
    _ = provider.embed_query("warm up")
    print("[nomic] Model loaded and warmed.")

    # Patch batch size on the store before indexing
    db.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteUnifiedStore(db, provider)
    store._EMBED_BATCH = args.batch

    # Run indexer with progress tracking
    from src.ingestion.indexer import RepositoryIndexer

    print(f"\n[nomic] Starting indexing of {src}…")
    print(       "        This typically takes 8–20 min on Apple Silicon.")
    print(       "        Progress is shown every 1 000 artifacts.\n", flush=True)

    t0     = time.perf_counter()
    report = RepositoryIndexer(store).index_repository(args.name, src)
    elapsed = time.perf_counter() - t0

    print()
    print("=" * 60)
    print("  Nomic Re-index Complete")
    print("=" * 60)
    print(f"  Repository   : {report.repository}")
    print(f"  Files indexed: {report.files_indexed}")
    print(f"  Files skipped: {report.files_skipped}")
    print(f"  Artifacts    : {report.artifacts_indexed:,}")
    print(f"  Graph edges  : {report.edges_indexed:,}")
    print(f"  Elapsed      : {elapsed/60:.1f} min")
    if report.artifacts_indexed:
        ms_each = elapsed * 1000 / report.artifacts_indexed
        print(f"  Throughput   : {ms_each:.2f} ms/artifact")
    print(f"  Index path   : {db}")
    print("=" * 60)
    print()
    print("To run the desktop app with the nomic index:")
    print(f"  DSEL_INDEX={db} python -m src.desktop")
    print()
    print("To run the benchmark with the nomic index:")
    print(f"  python evaluation/run_eval.py --db {db}")
    print()
    print("To run the semantic probe comparison:")
    print(f"  python evaluation/semantic_probe.py --alpha 0.6")
    print(f"  python evaluation/run_eval.py --db {db}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
