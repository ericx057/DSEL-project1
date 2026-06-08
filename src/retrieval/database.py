from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from src.retrieval.embeddings import EmbeddingProvider

class UnifiedStore(ABC):
    @abstractmethod
    def vector_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    def graph_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        depth: int = 3,
        breadth: int = 50,
    ) -> List[Dict[str, Any]]:
        pass

class InMemoryUnifiedStore(UnifiedStore):
    def __init__(self, data: List[Dict[str, Any]]):
        self.data = data
        
    def vector_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        return [doc for doc in self.data if doc.get("tier", 0) <= user_tier]
        
    def graph_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        depth: int = 3,
        breadth: int = 50,
    ) -> List[Dict[str, Any]]:
        return [doc for doc in self.data if doc.get("tier", 0) <= user_tier]


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    repository: str
    file_path: str
    language: str
    text: str
    tier: int
    fidelity: str
    symbol_name: Optional[str] = None
    line_start: int = 1
    line_end: int = 1
    kind: str = "chunk"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdgeRecord:
    source_id: str
    target_id: str
    relationship: str


class HashingEmbeddingProvider:
    def __init__(self, dimensions: int = 128):
        if dimensions < 4:
            raise ValueError("dimensions must be >= 4")
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())


QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "artifact",
    "as",
    "at",
    "be",
    "by",
    "callee",
    "confirm",
    "contains",
    "correspond",
    "defined",
    "does",
    "file",
    "for",
    "from",
    "in",
    "indexed",
    "is",
    "it",
    "kind",
    "kinds",
    "of",
    "on",
    "or",
    "public",
    "repository",
    "symbol",
    "the",
    "to",
    "what",
    "where",
    "whether",
    "which",
    "with",
}


