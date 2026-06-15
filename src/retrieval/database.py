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
        self._emb_cache: Optional[Dict[str, Any]] = None

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

    _EMBED_BATCH = 64

    def upsert_artifacts(self, artifacts: Sequence[ArtifactRecord]) -> None:
        if not artifacts:
            return
        now = time.time()
        sql = """
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
            for index in range(0, len(artifacts), self._EMBED_BATCH):
                batch = artifacts[index : index + self._EMBED_BATCH]
                embeddings = self.embedding_provider.embed_many([artifact.text for artifact in batch])
                self._connection.executemany(
                    sql,
                    [
                        (
                            artifact.artifact_id,
                            artifact.repository,
                            artifact.file_path,
                            artifact.language,
                            artifact.text,
                            artifact.tier,
                            artifact.fidelity,
                            artifact.symbol_name,
                            artifact.line_start,
                            artifact.line_end,
                            artifact.kind,
                            json.dumps(embedding),
                            json.dumps(artifact.metadata, sort_keys=True),
                            now,
                        )
                        for artifact, embedding in zip(batch, embeddings)
                    ],
                )
            self._emb_cache = None

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
                for chunk in self._chunks(ids, self._sqlite_variable_limit()):
                    placeholders = ",".join("?" for _ in chunk)
                    self._connection.execute(f"DELETE FROM edges WHERE source_id IN ({placeholders})", chunk)
                    self._connection.execute(f"DELETE FROM edges WHERE target_id IN ({placeholders})", chunk)
            self._connection.execute("DELETE FROM artifacts WHERE repository = ?", (repository,))
            self._emb_cache = None

    def _sqlite_variable_limit(self) -> int:
        if hasattr(self._connection, "getlimit"):
            return max(1, min(500, self._connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)))
        return 500

    @staticmethod
    def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
        for index in range(0, len(values), size):
            yield values[index : index + size]

    def _ensure_emb_cache(self) -> None:
        if self._emb_cache is not None:
            return
        rows = list(self._connection.execute("SELECT id, tier, repository, embedding FROM artifacts"))
        ids = [row["id"] for row in rows]
        tiers = [row["tier"] for row in rows]
        repos = [row["repository"] for row in rows]
        if _NUMPY:
            matrix = np.array([json.loads(row["embedding"]) for row in rows], dtype=np.float32)
        else:
            matrix = [json.loads(row["embedding"]) for row in rows]
        self._emb_cache = {"ids": ids, "tiers": tiers, "repos": repos, "matrix": matrix}

    def invalidate_emb_cache(self) -> None:
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

        query_embedding = self.embedding_provider.embed(query)
        ids = cache["ids"]
        tiers = cache["tiers"]
        repos = cache["repos"]
        matrix = cache["matrix"]
        repo_set = set(repo_scope) if repo_scope is not None else None

        if _NUMPY:
            if len(ids) == 0:
                return []
            scores = matrix @ np.array(query_embedding, dtype=np.float32)
            candidates = [
                (float(cosine), artifact_id)
                for artifact_id, tier, repository, cosine in zip(ids, tiers, repos, scores)
                if tier <= user_tier and (repo_set is None or repository in repo_set)
            ]
        else:
            candidates = [
                (self._cosine(query_embedding, embedding), artifact_id)
                for artifact_id, tier, repository, embedding in zip(ids, tiers, repos, matrix)
                if tier <= user_tier and (repo_set is None or repository in repo_set)
            ]

        candidates.sort(key=lambda item: item[0], reverse=True)
        candidate_ids = [artifact_id for _, artifact_id in candidates[: top_k * 4]]
        if not candidate_ids:
            return []
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = self._connection.execute(
            f"SELECT * FROM artifacts WHERE id IN ({placeholders})",
            candidate_ids,
        ).fetchall()
        cosine_scores = {artifact_id: score for score, artifact_id in candidates}

        scored = []
        for row in rows:
            item = self._row_to_dict(row)
            item["score"] = cosine_scores.get(row["id"], 0.0) + self._lexical_score(query, row)
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
            for neighbor_id in self._neighbor_ids(artifact_id):
                if neighbor_id in allowed and neighbor_id not in seen:
                    queue.append((neighbor_id, current_depth + 1))
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

    _FILENAME_RE = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*\.(cpp|cxx|cc|c|h|hpp|hxx|py|pyx))\b"
    )
    _QUALIFIED_SYM_RE = re.compile(r"`?([A-Z][A-Za-z0-9_]*)(?:::[A-Za-z0-9_]+)+`?")
    _BACKTICK_CLASS_RE = re.compile(r"`([A-Z][A-Za-z0-9_]{1,})`")

    def filename_search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
        max_per_file: int = 2,
    ) -> List[Dict[str, Any]]:
        source_exts = (".cpp", ".cxx", ".cc", ".c", ".py")
        header_exts = (".h", ".hpp", ".hxx")
        all_exts = (*header_exts, *source_exts)

        basenames = [match.group(1).lower() for match in self._FILENAME_RE.finditer(query)]
        class_names_for_text_fallback: List[str] = []

        for match in self._QUALIFIED_SYM_RE.finditer(query):
            for part in match.group(0).strip("`").split("::"):
                if not part or not part[0].isupper():
                    continue
                if part not in class_names_for_text_fallback:
                    class_names_for_text_fallback.append(part)
                for extension in all_exts:
                    candidate = f"{part.lower()}{extension}"
                    if candidate not in basenames:
                        basenames.append(candidate)

        for match in self._BACKTICK_CLASS_RE.finditer(query):
            class_name = match.group(1)
            if class_name not in class_names_for_text_fallback:
                class_names_for_text_fallback.append(class_name)
            for extension in all_exts:
                candidate = f"{class_name.lower()}{extension}"
                if candidate not in basenames:
                    basenames.append(candidate)

        repo_sql, repo_params = self._repo_clause(repo_scope)
        kind_order = " ORDER BY CASE kind WHEN 'class' THEN 0 WHEN 'function' THEN 1 WHEN 'method' THEN 2 ELSE 3 END"
        results: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        file_counts: Dict[str, int] = {}
        files_found_by_name: set[str] = set()

        def add_rows(rows: Sequence[sqlite3.Row], marker: str) -> None:
            for row in rows:
                if row["id"] in seen_ids:
                    continue
                file_path = row["file_path"]
                if file_counts.get(file_path, 0) >= max_per_file:
                    continue
                seen_ids.add(row["id"])
                file_counts[file_path] = file_counts.get(file_path, 0) + 1
                item = self._row_to_dict(row)
                item["score"] = 1.0
                item[marker] = True
                results.append(item)

        for basename in dict.fromkeys(basenames):
            params: List[Any] = [user_tier, f"%{basename}", *repo_params]
            rows = self._connection.execute(
                f"SELECT * FROM artifacts WHERE tier <= ? AND LOWER(file_path) LIKE ?{repo_sql}{kind_order}",
                params,
            ).fetchall()
            if rows:
                files_found_by_name.add(basename)
            add_rows(rows, "_fn_match")

        for class_name in dict.fromkeys(class_names_for_text_fallback):
            inferred = {f"{class_name.lower()}{extension}" for extension in all_exts}
            if inferred & files_found_by_name:
                continue
            params = [user_tier, f"%{class_name}%", *repo_params]
            rows = self._connection.execute(
                f"""
                SELECT * FROM artifacts
                WHERE tier <= ? AND text LIKE ?{repo_sql}
                  AND (
                    LOWER(file_path) LIKE '%.cpp'
                    OR LOWER(file_path) LIKE '%.cxx'
                    OR LOWER(file_path) LIKE '%.cc'
                    OR LOWER(file_path) LIKE '%.c'
                    OR LOWER(file_path) LIKE '%.h'
                    OR LOWER(file_path) LIKE '%.hpp'
                    OR LOWER(file_path) LIKE '%.hxx'
                    OR LOWER(file_path) LIKE '%.py'
                  )
                {kind_order}
                """,
                params,
            ).fetchall()
            if len({row["file_path"] for row in rows}) > 8:
                continue
            add_rows(rows, "_text_match")

        return results

    @staticmethod
    def _repo_clause(repo_scope: Optional[Sequence[str]]) -> tuple[str, List[str]]:
        if repo_scope is None:
            return "", []
        if not repo_scope:
            return " AND 1=0", []
        placeholders = ",".join("?" for _ in repo_scope)
        return f" AND repository IN ({placeholders})", list(repo_scope)

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
        terms = set(self._query_terms(query))
        anchors: List[tuple[float, str]] = []
        for artifact_id, row in allowed.items():
            haystack = self._searchable_text(row)
            if any(term in haystack for term in terms):
                anchors.append((self._lexical_score(query, row), artifact_id))
        anchors.sort(key=lambda item: (-item[0], item[1]))
        return [artifact_id for _, artifact_id in anchors]

    def _neighbor_ids(self, artifact_id: str) -> List[str]:
        priority = {
            "references": 0,
            "validated-by": 1,
            "calls": 2,
            "defines": 3,
            "imports": 4,
            "inherits": 5,
            "uses": 6,
            "bridges": 7,
        }
        rows = list(
            self._connection.execute(
                """
                SELECT source_id, target_id, relationship FROM edges
                WHERE source_id = ? OR target_id = ?
                """,
                (artifact_id, artifact_id),
            )
        )
        rows.sort(key=lambda row: priority.get(row["relationship"], 10))
        neighbor_ids: List[str] = []
        for row in rows:
            neighbor_id = row["target_id"] if row["source_id"] == artifact_id else row["source_id"]
            if neighbor_id not in neighbor_ids:
                neighbor_ids.append(neighbor_id)
        return neighbor_ids

    @classmethod
    def _lexical_score(cls, query: str, row: sqlite3.Row) -> float:
        searchable = cls._searchable_text(row)
        file_path = row["file_path"].lower()
        basename = Path(row["file_path"]).name.lower()
        suffix = Path(row["file_path"]).suffix.lower()
        score = 0.0

        for term in cls._query_terms(query):
            if term in searchable:
                score += 0.08
            score += cls._path_token_score(term, file_path)

        for literal in cls._query_literals(query):
            literal = literal.lower()
            if not literal:
                continue
            if literal == file_path:
                score += 5.0
            elif literal == basename:
                score += 3.0
            elif literal.endswith("/") and literal in file_path:
                score += 0.2
            elif literal in file_path:
                score += 1.5
            elif literal in searchable:
                score += 0.8
            if literal.startswith(".") and literal == suffix:
                score += 2.0

        for path_like in cls._path_like_terms(query):
            if path_like == file_path:
                score += 5.0
            elif path_like == basename:
                score += 3.0
            elif path_like.endswith("/") and path_like in file_path:
                score += 0.2
            elif path_like in file_path:
                score += 1.5
            elif path_like in searchable:
                score += 0.8
            if path_like.startswith(".") and path_like == suffix:
                score += 2.0

        query_terms = cls._query_terms(query)
        if "schema" in query_terms and not cls._is_policy_document_query(query_terms) and cls._is_schema_document(file_path, searchable):
            score += 2.5
        if cls._is_operational_query(query_terms) and cls._is_operational_artifact(file_path, row["kind"]):
            score += 2.5
        if cls._is_named_config_match(query_terms, file_path, row["line_end"]):
            score += 6.0

        return score

    @staticmethod
    def _searchable_text(row: sqlite3.Row) -> str:
        return " ".join(
            [
                row["id"],
                row["symbol_name"] or "",
                row["file_path"],
                Path(row["file_path"]).name,
                row["kind"],
                row["text"],
                row["metadata"],
            ]
        ).lower()

    @classmethod
    def _query_terms(cls, query: str) -> List[str]:
        normalized = query.lower().replace("\\", "/")
        terms = [
            term
            for term in HashingEmbeddingProvider._tokens(normalized)
            if term not in QUERY_STOPWORDS and len(term) > 1
        ]
        terms.extend(cls._path_like_terms(normalized))
        for literal in cls._query_literals(normalized):
            terms.extend(
                term
                for term in HashingEmbeddingProvider._tokens(literal)
                if term not in QUERY_STOPWORDS and len(term) > 1
            )
            terms.append(literal)
        return list(dict.fromkeys(term for term in terms if term))

    @staticmethod
    def _query_literals(query: str) -> List[str]:
        return [match.strip().lower().replace("\\", "/") for match in re.findall(r"`([^`]+)`", query)]

    @staticmethod
    def _path_like_terms(query: str) -> List[str]:
        normalized = query.lower().replace("\\", "/")
        candidates = re.findall(r"[a-z0-9_./-]+(?:\[[0-9]+\])?(?:\.[a-z0-9_./-]+)*", normalized)
        return list(
            dict.fromkeys(
                candidate.strip(".,:;()[]{}'\"")
                for candidate in candidates
                if "/" in candidate or "." in candidate or "[" in candidate
            )
        )

    @classmethod
    def _path_token_score(cls, term: str, file_path: str) -> float:
        if not term or len(term) < 3:
            return 0.0
        high_tokens, low_tokens = cls._path_token_groups(file_path)
        if term in high_tokens:
            return 0.6
        if any(cls._tokens_are_related(term, token) for token in high_tokens):
            return 0.35
        if term in low_tokens:
            return 0.25
        if any(cls._tokens_are_related(term, token) for token in low_tokens):
            return 0.15
        return 0.0

    @staticmethod
    def _path_token_groups(file_path: str) -> tuple[set[str], set[str]]:
        normalized = file_path.lower().replace("\\", "/")
        path = Path(normalized)
        high_values = {
            normalized,
            path.name,
            path.stem,
            path.suffix.lstrip("."),
        }
        high_values.update(re.split(r"[^a-z0-9]+", path.name))
        high_values.update(re.split(r"[^a-z0-9]+", path.stem))
        low_values = set(re.split(r"[^a-z0-9]+", path.parent.as_posix()))
        return (
            {value for value in high_values if value},
            {value for value in low_values if value and value != "."},
        )

    @classmethod
    def _tokens_are_related(cls, left: str, right: str) -> bool:
        left_stem = cls._light_stem(left)
        right_stem = cls._light_stem(right)
        if len(left_stem) < 5 or len(right_stem) < 5:
            return False
        return left_stem[:5] == right_stem[:5]

    @staticmethod
    def _light_stem(value: str) -> str:
        for suffix in ("ization", "ation", "tion", "ing", "ers", "er", "ed", "es", "s"):
            if value.endswith(suffix) and len(value) > len(suffix) + 3:
                return value[: -len(suffix)]
        return value

    @staticmethod
    def _is_schema_document(file_path: str, searchable: str) -> bool:
        return file_path.endswith(".schema.json") or "document_role = json schema" in searchable

    @classmethod
    def _is_operational_query(cls, query_terms: Sequence[str]) -> bool:
        operational_terms = {
            "script",
            "validator",
            "workflow",
            "command",
            "implements",
            "install",
            "build",
            "test",
            "lint",
        }
        return any(term in operational_terms for term in query_terms)

    @staticmethod
    def _is_operational_artifact(file_path: str, kind: str) -> bool:
        path = Path(file_path.lower())
        suffix = path.suffix
        if suffix in {".py", ".js", ".ts", ".sh", ".ps1", ".bat", ".cmd", ".yml", ".yaml", ".toml", ".ini", ".cfg"}:
            return True
        if any(part in {"scripts", "tools", "workflows", ".github", ".gitlab", ".circleci"} for part in path.parts):
            return True
        return any(marker in kind for marker in ("function", "method", "class", "module"))

    @classmethod
    def _is_named_config_match(cls, query_terms: Sequence[str], file_path: str, line_end: int) -> bool:
        path = Path(file_path.lower())
        if path.suffix or line_end > 3:
            return False
        name_tokens, _ = cls._path_token_groups(file_path)
        return any(term in name_tokens for term in query_terms)

    @staticmethod
    def _is_policy_document_query(query_terms: Sequence[str]) -> bool:
        markers = {
            "policy",
            "policies",
            "governance",
            "contributing",
            "contribution",
            "license",
            "licensing",
            "maintainer",
            "release",
            "rfc",
        }
        return any(term in markers for term in query_terms)

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
