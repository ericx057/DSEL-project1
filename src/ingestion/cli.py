from __future__ import annotations

import os
from pathlib import Path

from src.ingestion.indexer import RepositoryIndexer
from src.retrieval.database import SQLiteUnifiedStore
from src.retrieval.embedding_config import build_embedding_provider


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
