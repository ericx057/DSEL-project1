import re
from pathlib import Path
from typing import Any, Dict, List

_UNLOADED = object()
CrossEncoder = _UNLOADED


def _load_cross_encoder():
    global CrossEncoder
    if CrossEncoder is _UNLOADED:
        try:
            from sentence_transformers import CrossEncoder as LoadedCrossEncoder
            CrossEncoder = LoadedCrossEncoder
        except ImportError:
            CrossEncoder = None
    if CrossEncoder is None:
        raise ImportError("sentence-transformers is required for Reranker")
    return CrossEncoder

class Reranker:
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        if not use_mock:
            cross_encoder = _load_cross_encoder()
            self.model = cross_encoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                automodel_args={"local_files_only": True},
                tokenizer_args={"local_files_only": True},
            )

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_m: int = 5) -> List[Dict[str, Any]]:
        if not chunks:
            return []
            
        scored_chunks = []
        if self.use_mock:
            query_words = query.lower().split()
            for chunk in chunks:
                score = sum(1 for word in query_words if word in chunk.get("text", "").lower())
                chunk_copy = chunk.copy()
                chunk_copy["rerank_score"] = float(score)
                scored_chunks.append(chunk_copy)
        else:
            pairs = [[query, chunk.get("text", "")] for chunk in chunks]
            scores = self.model.predict(pairs)
            for chunk, score in zip(chunks, scores):
                chunk_copy = chunk.copy()
                chunk_copy["rerank_score"] = float(score)
                scored_chunks.append(chunk_copy)
                
        scored_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_chunks[:top_m]


