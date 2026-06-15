from __future__ import annotations

import os
from pathlib import Path

from src.ingestion.indexer import RepositoryIndexer
from src.retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore
from src.retrieval.embeddings import (
    LocalTransformersEmbeddingProvider,
    SentenceTransformersProvider,
    make_nomic_provider,
)


def build_embedding_provider():
    backend = os.environ.get("CIS_EMBEDDING_BACKEND", "nomic").lower()
    if backend == "hashing":
        return HashingEmbeddingProvider()
    if backend == "sentence_transformers" or backend == "minilm":
        model = os.environ.get("CIS_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformersProvider(model_name=model)
    # default: nomic-embed-text-v1.5 with task prefixes
    model = os.environ.get("CIS_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5")
    if model == "nomic-ai/nomic-embed-text-v1.5":
        return make_nomic_provider(local_files_only=False)
    return LocalTransformersEmbeddingProvider(
        model_name=model,
        trust_remote_code=os.environ.get("CIS_EMBEDDING_TRUST_REMOTE_CODE", "false").lower() == "true",
        local_files_only=False,
    )


def main() -> int:
    data_dir = Path(os.environ.get("CIS_DATA_DIR", "/data")).resolve()
    repo_path = Path(os.environ["CIS_REPOSITORY_PATH"]).resolve()
    repo_name = os.environ.get("CIS_REPOSITORY_NAME", repo_path.name)
    data_dir.mkdir(parents=True, exist_ok=True)
    if not repo_path.exists() or not repo_path.is_dir():
        raise RuntimeError(f"CIS_REPOSITORY_PATH is not a directory: {repo_path}")

    store = SQLiteUnifiedStore(data_dir / "index.db", build_embedding_provider())
    report = RepositoryIndexer(store).index_repository(repo_name, repo_path)
    print(
        "indexed "
        f"repository={report.repository} "
        f"files_indexed={report.files_indexed} "
        f"files_skipped={report.files_skipped} "
        f"artifacts={report.artifacts_indexed} "
        f"edges={report.edges_indexed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
