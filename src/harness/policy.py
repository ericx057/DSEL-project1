from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.harness.models import RetrievalPacket, TaskSpec
from src.retrieval.context_summary import ResponseShaper


RESPONSE_POLICY_VERSION = "response-policy-v3"


@dataclass(frozen=True)
class PolicyDecision:
    response: str
    accepted: bool
    source: str
    flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Takeaway:
    text: str
    sufficient: bool


class ResponsePolicy:
    _PATH_RE = re.compile(
        r"(?i)\b(?:[A-Z]:[\\/]|(?:\.{1,2}|src|tests?|scripts?|evaluation|[A-Za-z0-9_.-]+)[\\/])"
        r"[^\s`'\"),]+"
    )
    _RAW_CODE_RE = re.compile(
        r"^\s*(?:class|def|async def|return|if|else|for|while|switch|case|"
        r"template|namespace|public:|private:|protected:|[A-Za-z_:<>~*&\s]+\([^)]*\)\s*(?:const)?\s*[;{])",
        re.MULTILINE,
    )
    _INFERENCE_ERROR_RE = re.compile(r"\[Inference Error:.*?\]", re.IGNORECASE)
    _SUMMARY_RE = re.compile(
        r"^(?:\[\d+\]\s+)?(?P<symbol>.*?) \((?P<descriptors>.*?)\) - "
        r"(?P<body>Mentions (?P<mentions>.*?)\.|No salient identifiers extracted\.)$"
    )
    _QUERY_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "do",
        "does",
        "engine",
        "for",
        "from",
        "handle",
        "handled",
        "how",
        "in",
        "is",
        "it",
        "of",
        "or",
        "the",
        "to",
        "what",
        "where",
        "which",
        "with",
        "work",
        "works",
    }
    _ABSTRACT_DECL_RE = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_:]* is an? "
        r"(?:(?:Python|TypeScript|JavaScript|C\+\+|C#|Go|Rust|Java) )?"
        r"(?:class|function|method|artifact)"
        r"(?: in (?:Python|TypeScript|JavaScript|C\+\+|C#|Go|Rust|Java))?\.?\s*$",
        re.IGNORECASE,
    )
    _ARTIFACT_LABEL_RE = re.compile(
        r"\b(?:class|struct|interface|method|function)-implementation tied to\b",
        re.IGNORECASE,
    )
    _GENERIC_UNUSABLE = "The cached response matched code artifacts but did not contain a usable behavioral summary."
    _IGNORED_MENTIONS = {
        "Any",
        "AccessTier",
        "List",
        "Optional",
        "Sequence",
        "Tuple",
        "_Symbol",
        "bool",
        "cached",
        "cls",
        "context",
        "dict",
        "float",
        "int",
        "list",
        "pass",
        "self",
        "str",
        "value",
    }

    def __init__(self, shaper: Optional[ResponseShaper] = None):
        self.shaper = shaper or ResponseShaper()
        self.version = RESPONSE_POLICY_VERSION

    def apply(self, model_output: str, task: TaskSpec, packet: RetrievalPacket) -> PolicyDecision:
        flags = self._quality_flags(model_output)
        shaped = self.shaper.shape(model_output)
        flags.extend(flag for flag in self._quality_flags(shaped) if flag not in flags)

        if not packet.artifacts and not packet.summaries:
            return PolicyDecision(
                response=self.fallback_response(task, packet),
                accepted=False,
                source="fallback",
                flags=list(dict.fromkeys([*flags, "no_retrieval_context"])),
            )

        if (
            not shaped
            or shaped == self._GENERIC_UNUSABLE
            or self._is_inference_error(shaped)
            or self._is_abstract_answer(shaped, packet)
            or self._is_artifact_label_answer(shaped)
            or "path_leak" in flags
            or "raw_code" in flags
            or self._is_path_list_shell(model_output)
        ):
            return PolicyDecision(
                response=self.fallback_response(task, packet),
                accepted=False,
                source="fallback",
                flags=list(dict.fromkeys([*flags, "fallback_used"])),
            )

        return PolicyDecision(response=shaped, accepted=True, source="model", flags=list(dict.fromkeys(flags)))

    def sanitize_cached(self, cached_text: str) -> Optional[PolicyDecision]:
        shaped = self.shaper.shape(cached_text)
        original_flags = self._quality_flags(cached_text)
        shaped_flags = self._quality_flags(shaped)
        flags = list(dict.fromkeys([*original_flags, *shaped_flags]))
        if not shaped or shaped == self._GENERIC_UNUSABLE:
            return None
        if "path_leak" in shaped_flags or "raw_code" in shaped_flags:
            return None
        return PolicyDecision(response=shaped, accepted=True, source="cache", flags=list(dict.fromkeys(flags)))

    def fallback_response(self, task: TaskSpec, packet: RetrievalPacket) -> str:
        if not packet.artifacts and not packet.summaries:
            return f"No indexed context matched `{task.query}`."

        selected_artifacts = self._select_relevant_artifacts(task.query, packet)
        selected_summaries = self._select_relevant_summaries(task.query, packet, selected_artifacts)
        if not selected_artifacts and not selected_summaries:
            return f"No indexed context matched `{task.query}`."

        takeaways = [self._takeaway_from_summary(summary) for summary in selected_summaries]
        if not takeaways:
            takeaways = [self._takeaway_from_artifact(artifact) for artifact in selected_artifacts]
        takeaways = [takeaway for takeaway in takeaways if takeaway.text]
        takeaways = self._prune_takeaways(takeaways)

        if any(takeaway.sufficient for takeaway in takeaways):
            lines = [f"For `{task.query}`, the useful retrieved signals are:"]
        else:
            lines = [
                f"For `{task.query}`, the indexed context is too thin for a behavioral answer.",
                "",
                "What I can confirm:",
            ]
        lines.extend(f"- {takeaway.text}" for takeaway in takeaways[:5])
        return "\n".join(lines).strip()

    @staticmethod
    def _prune_takeaways(takeaways: List[_Takeaway]) -> List[_Takeaway]:
        for takeaway in takeaways:
            if "'s retrieved implementation " in takeaway.text:
                return [takeaway]
        return takeaways

    def _quality_flags(self, text: str) -> List[str]:
        flags: List[str] = []
        if self._PATH_RE.search(text):
            flags.append("path_leak")
        if self._RAW_CODE_RE.search(text):
            flags.append("raw_code")
        if self._is_path_list_shell(text):
            flags.append("path_list")
        if not text.strip():
            flags.append("empty")
        return flags

    @classmethod
    def _is_path_list_shell(cls, text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return False
        headings = {"relevant files:", "files:", "source files:", "sources:", "paths:", "file paths:"}
        bullet_paths = sum(1 for line in lines if line.startswith(("-", "*")) and cls._PATH_RE.search(line))
        return lines[0].lower() in headings or bullet_paths >= max(1, len(lines) - 1)

    def _is_abstract_answer(self, shaped: str, packet: RetrievalPacket) -> bool:
        if not self._has_abstract_declaration_line(shaped):
            return False
        if any(self._takeaway_from_summary(summary).sufficient for summary in packet.summaries):
            return True
        return bool(packet.artifacts or packet.summaries)

    @classmethod
    def _is_artifact_label_answer(cls, shaped: str) -> bool:
        return bool(cls._ARTIFACT_LABEL_RE.search(shaped))

    @classmethod
    def _is_inference_error(cls, shaped: str) -> bool:
        return bool(cls._INFERENCE_ERROR_RE.search(shaped))

    @classmethod
    def _has_abstract_declaration_line(cls, shaped: str) -> bool:
        for line in shaped.splitlines() or [shaped]:
            cleaned = re.sub(r"^\s*(?:[-*]\s*)?", "", line.strip())
            if cls._ABSTRACT_DECL_RE.match(cleaned):
                return True
        return False

    def _select_relevant_summaries(
        self,
        query: str,
        packet: RetrievalPacket,
        selected_artifacts: Optional[List[dict]] = None,
    ) -> List[str]:
        if not packet.summaries:
            return []
        artifacts = selected_artifacts if selected_artifacts is not None else self._select_relevant_artifacts(query, packet)
        if not artifacts:
            return self._select_summaries_by_relevance(query, packet.summaries)
        selected_ids = {id(artifact) for artifact in artifacts}
        summaries: List[str] = []
        for artifact, summary in zip(packet.artifacts, packet.summaries):
            if id(artifact) in selected_ids:
                summaries.append(summary)
        return summaries or self._select_summaries_by_relevance(query, packet.summaries)

    def _select_relevant_artifacts(self, query: str, packet: RetrievalPacket) -> List[dict]:
        if not packet.artifacts:
            return []
        named_terms = self._named_query_terms(query)
        terms = self._query_terms(query)
        scored = [
            (self._artifact_relevance(terms, artifact), index, artifact)
            for index, artifact in enumerate(packet.artifacts)
        ]
        positive = [(score, index, artifact) for score, index, artifact in scored if score > 0]
        if named_terms:
            anchored = [
                (score, index, artifact)
                for score, index, artifact in positive
                if self._artifact_mentions_named_term(named_terms, artifact)
            ]
            if anchored:
                positive = anchored
        if not positive:
            return []
        positive.sort(key=lambda item: (-item[0], item[1]))
        return [artifact for _, _, artifact in positive[:5]]

    def _select_summaries_by_relevance(self, query: str, summaries: List[str]) -> List[str]:
        terms = self._query_terms(query)
        named_terms = self._named_query_terms(query)
        scored = [
            (self._summary_relevance(terms, named_terms, summary), index, summary)
            for index, summary in enumerate(summaries)
        ]
        positive = [(score, index, summary) for score, index, summary in scored if score > 0]
        positive.sort(key=lambda item: (-item[0], item[1]))
        return [summary for _, _, summary in positive[:5]]

    @classmethod
    def _summary_relevance(cls, terms: List[str], named_terms: List[str], summary: str) -> float:
        parts = set(cls._identifier_parts(summary))
        score = 0.0
        matched_terms: set[str] = set()
        has_anchor = False
        for term in terms:
            if term in parts:
                score += 2.0
                matched_terms.add(term)
            elif term in summary.lower():
                score += 0.5
                matched_terms.add(term)
        for term in named_terms:
            if term in parts:
                score += 8.0
                has_anchor = True
        if not has_anchor and len(matched_terms) < 2:
            return 0.0
        return score

    @classmethod
    def _artifact_relevance(cls, terms: List[str], artifact: dict) -> float:
        metadata = artifact.get("metadata") or {}
        symbol = str(artifact.get("symbol_name") or "")
        qualified = str(metadata.get("qualified_name") or "")
        file_path = str(artifact.get("file_path") or "").lower().replace("\\", "/")
        text = " ".join(
            str(value)
            for value in (
                symbol,
                qualified,
                artifact.get("kind", ""),
                artifact.get("text", ""),
            )
        ).lower()
        symbol_norm = cls._normalize_identifier(symbol)
        qualified_parts = cls._identifier_parts(qualified)
        if ("tests/" in file_path or file_path.startswith("tests/")) and "test" not in terms and "tests" not in terms:
            return 0.0

        score = 0.0
        matched_terms: set[str] = set()
        has_anchor = False
        for term in terms:
            if term == symbol_norm:
                score += 8.0
                matched_terms.add(term)
                has_anchor = True
            if term in qualified_parts:
                score += 5.0 if qualified_parts and term == qualified_parts[-1] else 2.0
                matched_terms.add(term)
                if qualified_parts and term in {qualified_parts[0], qualified_parts[-1]}:
                    has_anchor = True
            elif term in text:
                score += 1.0
                matched_terms.add(term)
        if not has_anchor and len(matched_terms) < 2:
            return 0.0
        return score

    @classmethod
    def _query_terms(cls, query: str) -> List[str]:
        terms: List[str] = []
        for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query):
            for token in cls._identifier_parts(raw):
                if token not in cls._QUERY_STOPWORDS and len(token) > 1:
                    stemmed = cls._light_stem(token)
                    terms.append(stemmed)
        return list(dict.fromkeys(terms))

    @classmethod
    def _named_query_terms(cls, query: str) -> List[str]:
        terms: List[str] = []
        for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query):
            if not any(char.isupper() for char in raw[1:]):
                continue
            normalized = cls._normalize_identifier(raw)
            if normalized:
                terms.append(normalized)
        return list(dict.fromkeys(terms))

    @classmethod
    def _artifact_mentions_named_term(cls, named_terms: List[str], artifact: dict) -> bool:
        metadata = artifact.get("metadata") or {}
        parts: List[str] = []
        for value in (artifact.get("symbol_name", ""), metadata.get("qualified_name", "")):
            parts.extend(cls._identifier_parts(str(value)))
        part_set = set(parts)
        return any(term in part_set for term in named_terms)

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @classmethod
    def _identifier_parts(cls, value: str) -> List[str]:
        parts: List[str] = []
        for raw in re.split(r"[^A-Za-z0-9]+", value):
            if not raw:
                continue
            lowered = raw.lower()
            parts.append(lowered)
            normalized = cls._normalize_identifier(raw)
            if normalized and normalized != lowered:
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
    def _light_stem(value: str) -> str:
        for suffix in ("ization", "ation", "tion", "ing", "ers", "er", "ed", "es", "s"):
            if value.endswith(suffix) and len(value) > len(suffix) + 3:
                return value[: -len(suffix)]
        return value

    def _takeaway_from_summary(self, summary: str) -> _Takeaway:
        summary = re.sub(r"^\[\d+\]\s+", "", summary.strip())
        match = self._SUMMARY_RE.match(summary)
        if not match:
            return _Takeaway(summary, True)

        symbol = match.group("symbol").strip()
        descriptors = [part.strip() for part in match.group("descriptors").split(",") if part.strip()]
        kind = descriptors[0] if descriptors else "artifact"
        display_kind = kind.removesuffix("-implementation")
        language = self._format_language(
            descriptors[1] if len(descriptors) > 1 and not descriptors[1].startswith("lines ") else ""
        )
        mentions = [
            value.strip()
            for value in (match.group("mentions") or "").split(",")
            if value.strip()
            and value.strip() != symbol
            and value.strip() not in self._IGNORED_MENTIONS
            and value.strip().lower() not in {item.lower() for item in self._IGNORED_MENTIONS}
        ]
        language_text = f"{language} " if language else ""
        article = self._article(language_text + display_kind)
        if not mentions:
            return _Takeaway(
                (
                    f"{symbol} is {article} {language_text}{display_kind}. "
                    f"The retrieved excerpt only identifies the {display_kind}; it does not show methods or behavior."
                ),
                False,
            )
        if kind in {"class-implementation", "struct-implementation", "interface-implementation"}:
            behavior = [phrase for phrase in (self._behavior_phrase(mention) for mention in mentions) if phrase]
            if behavior:
                return _Takeaway(
                    f"{symbol}'s retrieved implementation {self._join_terms(behavior[:5])}.",
                    True,
                )
        return _Takeaway(
            f"{symbol} is {article} {language_text}{display_kind} tied to {self._join_terms(mentions[:5])}.",
            True,
        )

    @classmethod
    def _behavior_phrase(cls, identifier: str) -> str:
        parts = cls._identifier_words(identifier)
        if not parts:
            return ""
        first, rest = parts[0], parts[1:]
        verb_map = {
            "acquire": "acquires",
            "append": "appends",
            "build": "builds",
            "collect": "collects",
            "dedupe": "deduplicates",
            "delete": "deletes",
            "detect": "detects",
            "find": "finds",
            "generate": "generates",
            "get": "gets",
            "index": "indexes",
            "iter": "iterates",
            "merge": "merges",
            "parse": "parses",
            "publish": "publishes",
            "release": "releases",
            "resolve": "resolves",
            "search": "searches",
            "set": "sets",
            "upsert": "upserts",
            "validate": "validates",
            "warm": "warms",
        }
        if first == "is":
            return f"checks {cls._object_phrase(rest)}".strip()
        if first in verb_map:
            return f"{verb_map[first]} {cls._object_phrase(rest)}".strip()
        return ""

    @staticmethod
    def _identifier_words(identifier: str) -> List[str]:
        normalized = identifier.strip("_")
        if not normalized:
            return []
        words: List[str] = []
        for raw in re.split(r"[^A-Za-z0-9]+", normalized):
            if not raw:
                continue
            for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", raw):
                if part:
                    words.append(part.lower())
        return words

    @staticmethod
    def _object_phrase(words: List[str]) -> str:
        if not words:
            return "state"
        if words == ["excluded"]:
            return "excluded paths"
        adjusted = list(words)
        plurals = {
            "file": "files",
            "path": "paths",
            "repository": "repositories",
        }
        adjusted[-1] = plurals.get(adjusted[-1], adjusted[-1])
        return " ".join(adjusted)

    def _takeaway_from_artifact(self, artifact: dict) -> _Takeaway:
        symbol = str(artifact.get("symbol_name") or artifact.get("kind") or "artifact").strip()
        kind = str(artifact.get("kind") or "artifact").strip()
        language = self._format_language(str(artifact.get("language") or ""))
        language_text = f"{language} " if language else ""
        return _Takeaway(f"{symbol} is {self._article(language_text + kind)} {language_text}{kind}.", False)

    @staticmethod
    def _format_language(language: str) -> str:
        names = {
            "python": "Python",
            "typescript": "TypeScript",
            "javascript": "JavaScript",
            "cpp": "C++",
            "csharp": "C#",
            "go": "Go",
            "rust": "Rust",
            "java": "Java",
        }
        return names.get(language.lower(), language)

    @staticmethod
    def _join_terms(terms: List[str]) -> str:
        if len(terms) <= 1:
            return terms[0] if terms else "no concrete behavior"
        if len(terms) == 2:
            return f"{terms[0]} and {terms[1]}"
        return ", ".join(terms[:-1]) + f", and {terms[-1]}"

    @staticmethod
    def _article(value: str) -> str:
        return "an" if value[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
