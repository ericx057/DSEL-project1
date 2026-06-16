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
    _SUMMARY_RE = re.compile(
        r"^(?:\[\d+\]\s+)?(?P<symbol>.*?) \((?P<descriptors>.*?)\) - "
        r"(?P<body>Mentions (?P<mentions>.*?)\.|No salient identifiers extracted\.)$"
    )
    _ABSTRACT_DECL_RE = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_:]* is an? "
        r"(?:(?:Python|TypeScript|JavaScript|C\+\+|C#|Go|Rust|Java) )?"
        r"(?:class|function|method|artifact)"
        r"(?: in (?:Python|TypeScript|JavaScript|C\+\+|C#|Go|Rust|Java))?\.?\s*$"
    )
    _GENERIC_UNUSABLE = "The cached response matched code artifacts but did not contain a usable behavioral summary."

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
            or self._is_abstract_answer(shaped, packet)
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

        takeaways = [self._takeaway_from_summary(summary) for summary in packet.summaries]
        if not takeaways:
            takeaways = [self._takeaway_from_artifact(artifact) for artifact in packet.artifacts]
        takeaways = [takeaway for takeaway in takeaways if takeaway.text]

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
        if not self._ABSTRACT_DECL_RE.match(shaped.strip()):
            return False
        return any(self._takeaway_from_summary(summary).sufficient for summary in packet.summaries)

    def _takeaway_from_summary(self, summary: str) -> _Takeaway:
        summary = re.sub(r"^\[\d+\]\s+", "", summary.strip())
        match = self._SUMMARY_RE.match(summary)
        if not match:
            return _Takeaway(summary, True)

        symbol = match.group("symbol").strip()
        descriptors = [part.strip() for part in match.group("descriptors").split(",") if part.strip()]
        kind = descriptors[0] if descriptors else "artifact"
        language = self._format_language(
            descriptors[1] if len(descriptors) > 1 and not descriptors[1].startswith("lines ") else ""
        )
        mentions = [
            value.strip()
            for value in (match.group("mentions") or "").split(",")
            if value.strip()
            and value.strip() != symbol
            and value.strip().lower() not in {"pass", "cached", "context", "value"}
        ]
        language_text = f"{language} " if language else ""
        article = self._article(language_text + kind)
        if not mentions:
            return _Takeaway(
                (
                    f"{symbol} is {article} {language_text}{kind}. "
                    f"The retrieved excerpt only identifies the {kind}; it does not show methods or behavior."
                ),
                False,
            )
        return _Takeaway(
            f"{symbol} is {article} {language_text}{kind} tied to {self._join_terms(mentions[:5])}.",
            True,
        )

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