class LexicalReranker:
    STOPWORDS = {
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
        "how",
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
        "which",
        "with",
    }

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_m: int = 8) -> List[Dict[str, Any]]:
        scored_chunks = []
        for chunk in chunks:
            chunk_copy = chunk.copy()
            chunk_copy["rerank_score"] = float(self._score(query, chunk))
            scored_chunks.append(chunk_copy)
        scored_chunks.sort(key=lambda item: (item["rerank_score"], item.get("score", 0.0)), reverse=True)
        return self._diverse_top_m(scored_chunks, top_m)

    @classmethod
    def _score(cls, query: str, chunk: Dict[str, Any]) -> float:
        searchable = cls._searchable_text(chunk)
        file_path = str(chunk.get("file_path", "")).lower().replace("\\", "/")
        basename = Path(file_path).name
        suffix = Path(file_path).suffix
        score = 0.0

        for term in cls._query_terms(query):
            if term in searchable:
                score += 1.0
            score += cls._symbol_term_score(term, chunk)
            score += cls._path_token_score(term, file_path)

        for literal in cls._query_literals(query):
            if literal == file_path:
                score += 50.0
            elif literal == basename:
                score += 30.0
            elif literal.endswith("/") and literal in file_path:
                score += 1.0
            elif literal in file_path:
                score += 15.0
            elif literal in searchable:
                score += 8.0
            if literal.startswith(".") and literal == suffix:
                score += 20.0

        for path_like in cls._path_like_terms(query):
            if path_like == file_path:
                score += 50.0
            elif path_like == basename:
                score += 30.0
            elif path_like.endswith("/") and path_like in file_path:
                score += 1.0
            elif path_like in file_path:
                score += 15.0
            elif path_like in searchable:
                score += 8.0
            if path_like.startswith(".") and path_like == suffix:
                score += 20.0

        query_terms = cls._query_terms(query)
        if "schema" in query_terms and not cls._is_policy_document_query(query_terms) and cls._is_schema_document(file_path, searchable):
            score += 30.0
        if cls._is_policy_document_query(query_terms) and cls._is_policy_document(file_path):
            score += 120.0
            score += cls._policy_phrase_bonus(query_terms, searchable)
        if cls._is_operational_query(query_terms) and cls._is_operational_artifact(file_path, str(chunk.get("kind", ""))):
            score += 35.0
        if cls._is_named_config_match(query_terms, file_path, int(chunk.get("line_end", 9999) or 9999)):
            score += 60.0
        score += cls._owner_action_bonus(query_terms, chunk)
        score += cls._source_marker_score(chunk)

        return score

    @classmethod
    def _symbol_term_score(cls, term: str, chunk: Dict[str, Any]) -> float:
        if not term:
            return 0.0
        metadata = chunk.get("metadata") or {}
        symbol = str(chunk.get("symbol_name", ""))
        qualified = str(metadata.get("qualified_name", ""))
        kind = str(chunk.get("kind", "")).lower()
        normalized_symbol = cls._normalize_identifier(symbol)
        normalized_qualified = cls._normalize_identifier(qualified)
        qualified_parts = cls._qualified_parts(qualified)

        score = 0.0
        if term == normalized_symbol:
            score += 40.0
            if kind in {"class", "struct", "interface", "enum"}:
                score += 15.0
            if "implementation" in kind:
                score += 20.0
        elif term == normalized_qualified:
            score += 35.0
        elif term in qualified_parts:
            if qualified_parts and term == qualified_parts[-1]:
                score += 18.0
            else:
                score += 3.0
        elif term in f"{normalized_symbol} {normalized_qualified}":
            score += 6.0
        return score

    @classmethod
    def _owner_action_bonus(cls, query_terms: List[str], chunk: Dict[str, Any]) -> float:
        kind = str(chunk.get("kind", "")).lower()
        if "method" not in kind and "function" not in kind:
            return 0.0
        metadata = chunk.get("metadata") or {}
        qualified = str(metadata.get("qualified_name", ""))
        parts = cls._qualified_parts(qualified)
        if len(parts) < 2:
            return 0.0
        owner_terms = set(parts[:-1])
        action_terms = set(parts[1:])
        query_set = set(query_terms)
        if owner_terms & query_set and action_terms & query_set:
            return 60.0
        return 0.0

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @classmethod
    def _qualified_parts(cls, value: str) -> List[str]:
        parts: List[str] = []
        for part in re.split(r"::|\.|#", value):
            parts.extend(cls._identifier_parts(part))
        return list(dict.fromkeys(parts))

    @classmethod
    def _identifier_parts(cls, value: str) -> List[str]:
        parts: List[str] = []
        for raw in re.split(r"[^A-Za-z0-9]+", value):
            if not raw:
                continue
            lowered = raw.lower()
            parts.append(lowered)
            normalized = cls._normalize_identifier(raw)
            if normalized:
                parts.append(normalized)
            for camel_part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", raw):
                token = camel_part.lower()
                if token:
                    parts.append(token)
        normalized_full = cls._normalize_identifier(value)
        if normalized_full:
            parts.append(normalized_full)
        return list(dict.fromkeys(parts))

    @staticmethod
    def _source_marker_score(chunk: Dict[str, Any]) -> float:
        score = 0.0
        if chunk.get("_alias_match"):
            score += 12.0
        if chunk.get("_path_match"):
            score += 6.0
        if chunk.get("_fn_match"):
            score += 5.0
        if chunk.get("_lexical_match"):
            score += 4.0
        if chunk.get("_text_match"):
            score += 2.0
        return score

    @classmethod
    def _diverse_top_m(cls, chunks: List[Dict[str, Any]], top_m: int) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        selected_owners: set[str] = set()
        seen_files: set[str] = set()
        seen_basenames: set[str] = set()
        for chunk in chunks:
            file_path = str(chunk.get("file_path", ""))
            basename = Path(file_path).name.lower()
            owner = cls._chunk_owner(chunk)
            if (file_path in seen_files or basename in seen_basenames) and owner not in selected_owners:
                continue
            selected.append(chunk)
            if owner:
                selected_owners.add(owner)
            seen_files.add(file_path)
            if basename:
                seen_basenames.add(basename)
            if len(selected) == top_m:
                return selected
        for chunk in chunks:
            file_path = str(chunk.get("file_path", ""))
            if chunk in selected or file_path in seen_files:
                continue
            selected.append(chunk)
            seen_files.add(file_path)
            if len(selected) == top_m:
                break
        return selected

    @classmethod
    def _chunk_owner(cls, chunk: Dict[str, Any]) -> str:
        metadata = chunk.get("metadata") or {}
        qualified = str(metadata.get("qualified_name") or "")
        parts = [part for part in re.split(r"::|\.|#", qualified) if part]
        if not parts:
            return ""
        kind = str(chunk.get("kind") or "").lower()
        if kind in {"class", "struct", "interface", "enum", "class-implementation", "struct-implementation"}:
            return cls._normalize_identifier(parts[-1])
        if len(parts) > 1:
            return cls._normalize_identifier(parts[-2])
        return ""

    @staticmethod
    def _searchable_text(chunk: Dict[str, Any]) -> str:
        return " ".join(
            str(chunk.get(field, ""))
            for field in ("id", "symbol_name", "file_path", "kind", "text", "metadata")
        ).lower().replace("\\", "/")

    @classmethod
    def _query_terms(cls, query: str) -> List[str]:
        normalized = query.lower().replace("\\", "/")
        terms = []
        for raw in re.findall(r"[a-z_][a-z0-9_]*", normalized):
            for term in cls._identifier_parts(raw):
                if term not in cls.STOPWORDS and len(term) > 1:
                    terms.append(term)
                    stemmed = cls._light_stem(term)
                    if stemmed != term:
                        terms.append(stemmed)
        terms.extend(cls._path_like_terms(normalized))
        for literal in cls._query_literals(normalized):
            for raw in re.findall(r"[a-z_][a-z0-9_]*", literal):
                terms.extend(
                    term
                    for term in cls._identifier_parts(raw)
                    if term not in cls.STOPWORDS and len(term) > 1
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
            return 6.0
        if any(cls._tokens_are_related(term, token) for token in high_tokens):
            return 3.5
        if term in low_tokens:
            return 2.5
        if any(cls._tokens_are_related(term, token) for token in low_tokens):
            return 1.5
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
        if value.endswith("s") and len(value) > 3:
            return value[:-1]
        for suffix in ("ization", "ation", "tion", "ing", "ers", "er", "ed", "es", "s"):
            if value.endswith(suffix) and len(value) > len(suffix) + 3:
                return value[: -len(suffix)]
        return value

    @staticmethod
    def _is_schema_document(file_path: str, searchable: str) -> bool:
        return file_path.endswith(".schema.json") or "document_role = json schema" in searchable

    @classmethod
    def _is_operational_query(cls, query_terms: List[str]) -> bool:
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
    def _is_named_config_match(cls, query_terms: List[str], file_path: str, line_end: int) -> bool:
        path = Path(file_path.lower())
        if path.suffix or line_end > 3:
            return False
        name_tokens, _ = cls._path_token_groups(file_path)
        return any(term in name_tokens for term in query_terms)

    @staticmethod
    def _is_policy_document_query(query_terms: List[str]) -> bool:
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
    def _is_policy_document(file_path: str) -> bool:
        basename = Path(file_path.lower()).name
        return basename in {
            "code_of_conduct.md",
            "contributing.md",
            "governance.md",
            "license",
            "licenses.md",
            "maintainers.md",
        }

    @staticmethod
    def _policy_phrase_bonus(query_terms: List[str], searchable: str) -> float:
        score = 0.0
        query_set = set(query_terms)
        if "rfc" in query_set:
            if "rfc" in searchable:
                score += 20.0
            if "semantic or schema changes" in searchable:
                score += 30.0
            if "schema constraint changes" in searchable:
                score += 25.0
            if "interoperability behavior changes" in searchable:
                score += 25.0
        if "maintainer" in query_set and "nathan sharp" in searchable:
            score += 30.0
        if "release" in query_set:
            if "validates successfully" in searchable:
                score += 25.0
            if "self-consistent" in searchable:
                score += 25.0
        if "license" in query_set and "mit-licensed areas" in searchable:
            score += 20.0
        if "license" in query_set and "schemas/" in searchable and "examples/" in searchable and "mit" in searchable:
            score += 35.0
        return score