class SQLiteUnifiedStore(UnifiedStore):
    def __init__(self, db_path: str | Path, embedding_provider: Optional[EmbeddingProvider] = None):
        self.db_path = Path(db_path)
        self.embedding_provider = embedding_provider or HashingEmbeddingProvider()
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()
        # Embedding cache: loaded once, reused for every vector_search call.
        self._emb_cache: Optional[Dict[str, Any]] = None  # set by _ensure_emb_cache()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    text TEXT NOT NULL,
                    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
                    fidelity TEXT NOT NULL,
                    symbol_name TEXT,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_tier_repo ON artifacts(tier, repository)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_symbol ON artifacts(symbol_name)"
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, relationship),
                    FOREIGN KEY (source_id) REFERENCES artifacts(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES artifacts(id) ON DELETE CASCADE
                )
                """
            )
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_file_path ON artifacts(file_path)")

    _EMBED_BATCH = 64   # artifacts per embed_many call

    def upsert_artifacts(self, artifacts: Sequence[ArtifactRecord]) -> None:
        if not artifacts:
            return
        now = time.time()
        _SQL = """
            INSERT INTO artifacts (
                id, repository, file_path, language, text, tier, fidelity,
                symbol_name, line_start, line_end, kind, embedding, metadata, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                repository=excluded.repository,
                file_path=excluded.file_path,
                language=excluded.language,
                text=excluded.text,
                tier=excluded.tier,
                fidelity=excluded.fidelity,
                symbol_name=excluded.symbol_name,
                line_start=excluded.line_start,
                line_end=excluded.line_end,
                kind=excluded.kind,
                embedding=excluded.embedding,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at
        """
        with self._lock, self._connection:
            for i in range(0, len(artifacts), self._EMBED_BATCH):
                batch = artifacts[i : i + self._EMBED_BATCH]
                embeddings = self.embedding_provider.embed_many(
                    [a.text for a in batch]
                )
                self._connection.executemany(
                    _SQL,
                    [
                        (
                            a.artifact_id, a.repository, a.file_path, a.language,
                            a.text, a.tier, a.fidelity, a.symbol_name,
                            a.line_start, a.line_end, a.kind,
                            json.dumps(emb),
                            json.dumps(a.metadata, sort_keys=True),
                            now,
                        )
                        for a, emb in zip(batch, embeddings)
                    ],
                )
            self._emb_cache = None  # invalidate so next search rebuilds

    def upsert_edges(self, edges: Sequence[GraphEdgeRecord]) -> None:
        with self._lock, self._connection:
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO edges(source_id, target_id, relationship)
                VALUES (?, ?, ?)
                """,
                [(edge.source_id, edge.target_id, edge.relationship) for edge in edges],
            )

    def delete_repository(self, repository: str) -> None:
        with self._lock, self._connection:
            ids = [row["id"] for row in self._connection.execute("SELECT id FROM artifacts WHERE repository = ?", (repository,))]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                self._connection.execute(f"DELETE FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})", ids + ids)
            self._connection.execute("DELETE FROM artifacts WHERE repository = ?", (repository,))

    def _ensure_emb_cache(self) -> None:
        """Load all artifact embeddings into memory once for fast repeated vector_search calls."""
        if self._emb_cache is not None:
            return
        rows = list(self._connection.execute("SELECT id, tier, repository, embedding FROM artifacts"))
        ids = [r["id"] for r in rows]
        tiers = [r["tier"] for r in rows]
        repos = [r["repository"] for r in rows]
        if _NUMPY:
            matrix = np.array([json.loads(r["embedding"]) for r in rows], dtype=np.float32)
        else:
            matrix = [json.loads(r["embedding"]) for r in rows]
        self._emb_cache = {"ids": ids, "tiers": tiers, "repos": repos, "matrix": matrix}

    def invalidate_emb_cache(self) -> None:
        """Call after upsert_artifacts so the next search rebuilds the cache."""
        self._emb_cache = None

    def vector_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        self._ensure_emb_cache()
        cache = self._emb_cache
        assert cache is not None

        query_vec = self.embedding_provider.embed(query)
        query_terms = self._signal_terms(query)

        # Build boolean mask for tier + repo filter.
        ids = cache["ids"]
        tiers = cache["tiers"]
        repos = cache["repos"]
        matrix = cache["matrix"]

        if _NUMPY:
            if len(ids) == 0:
                return []
            qv = np.array(query_vec, dtype=np.float32)
            scores = matrix @ qv  # (N,) cosine similarities (pre-normalised embeddings)

            # Apply tier/repo filter and keyword bonus in one pass.
            repo_set = set(repo_scope) if repo_scope is not None else None
            results = []
            for i, (artifact_id, tier, repo, cos) in enumerate(zip(ids, tiers, repos, scores)):
                if tier > user_tier:
                    continue
                if repo_set is not None and repo not in repo_set:
                    continue
                results.append((float(cos), artifact_id))
        else:
            repo_set = set(repo_scope) if repo_scope is not None else None
            results = []
            for i, (artifact_id, tier, repo, emb) in enumerate(zip(ids, tiers, repos, matrix)):
                if tier > user_tier:
                    continue
                if repo_set is not None and repo not in repo_set:
                    continue
                cos = self._cosine(query_vec, emb)
                results.append((cos, artifact_id))

        results.sort(key=lambda x: x[0], reverse=True)
        top_ids = {aid for _, aid in results[:top_k * 4]}  # fetch a wider slice for keyword rerank

        # Fetch full rows for the top candidates only.
        if not top_ids:
            return []
        placeholders = ",".join("?" for _ in top_ids)
        rows = self._connection.execute(
            f"SELECT * FROM artifacts WHERE id IN ({placeholders})", list(top_ids)
        ).fetchall()

        scored = []
        score_map = {aid: cos for cos, aid in results}
        for row in rows:
            text = f"{row['symbol_name'] or ''} {row['text']}".lower()
            keyword_score = sum(1 for term in query_terms if term in text) * 0.05
            item = self._row_to_dict(row)
            item["score"] = score_map.get(row["id"], 0.0) + keyword_score
            scored.append(item)

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def graph_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        depth: int = 3,
        breadth: int = 50,
    ) -> List[Dict[str, Any]]:
        allowed = {row["id"]: row for row in self._select_allowed_artifacts(user_tier, repo_scope)}
        if not allowed:
            return []
        anchors = self._find_anchor_ids(query, allowed)
        if not anchors:
            anchors = [item["id"] for item in self.vector_search(query, user_tier, repo_scope, top_k=3)]
        seen = set()
        queue = [(anchor, 0) for anchor in anchors if anchor in allowed]
        ordered_ids: List[str] = []
        while queue and len(ordered_ids) < breadth:
            artifact_id, current_depth = queue.pop(0)
            if artifact_id in seen or artifact_id not in allowed:
                continue
            seen.add(artifact_id)
            ordered_ids.append(artifact_id)
            if current_depth >= depth:
                continue
            for edge in self._outgoing_edges(artifact_id):
                if edge["target_id"] in allowed and edge["target_id"] not in seen:
                    queue.append((edge["target_id"], current_depth + 1))
        return [self._row_to_dict(allowed[artifact_id]) for artifact_id in ordered_ids]

    def list_edges(
        self,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        relationship: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        allowed_ids = {row["id"] for row in self._select_allowed_artifacts(user_tier, repo_scope)}
        if not allowed_ids:
            return []
        clauses = []
        params: List[Any] = []
        if relationship:
            clauses.append("relationship = ?")
            params.append(relationship)
        query = "SELECT source_id, target_id, relationship FROM edges"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        edges = []
        for row in self._connection.execute(query, params):
            if row["source_id"] in allowed_ids and row["target_id"] in allowed_ids:
                edges.append(dict(row))
        return edges

    def list_artifacts(
        self,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        return [self._row_to_dict(row) for row in self._select_allowed_artifacts(user_tier, repo_scope)]

    def get_artifacts_by_ids(self, artifact_ids: Sequence[str], user_tier: int) -> List[Dict[str, Any]]:
        if not artifact_ids:
            return []
        placeholders = ",".join("?" for _ in artifact_ids)
        rows = self._connection.execute(
            f"SELECT * FROM artifacts WHERE tier <= ? AND id IN ({placeholders})",
            [user_tier, *artifact_ids],
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # Matches explicit source file basenames: Document.cpp, GCS.h, sketch.py …
    _FILENAME_RE = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*\.(cpp|cxx|cc|c|h|hpp|hxx|py|pyx))\b"
    )
    # Matches C++ qualified symbols with at least one :: segment.
    _QUALIFIED_SYM_RE = re.compile(
        r"`?([A-Z][A-Za-z0-9_]*)(?:::[A-Za-z0-9_]+)+`?"
    )
    # Matches bare backtick-quoted identifiers starting with uppercase, length ≥ 2.
    _BACKTICK_CLASS_RE = re.compile(
        r"`([A-Z][A-Za-z0-9_]{1,})`"
    )

    def filename_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        max_per_file: int = 2,
    ) -> List[Dict[str, Any]]:
        """Return artifacts for source files referenced (directly or via C++ symbols) in the query.

        Three extraction passes:
        1. Explicit basenames — ``Document.cpp``, ``GCS.h``, ``Sketch.py``
        2. Qualified C++ symbols — ``ClassName::method`` → infer ``ClassName.cpp`` / ``ClassName.h``
        3. Bare backtick class names — `` `SketchObject` `` → infer ``SketchObject.h`` / ``.cpp``

        For any class name where the inferred filename produces no DB hit, falls back to a
        text-content LIKE search so that files like ``PropertyLinks.cpp`` are found even when
        the class ``PropertyLinkSub`` doesn't appear in the file name.
        """
        source_exts = (".cpp", ".cxx", ".cc", ".c", ".py")
        header_exts = (".h", ".hpp", ".hxx")
        all_exts = (*header_exts, *source_exts)  # headers first for hierarchy queries

        basenames: list[str] = [
            m.group(1).lower() for m in self._FILENAME_RE.finditer(query)
        ]

        # Track which class names to attempt text fallback for if filename lookup misses.
        class_names_for_text_fallback: list[str] = []

        for m in self._QUALIFIED_SYM_RE.finditer(query):
            full = m.group(0).strip("`")
            parts = full.split("::")
            # Add every uppercase-starting component — the reranker's overlap+file
            # scores will surface the right file even when multiple components map
            # to files (e.g. GCS::System → both GCS.h and SubSystem.cpp get fn_match,
            # but GCS.h wins on overlap; Gui::Document → both Gui*.h and Document.cpp
            # get fn_match, but Document.cpp wins on overlap for openCommand query).
            for part in parts:
                if not part or not part[0].isupper():
                    continue
                if part not in class_names_for_text_fallback:
                    class_names_for_text_fallback.append(part)
                for ext in all_exts:
                    candidate = f"{part.lower()}{ext}"
                    if candidate not in basenames:
                        basenames.append(candidate)

        for m in self._BACKTICK_CLASS_RE.finditer(query):
            cls = m.group(1)
            # Skip if already captured by qualified symbol regex.
            if cls not in class_names_for_text_fallback:
                class_names_for_text_fallback.append(cls)
            for ext in all_exts:
                candidate = f"{cls.lower()}{ext}"
                if candidate not in basenames:
                    basenames.append(candidate)

        results: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        file_counts: Dict[str, int] = {}
        files_found_by_name: set[str] = set()  # basenames that got filename hits

        def _add_rows(rows: list) -> None:
            for row in rows:
                if row["id"] in seen_ids:
                    continue
                fp = row["file_path"]
                if file_counts.get(fp, 0) >= max_per_file:
                    continue
                seen_ids.add(row["id"])
                file_counts[fp] = file_counts.get(fp, 0) + 1
                item = self._row_to_dict(row)
                item["score"] = 1.0
                item["_fn_match"] = True
                results.append(item)

        def _repo_clause() -> tuple[str, list]:
            if repo_scope is None:
                return "", []
            if not repo_scope:
                return " AND 1=0", []
            placeholders = ",".join("?" for _ in repo_scope)
            return f" AND repository IN ({placeholders})", list(repo_scope)

        repo_sql, repo_params = _repo_clause()
        kind_order = " ORDER BY CASE kind WHEN 'class' THEN 0 WHEN 'function' THEN 1 WHEN 'method' THEN 2 ELSE 3 END"

        for basename in dict.fromkeys(basenames):
            params: List[Any] = [user_tier, f"%{basename}"] + repo_params
            sql = f"SELECT * FROM artifacts WHERE tier <= ? AND LOWER(file_path) LIKE ?{repo_sql}{kind_order}"
            rows = self._connection.execute(sql, params).fetchall()
            if rows:
                files_found_by_name.add(basename)
            _add_rows(rows)

        # Text-content fallback: for each class name whose inferred filename had no DB hit,
        # search artifacts whose text contains the class name and whose path is a source file.
        for cls in dict.fromkeys(class_names_for_text_fallback):
            inferred = {f"{cls.lower()}{ext}" for ext in all_exts}
            if inferred & files_found_by_name:
                continue  # filename lookup already found this class
            params_t: List[Any] = [user_tier, f"%{cls}%"] + repo_params
            sql_t = (
                f"SELECT * FROM artifacts WHERE tier <= ? AND text LIKE ?{repo_sql}"
                " AND (LOWER(file_path) LIKE '%.cpp' OR LOWER(file_path) LIKE '%.h'"
                " OR LOWER(file_path) LIKE '%.py'){kind_order}".format(kind_order=kind_order)
            )
            rows = self._connection.execute(sql_t, params_t).fetchall()
            # If the class name appears in too many files it is a generic term
            # (e.g. "Visibility", "Base") — skip entirely to avoid flooding results.
            unique_files_in_fallback = len({r["file_path"] for r in rows})
            if unique_files_in_fallback > 8:
                continue
            # Cap text-fallback results more aggressively — they're lower-confidence.
            text_file_counts: Dict[str, int] = {}
            for row in rows:
                fp = row["file_path"]
                if text_file_counts.get(fp, 0) >= 2:
                    continue
                text_file_counts[fp] = text_file_counts.get(fp, 0) + 1
                if row["id"] in seen_ids:
                    continue
                if file_counts.get(fp, 0) >= max_per_file:
                    continue
                seen_ids.add(row["id"])
                file_counts[fp] = file_counts.get(fp, 0) + 1
                item = self._row_to_dict(row)
                item["score"] = 1.0
                # Weaker signal than filename match — text content may be coincidental.
                item["_text_match"] = True
                results.append(item)

        return results

    def _select_allowed_artifacts(
        self,
        user_tier: int,
        repo_scope: Optional[Sequence[str]],
    ) -> List[sqlite3.Row]:
        params: List[Any] = [user_tier]
        query = "SELECT * FROM artifacts WHERE tier <= ?"
        if repo_scope is not None:
            if not repo_scope:
                return []
            placeholders = ",".join("?" for _ in repo_scope)
            query += f" AND repository IN ({placeholders})"
            params.extend(repo_scope)
        return list(self._connection.execute(query, params))

    def _find_anchor_ids(self, query: str, allowed: Dict[str, sqlite3.Row]) -> List[str]:
        terms = self._signal_terms(query)
        anchors = []
        for artifact_id, row in allowed.items():
            haystack = " ".join(
                [
                    artifact_id,
                    row["symbol_name"] or "",
                    row["file_path"],
                    row["text"],
                    row["metadata"],
                ]
            ).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                anchors.append((score, artifact_id))
        anchors.sort(key=lambda item: (-item[0], item[1]))
        return [artifact_id for _, artifact_id in anchors]

    @staticmethod
    def _signal_terms(query: str) -> set[str]:
        return {
            term
            for term in HashingEmbeddingProvider._tokens(query)
            if term not in QUERY_STOPWORDS and len(term) > 1
        }

    def _outgoing_edges(self, artifact_id: str) -> List[sqlite3.Row]:
        priority = {"calls": 0, "defines": 1, "imports": 2, "inherits": 3, "uses": 4, "bridges": 5}
        rows = list(
            self._connection.execute(
                "SELECT source_id, target_id, relationship FROM edges WHERE source_id = ?",
                (artifact_id,),
            )
        )
        rows.sort(key=lambda row: priority.get(row["relationship"], 10))
        return rows

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if not left or not right:
            return 0.0
        return float(sum(a * b for a, b in zip(left, right)))

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "repository": row["repository"],
            "file_path": row["file_path"],
            "language": row["language"],
            "text": row["text"],
            "tier": row["tier"],
            "fidelity": row["fidelity"],
            "symbol_name": row["symbol_name"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "kind": row["kind"],
            "metadata": json.loads(row["metadata"]),
        }
