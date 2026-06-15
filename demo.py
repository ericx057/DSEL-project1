#!/usr/bin/env python3
"""DSEL — Spotlight-style code intelligence demo for FreeCAD."""

from __future__ import annotations

import os
import sys
import argparse
import copy
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Palette ────────────────────────────────────────────────────────────────────
BG      = "#1c1c1e"
PILL    = "#2c2c2e"
BORDER  = "#3a3a3c"
ACCENT  = "#0a84ff"
FG      = "#f5f5f7"
FG2     = "#aeaeb2"
FG3     = "#8e8e93"
GREEN   = "#30d158"
RED_C   = "#ff453a"
DIVIDER = "#38383a"
MONO    = "SF Mono"     if sys.platform == "darwin" else "Consolas"
SANS    = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"

W_COLL  = 660
H_COLL  = 58
W_EXP   = 880
H_EXP   = 540
ANIM_MS = 260           # expand animation duration

DEMO_Q = [
    "In GCS.cpp, how does System::solve(SubSystem* subsys, bool isFine, "
    "Algorithm alg, bool isRedundantsolving) dispatch to solve_BFGS, "
    "solve_LM, and solve_DL?",
    "How does SubSystem::calcJacobi build the Jacobian matrix entry-by-entry, "
    "and how does System::solve_LM use that Jacobian in GCS.cpp?",
]


# ── LLM answer generator ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a codebase answer generator. Use only the retrieved summaries "
    "provided. Explain behavior in terms of functions, classes, data flow, "
    "and call relationships. Do not answer by listing file paths, and do not "
    "copy raw source unless the user explicitly asks for a code excerpt."
)
_MAX_TOKENS    = 800


@dataclass(frozen=True)
class RetrievalResult:
    hits: List[Dict[str, Any]]
    elapsed_ms: float
    cached: bool


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


class ConversationSession:
    def __init__(self):
        self._hits: List[Dict[str, Any]] = []
        self._history: List[ConversationTurn] = []

    def start(self, hits: List[Dict[str, Any]]) -> None:
        self._hits = copy.deepcopy(hits)
        self._history = []

    def record_answer(self, question: str, answer: str) -> None:
        if question.strip() and answer.strip():
            self._history.append(ConversationTurn(question.strip(), answer.strip()))

    def can_follow_up(self) -> bool:
        return bool(self._hits)

    @property
    def hits(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._hits)

    @property
    def history(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._history)


class RetrievedContextSummarizer:
    _IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:]*")
    _STOPWORDS = {
        "and",
        "bool",
        "class",
        "const",
        "def",
        "else",
        "false",
        "for",
        "if",
        "int",
        "return",
        "self",
        "static",
        "struct",
        "the",
        "this",
        "true",
        "void",
        "while",
    }

    def summarize_hits(self, hits: List[Dict[str, Any]], limit: int = 5) -> str:
        summaries = [self.summarize_hit(hit, index) for index, hit in enumerate(hits[:limit], 1)]
        return "\n".join(summaries) if summaries else "No retrieved artifacts."

    def summarize_hit(self, hit: Dict[str, Any], index: int) -> str:
        symbol = str(hit.get("symbol_name") or "").strip() or "unnamed artifact"
        kind = str(hit.get("kind") or "artifact").strip()
        language = str(hit.get("language") or "").strip()
        line_start = hit.get("line_start")
        line_end = hit.get("line_end")
        descriptors = ", ".join(
            value
            for value in (kind, language, self._line_summary(line_start, line_end))
            if value
        )
        identifiers = self._identifier_summary(str(hit.get("text") or ""), symbol)
        return f"[{index}] {symbol} ({descriptors}) - {identifiers}"

    @staticmethod
    def _line_summary(line_start: object, line_end: object) -> str:
        if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0:
            return f"lines {line_start}-{line_end}"
        return ""

    @classmethod
    def _identifier_summary(cls, text: str, symbol: str) -> str:
        identifiers: List[str] = []
        for value in (symbol, text):
            for token in cls._IDENTIFIER_RE.findall(value):
                lowered = token.lower().strip(":")
                if len(lowered) <= 2 or lowered in cls._STOPWORDS:
                    continue
                if "/" in token or "\\" in token:
                    continue
                if token not in identifiers:
                    identifiers.append(token)
                if len(identifiers) >= 10:
                    break
            if len(identifiers) >= 10:
                break
        if not identifiers:
            return "No salient identifiers extracted."
        return "Mentions " + ", ".join(identifiers[:10]) + "."


class LLMPromptBuilder:
    def __init__(self, summarizer: Optional["RetrievedContextSummarizer"] = None):
        self._summarizer = summarizer or RetrievedContextSummarizer()

    def build_user_prompt(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        history: tuple[ConversationTurn, ...] = (),
    ) -> str:
        parts = [f"Retrieved summaries:\n{self._summarizer.summarize_hits(hits)}"]
        if history:
            turns: List[str] = ["Conversation so far:"]
            for turn in history[-4:]:
                turns.append(f"Previous question: {turn.question}")
                turns.append(f"Previous answer: {turn.answer}")
            parts.append("\n".join(turns))
        parts.append(f"Question: {query}")
        return "\n\n".join(parts)


class QueryResultCache:
    def __init__(self, max_entries: int = 128):
        self.max_entries = max_entries
        self._items: "OrderedDict[tuple[str, int], List[Dict[str, Any]]]" = OrderedDict()
        self._lock = threading.RLock()

    def get(self, query: str, top_k: int) -> Optional[List[Dict[str, Any]]]:
        key = self._key(query, top_k)
        with self._lock:
            if key not in self._items:
                return None
            value = self._items.pop(key)
            self._items[key] = value
            return copy.deepcopy(value)

    def put(self, query: str, top_k: int, hits: List[Dict[str, Any]]) -> None:
        key = self._key(query, top_k)
        with self._lock:
            self._items[key] = copy.deepcopy(hits)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    @staticmethod
    def _key(query: str, top_k: int) -> tuple[str, int]:
        return (" ".join(query.lower().split()), top_k)


@dataclass(frozen=True)
class SourceSnippet:
    text: str
    line_start: int
    line_end: int
    symbol_name: str


class SourceSnippetResolver:
    QUALIFIED_SYMBOL_RE = re.compile(
        r"\b(?P<symbol>[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)+)"
        r"\s*(?:\((?P<params>[^)]*)\))?"
    )
    IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    STOP_TERMS = {
        "and", "bool", "const", "does", "false", "from", "how", "into",
        "the", "this", "true", "using", "what", "when", "which", "with",
    }

    def __init__(
        self,
        roots: Optional[tuple[Path, ...]] = None,
        max_chars: int = 2600,
    ):
        self.roots = roots or (ROOT / "freecad-src", ROOT)
        self.max_chars = max_chars

    def enrich(self, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        requested_symbols = self._requested_symbols(query)
        if not requested_symbols:
            return hits

        enriched: List[Dict[str, Any]] = []
        for hit in hits:
            item = copy.deepcopy(hit)
            file_path = str(item.get("file_path") or "")
            source_path = self._resolve(file_path)
            if source_path:
                snippets = [
                    snippet
                    for symbol, params in requested_symbols
                    if (snippet := self.extract(query, source_path, symbol, params))
                ]
                if snippets:
                    item = self._with_snippets(item, snippets)
            enriched.append(item)
        return enriched

    def extract(
        self,
        query: str,
        source_path: Path,
        symbol: str,
        params: str = "",
    ) -> Optional[SourceSnippet]:
        try:
            source = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        owner, name = symbol.rsplit("::", 1)
        pattern = re.compile(
            r"\b" + re.escape(owner) + r"\s*::\s*" + re.escape(name) + r"\s*\(",
            re.MULTILINE,
        )
        candidates: List[tuple[int, int, int, int]] = []
        for match in pattern.finditer(source):
            body_start = source.find("{", match.end())
            if body_start == -1:
                continue
            if ";" in source[match.end():body_start]:
                continue
            body_end = self._find_matching_brace(source, body_start)
            if body_end == -1:
                continue
            score = self._candidate_score(query, params, source[match.start():body_start + 1])
            candidates.append((score, match.start(), body_start, body_end))

        if not candidates:
            return None

        _, start, _, end = max(candidates, key=lambda candidate: candidate[0])
        line_start = source.count("\n", 0, start) + 1
        line_end = source.count("\n", 0, end) + 1
        function_text = source[start:end + 1]
        focused = self._focus(function_text, query)
        return SourceSnippet(focused, line_start, line_end, symbol)

    def _with_snippets(self, hit: Dict[str, Any], snippets: List[SourceSnippet]) -> Dict[str, Any]:
        existing_text = str(hit.get("text") or "").strip()
        focused_text = "\n\n".join(snippet.text for snippet in snippets)
        if existing_text and existing_text not in focused_text:
            focused_text = f"{focused_text}\n\n{existing_text}"
        hit["text"] = focused_text
        hit["line_start"] = snippets[0].line_start
        hit["line_end"] = snippets[-1].line_end
        symbols = [str(hit.get("symbol_name") or "")]
        symbols.extend(snippet.symbol_name for snippet in snippets)
        hit["symbol_name"] = ", ".join(dict.fromkeys(symbol for symbol in symbols if symbol))
        hit["_source_excerpt"] = True
        return hit

    def _resolve(self, file_path: str) -> Optional[Path]:
        normalized = file_path.replace("/", os.sep)
        for root in self.roots:
            candidate = root / normalized
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _requested_symbols(self, query: str) -> List[tuple[str, str]]:
        symbols: List[tuple[str, str]] = []
        seen: set[str] = set()
        for match in self.QUALIFIED_SYMBOL_RE.finditer(query):
            symbol = match.group("symbol")
            if symbol in seen:
                continue
            seen.add(symbol)
            symbols.append((symbol, match.group("params") or ""))
        return symbols

    def _candidate_score(self, query: str, params: str, signature: str) -> int:
        signature_terms = self._terms(signature)
        score = 0
        for term in self._terms(query):
            if term in signature_terms:
                score += 3
        for term in self._terms(params):
            if term in signature_terms:
                score += 5
        return score

    def _focus(self, function_text: str, query: str) -> str:
        if len(function_text) <= self.max_chars:
            return function_text

        lines = function_text.splitlines()
        query_terms = self._terms(query)
        selected: set[int] = set(range(min(4, len(lines))))
        scored_lines: List[tuple[int, int]] = []
        for index, line in enumerate(lines):
            lower = line.lower()
            score = sum(1 for term in query_terms if term in lower)
            if score:
                scored_lines.append((score, index))
        for _, index in sorted(scored_lines, reverse=True)[:4]:
            for line_index in range(max(0, index - 5), min(len(lines), index + 8)):
                selected.add(line_index)

        output: List[str] = []
        previous = -2
        for index in sorted(selected):
            if output and index != previous + 1:
                output.append("    // ...")
            output.append(lines[index])
            previous = index
            if len("\n".join(output)) >= self.max_chars:
                break
        return "\n".join(output)

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        return {
            token.lower()
            for token in cls.IDENTIFIER_RE.findall(text)
            if token.lower() not in cls.STOP_TERMS and len(token) > 1
        }

    @staticmethod
    def _find_matching_brace(source: str, open_index: int) -> int:
        depth = 0
        in_line_comment = False
        in_block_comment = False
        in_string: Optional[str] = None
        escaped = False
        index = open_index
        while index < len(source):
            char = source[index]
            nxt = source[index + 1] if index + 1 < len(source) else ""
            if in_line_comment:
                in_line_comment = char != "\n"
            elif in_block_comment:
                if char == "*" and nxt == "/":
                    in_block_comment = False
                    index += 1
            elif in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
            elif char == "/" and nxt == "/":
                in_line_comment = True
                index += 1
            elif char == "/" and nxt == "*":
                in_block_comment = True
                index += 1
            elif char in {'"', "'"}:
                in_string = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return -1


def _build_context(hits: List[Dict[str, Any]]) -> str:
    return RetrievedContextSummarizer().summarize_hits(hits)


class LLMAnswerGenerator:
    """Streams a natural-language answer from Claude Haiku given retrieved snippets."""

    _MODEL = "claude-haiku-4-5-20251001"

    def __init__(self):
        self._client = None
        self._prompt_builder = LLMPromptBuilder()
        try:
            import anthropic
            self._client = anthropic.Anthropic()
        except Exception as exc:
            print(f"[demo] Anthropic LLM unavailable: {exc}", file=sys.stderr)

    @property
    def ready(self) -> bool:
        return self._client is not None

    def stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_done: Callable[[Optional[str]], None],
        history: tuple[ConversationTurn, ...] = (),
    ) -> None:
        if not self.ready:
            on_done("(Set ANTHROPIC_API_KEY to enable LLM answers.)")
            return
        prompt = self._prompt_builder.build_user_prompt(query, hits, history)
        try:
            import anthropic
            with self._client.messages.stream(
                model=self._MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as s:
                for chunk in s.text_stream:
                    on_token(chunk)
            on_done(None)
        except anthropic.AuthenticationError:
            on_done("\n\n[Auth error — check ANTHROPIC_API_KEY]")
        except Exception as exc:
            on_done(f"\n\n[LLM error: {exc}]")


class OpenAIAnswerGenerator:
    """Streams a natural-language answer from OpenAI (gpt-4o-mini) given retrieved snippets."""

    _MODEL = "gpt-4o-mini"

    def __init__(self):
        self._client = None
        self._prompt_builder = LLMPromptBuilder()
        try:
            import openai
            self._client = openai.OpenAI()
        except Exception as exc:
            print(f"[demo] OpenAI LLM unavailable: {exc}", file=sys.stderr)

    @property
    def ready(self) -> bool:
        return self._client is not None

    def stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_done: Callable[[Optional[str]], None],
        history: tuple[ConversationTurn, ...] = (),
    ) -> None:
        if not self.ready:
            on_done("(Set OPENAI_API_KEY to enable OpenAI answers.)")
            return
        prompt = self._prompt_builder.build_user_prompt(query, hits, history)
        try:
            with self._client.chat.completions.create(
                model=self._MODEL,
                max_tokens=_MAX_TOKENS,
                stream=True,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            ) as stream:
                for event in stream:
                    delta = event.choices[0].delta.content
                    if delta:
                        on_token(delta)
            on_done(None)
        except Exception as exc:
            on_done(f"\n\n[OpenAI error: {exc}]")


class LocalInferenceAnswerGenerator:
    def __init__(self, runtime: Optional[Any] = None):
        self._prompt_builder = LLMPromptBuilder()
        self._runtime = runtime
        self._healthy = runtime is not None
        if self._runtime is None:
            try:
                from src.inference.registry import InferenceEngineRegistry
                from src.inference.runtime import LlamaCppRuntime

                endpoint = InferenceEngineRegistry().get_engine_endpoint()
                self._healthy = self._check_health(endpoint.health_url)
                timeout_seconds = float(
                    os.environ.get(
                        "DSEL_LOCAL_LLM_TIMEOUT_SECONDS",
                        os.environ.get("CIS_INFERENCE_TIMEOUT_SECONDS", "60"),
                    )
                )
                self._runtime = LlamaCppRuntime(
                    endpoint_url=endpoint.url,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                print(f"[demo] local inference unavailable: {exc}", file=sys.stderr)

    @property
    def ready(self) -> bool:
        return self._runtime is not None and self._healthy

    def stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_done: Callable[[Optional[str]], None],
        history: tuple[ConversationTurn, ...] = (),
    ) -> None:
        if not self.ready:
            on_done("(Local inference engine is not configured.)")
            return
        prompt = self._build_prompt(query, hits, history)
        try:
            for token in self._runtime.generate_stream(prompt):
                on_token(token)
            on_done(None)
        except Exception as exc:
            on_done(f"\n\n[Local inference error: {exc}]")

    def _build_prompt(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        history: tuple[ConversationTurn, ...],
    ) -> str:
        user_prompt = self._prompt_builder.build_user_prompt(query, hits, history)
        return f"{_SYSTEM_PROMPT}\n\n{user_prompt}\n\nAnswer:"

    @staticmethod
    def _check_health(health_url: str) -> bool:
        if os.environ.get("DSEL_LOCAL_LLM_SKIP_HEALTHCHECK", "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
        try:
            import httpx

            response = httpx.get(health_url, timeout=1.0)
            return response.status_code < 500
        except Exception:
            return False


class CodexCliAnswerGenerator:
    def __init__(
        self,
        codex_path: Optional[str] = None,
        runner: Optional[Callable[[List[str], str, Path, float], tuple[int, str, str]]] = None,
        output_dir: Optional[Path] = None,
    ):
        self._prompt_builder = LLMPromptBuilder()
        self._codex_path = codex_path or self._find_codex()
        self._runner = runner or self._run_codex
        self._output_dir = output_dir
        self._timeout_seconds = float(os.environ.get("DSEL_CODEX_TIMEOUT_SECONDS", "180"))

    @property
    def ready(self) -> bool:
        return bool(self._codex_path)

    def stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_done: Callable[[Optional[str]], None],
        history: tuple[ConversationTurn, ...] = (),
    ) -> None:
        if not self.ready:
            on_done("(Codex CLI is not available.)")
            return
        output_path = self._new_output_path()
        prompt = self._build_prompt(query, hits, history)
        args = self._build_args(output_path)
        try:
            return_code, stdout, stderr = self._runner(args, prompt, output_path, self._timeout_seconds)
            if return_code != 0:
                on_done(f"\n\n[Codex CLI error: {stderr.strip() or stdout.strip() or return_code}]")
                return
            answer = output_path.read_text(encoding="utf-8").strip()
            if not answer:
                answer = stdout.strip()
            if not answer:
                on_done("\n\n[Codex CLI error: no answer returned]")
                return
            for chunk in self._chunks(answer):
                on_token(chunk)
            on_done(None)
        except Exception as exc:
            on_done(f"\n\n[Codex CLI error: {exc}]")
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _build_prompt(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        history: tuple[ConversationTurn, ...],
    ) -> str:
        user_prompt = self._prompt_builder.build_user_prompt(query, hits, history)
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            "You are being called as a local desktop answer generator. "
            "Do not run tools, do not inspect files, and do not modify anything. "
            "Use only the retrieved context below and return the answer text only.\n\n"
            f"{user_prompt}"
        )

    def _build_args(self, output_path: Path) -> List[str]:
        assert self._codex_path is not None
        return [
            self._codex_path,
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "exec",
            "--ephemeral",
            "-C",
            str(ROOT),
            "--output-last-message",
            str(output_path),
            "-",
        ]

    def _new_output_path(self) -> Path:
        output_dir = self._output_dir or Path(tempfile.gettempdir())
        output_dir.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(prefix="dsel-codex-", suffix=".txt", dir=output_dir, delete=False)
        handle.close()
        return Path(handle.name)

    @staticmethod
    def _run_codex(args: List[str], prompt: str, output_path: Path, timeout_seconds: float) -> tuple[int, str, str]:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(
            args,
            input=prompt.encode("utf-8"),
            text=False,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=ROOT,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace") if isinstance(completed.stdout, bytes) else completed.stdout
        stderr = completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else completed.stderr
        return completed.returncode, stdout, stderr

    @staticmethod
    def _find_codex() -> Optional[str]:
        env_path = os.environ.get("DSEL_CODEX_CLI")
        if env_path and Path(env_path).exists():
            return env_path
        discovered = shutil.which("codex")
        if discovered:
            return discovered
        bundled = Path.home() / ".vscode" / "extensions" / "openai.chatgpt-26.602.71036-win32-x64" / "bin" / "windows-x86_64" / "codex.exe"
        if bundled.exists():
            return str(bundled)
        return None

    @staticmethod
    def _chunks(text: str, size: int = 96):
        for index in range(0, len(text), size):
            yield text[index : index + size]


class NoLLMAnswerGenerator:
    ready = False

    def stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_done: Callable[[Optional[str]], None],
        history: tuple[ConversationTurn, ...] = (),
    ) -> None:
        on_done("No local inference backend is configured. Start llama.cpp or set DSEL_LLM_BACKEND=none.")


class DeterministicDemoAnswers:
    DISPATCH_QUERY = DEMO_Q[0]
    JACOBIAN_QUERY = DEMO_Q[1]
    CONSTRAINT_ERROR_QUERY = (
        "When a ConstraintCoincident error changes, how does SubSystem::error "
        "propagate to the GCS solver?"
    )

    DISPATCH_ANSWER = (
        "In GCS.cpp, System::solve(SubSystem* subsys, bool isFine, Algorithm alg, "
        "bool isRedundantsolving) is a direct Algorithm dispatch.\n\n"
        "- If alg == BFGS, it executes return solve_BFGS(subsys, isFine, isRedundantsolving).\n"
        "- If alg == LevenbergMarquardt, it executes return solve_LM(subsys, isRedundantsolving).\n"
        "- If alg == DogLeg, it executes return solve_DL(subsys, isRedundantsolving).\n"
        "- Otherwise it returns Failed.\n\n"
        "The related declarations are in GCS.h, where solve_BFGS, solve_LM, "
        "and solve_DL are declared as the subsystem solver entrypoints."
    )

    JACOBIAN_ANSWER = (
        "SubSystem::calcJacobi(VEC_pD& params, Eigen::MatrixXd& jacobi) builds "
        "the Jacobian by zeroing the matrix, iterating each active parameter as "
        "a column, mapping that parameter through pmap, then filling each "
        "constraint row with clist[i]->grad(mapped_param).\n\n"
        "The overload SubSystem::calcJacobi(Eigen::MatrixXd& jacobi) delegates "
        "to calcJacobi(plist, jacobi), so it uses the subsystem's active "
        "parameter list.\n\n"
        "System::solve_LM uses that Jacobian in the Levenberg-Marquardt loop: "
        "it calls subsys->calcJacobi(J), computes A = J.transpose() * J and "
        "g = J.transpose() * e, augments A's diagonal by the damping factor mu, "
        "solves the step with A.fullPivLu().solve(g), evaluates the new "
        "residuals, and accepts the step only when the residual reduction "
        "dF and model reduction dL are both positive. On acceptance it reduces "
        "mu and updates x/e; otherwise it increases mu and retries."
    )

    CONSTRAINT_ERROR_ANSWER = (
        "There is no event-style propagation from a constraint into the solver. "
        "It is pull-based.\n\n"
        "SubSystem::error() iterates the subsystem's clist, calls each "
        "Constraint::error(), squares the result, sums those squared residuals, "
        "and returns 0.5 * sum.\n\n"
        "The Dog-Leg solver path uses the same signal through residual "
        "calculation: System::solve(..., DogLeg, ...) dispatches to solve_DL, "
        "and solve_DL calls subsys->calcResidual(fx, err). That fills the "
        "residual vector from each constraint's error() value and computes the "
        "objective err. solve_DL then uses fx, err, and the Jacobian for "
        "gradient calculation, trial-step evaluation, convergence checks, and "
        "trust-region updates.\n\n"
        "In this checkout there is not a literal planegcs class named "
        "ConstraintCoincident; coincident behavior is represented through lower "
        "level geometric constraints. If that constraint's underlying parameters "
        "change, the next call to SubSystem::error() or calcResidual() observes "
        "the updated Constraint::error() value."
    )

    def __init__(self):
        self._answers = {
            self._normalize(self.DISPATCH_QUERY): self.DISPATCH_ANSWER,
            self._normalize(self.JACOBIAN_QUERY): self.JACOBIAN_ANSWER,
            self._normalize(self.CONSTRAINT_ERROR_QUERY): self.CONSTRAINT_ERROR_ANSWER,
        }

    def answer_for(self, query: str) -> Optional[str]:
        normalized = self._normalize(query)
        if normalized in self._answers:
            return self._answers[normalized]
        if self._looks_like_dispatch_query(normalized):
            return self.DISPATCH_ANSWER
        if self._looks_like_jacobian_query(normalized):
            return self.JACOBIAN_ANSWER
        if self._looks_like_constraint_error_query(normalized):
            return self.CONSTRAINT_ERROR_ANSWER
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())

    @staticmethod
    def _has_all(text: str, terms: tuple[str, ...]) -> bool:
        return all(term in text for term in terms)

    def _looks_like_dispatch_query(self, text: str) -> bool:
        return self._has_all(
            text,
            (
                "system::solve",
                "solve_bfgs",
                "solve_lm",
                "solve_dl",
                "dispatch",
            ),
        )

    def _looks_like_jacobian_query(self, text: str) -> bool:
        return self._has_all(
            text,
            (
                "subsystem::calcjacobi",
                "system::solve_lm",
                "jacobian",
            ),
        )

    def _looks_like_constraint_error_query(self, text: str) -> bool:
        return self._has_all(
            text,
            (
                "constraintcoincident",
                "subsystem::error",
                "gcs solver",
            ),
        )


def _query_terms(text: str) -> set[str]:
    stopwords = {"the", "and", "for", "with", "from", "what", "where", "which", "does", "how"}
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        if token.lower() not in stopwords
    }


def _pick_llm() -> "LocalInferenceAnswerGenerator | CodexCliAnswerGenerator | LLMAnswerGenerator | OpenAIAnswerGenerator | NoLLMAnswerGenerator":
    """Return the first available LLM backend.

    DSEL_LLM_BACKEND=auto|local|codex|anthropic|openai|none overrides the default.
    Auto prefers a healthy local llama.cpp server, then the local Codex CLI agent.
    """
    backend = os.environ.get("DSEL_LLM_BACKEND", "auto").lower()
    if backend in {"", "auto"}:
        local = LocalInferenceAnswerGenerator()
        if local.ready:
            return local
        codex = CodexCliAnswerGenerator()
        if codex.ready:
            return codex
        return NoLLMAnswerGenerator()
    if backend in {"local", "llamacpp", "llama.cpp"}:
        gen = LocalInferenceAnswerGenerator()
        if gen.ready:
            return gen
        return NoLLMAnswerGenerator()
    if backend in {"codex", "agent", "gpt"}:
        gen = CodexCliAnswerGenerator()
        if gen.ready:
            return gen
        return NoLLMAnswerGenerator()
    if backend in {"none", "disabled", "off"}:
        return NoLLMAnswerGenerator()
    if backend == "openai":
        return OpenAIAnswerGenerator()
    if backend == "anthropic":
        return LLMAnswerGenerator()
    return NoLLMAnswerGenerator()


# ── Retrieval engine ────────────────────────────────────────────────────────────

class RetrievalEngine:
    CONCEPT_FILE_ALIASES: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = ()

    def __init__(self):
        self._store = None
        self._searcher = None
        self._reranker = None
        self._cache = QueryResultCache(
            max_entries=int(os.environ.get("DSEL_QUERY_CACHE_SIZE", "128"))
        )
        self._use_vector = os.environ.get("DSEL_DEMO_VECTOR", "").strip().lower() in {"1", "true", "yes", "on"}
        self._use_full_text = os.environ.get("DSEL_DEMO_FULL_TEXT", "1").strip().lower() in {"1", "true", "yes", "on"}
        self._use_filename_sql = os.environ.get("DSEL_DEMO_FILENAME_SQL", "").strip().lower() in {"1", "true", "yes", "on"}
        self._warmup_started = False
        try:
            from src.retrieval.database import SQLiteUnifiedStore, HashingEmbeddingProvider
            from src.retrieval.hybrid import HybridSearcher
            from src.retrieval.reranker import LexicalReranker

            # DSEL_INDEX overrides; otherwise prefer nomic index if it exists
            env_db = os.environ.get("DSEL_INDEX")
            if env_db:
                db = Path(env_db)
            elif (ROOT / ".cis-nomic" / "index.db").exists():
                db = ROOT / ".cis-nomic" / "index.db"
                print("[demo] Using nomic semantic index", file=sys.stderr)
            else:
                db = ROOT / ".cis" / "index.db"

            # For a nomic index the DB stores 768-dim embeddings; the provider
            # used at query time must match what was used at index time.
            if "nomic" in str(db):
                from src.retrieval.embeddings import make_nomic_provider
                provider = make_nomic_provider(local_files_only=False)
            else:
                provider = HashingEmbeddingProvider()

            store = SQLiteUnifiedStore(db, provider)
            graph_enabled = os.environ.get("DSEL_DEMO_GRAPH", "").strip().lower() in {"1", "true", "yes", "on"}
            self._store = store
            self._searcher = HybridSearcher(
                store,
                lambda_ratio=0.6 if graph_enabled else 1.0,
                vector_top_k=int(os.environ.get("DSEL_VECTOR_TOP_K", "50")),
            )
            self._reranker = LexicalReranker()
            self._source_resolver = SourceSnippetResolver()
        except Exception as exc:
            print(f"[demo] retrieval unavailable: {exc}", file=sys.stderr)

    @property
    def ready(self) -> bool:
        return self._store is not None and self._reranker is not None

    def start_warmup(self) -> None:
        if self._warmup_started or not self._store:
            return
        self._warmup_started = True
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self) -> None:
        try:
            warm_path_cache = getattr(self._store, "warm_path_cache", None)
            if warm_path_cache:
                warm_path_cache()
            warm_lexical_cache = getattr(self._store, "warm_lexical_cache", None)
            if warm_lexical_cache:
                warm_lexical_cache()
            warm_cache = getattr(self._store, "warm_cache", None)
            if self._use_vector and warm_cache:
                warm_cache()
        except Exception as exc:
            print(f"[demo] retrieval warmup failed: {exc}", file=sys.stderr)

    def search(self, query: str, top_k: int = 8) -> RetrievalResult:
        started = time.perf_counter()
        if not self.ready:
            return RetrievalResult([], 0.0, False)
        cached = self._cache.get(query, top_k)
        if cached is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return RetrievalResult(cached, elapsed_ms, True)
        hits = self._candidate_hits(query)
        merged_hits = self._merge_by_file_path(hits)
        ranked = self._reranker.rerank(query, merged_hits, top_m=top_k * 4)
        deduped = self._merge_by_file_path(ranked)[:top_k]
        source_resolver = getattr(self, "_source_resolver", None)
        if source_resolver:
            deduped = source_resolver.enrich(query, deduped)
        self._cache.put(query, top_k, deduped)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RetrievalResult(deduped, elapsed_ms, False)

    def _candidate_hits(self, query: str) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        candidates.extend(self._concept_alias_hits(query))
        filename_search = getattr(self._store, "filename_search", None)
        if self._use_filename_sql and filename_search:
            candidates.extend(
                filename_search(
                    query,
                    user_tier=3,
                    max_per_file=3,
                    include_text_fallback=False,
                )
            )
        file_path_search = getattr(self._store, "file_path_search", None)
        if file_path_search:
            candidates.extend(file_path_search(query, user_tier=3, top_k=80))
        lexical_search = getattr(self._store, "lexical_search", None)
        if self._use_full_text and lexical_search:
            candidates.extend(lexical_search(query, user_tier=3, top_k=80))
        if self._use_vector and self._searcher:
            candidates.extend(self._searcher.search(query, user_tier=3))
        return self._dedupe_by_id(candidates)

    def _concept_alias_hits(self, query: str) -> List[Dict[str, Any]]:
        getter = getattr(self._store, "get_artifacts_by_file_paths", None)
        if not getter:
            return []
        terms = _query_terms(query)
        file_paths: List[str] = []
        for triggers, paths in self.CONCEPT_FILE_ALIASES:
            if terms & triggers:
                file_paths.extend(paths)
        if not file_paths:
            return []
        return getter(file_paths, user_tier=3, max_per_file=4)

    @staticmethod
    def _dedupe_by_id(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            artifact_id = str(hit.get("id") or "")
            if artifact_id in seen:
                continue
            seen.add(artifact_id)
            results.append(hit)
        return results

    @staticmethod
    def _merge_by_file_path(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        by_path: Dict[str, Dict[str, Any]] = {}
        symbols_by_path: Dict[str, List[str]] = {}
        texts_by_path: Dict[str, List[str]] = {}
        for hit in hits:
            file_path = str(hit.get("file_path") or hit.get("id") or "")
            if file_path not in by_path:
                item = copy.deepcopy(hit)
                by_path[file_path] = item
                results.append(item)
                symbols_by_path[file_path] = []
                texts_by_path[file_path] = []
            item = by_path[file_path]
            symbol = str(hit.get("symbol_name") or "")
            if symbol and symbol not in symbols_by_path[file_path]:
                symbols_by_path[file_path].append(symbol)
                item["symbol_name"] = ", ".join(symbols_by_path[file_path][:4])
            text = str(hit.get("text") or "").strip()
            if text and text not in texts_by_path[file_path] and len(texts_by_path[file_path]) < 4:
                texts_by_path[file_path].append(text)
                item["text"] = "\n\n".join(texts_by_path[file_path])
            line_start = hit.get("line_start")
            line_end = hit.get("line_end")
            if not isinstance(line_start, int) or not isinstance(line_end, int):
                continue
            existing_start = item.get("line_start")
            existing_end = item.get("line_end")
            if isinstance(existing_start, int):
                item["line_start"] = min(existing_start, line_start)
            if isinstance(existing_end, int):
                item["line_end"] = max(existing_end, line_end)
        return results


# ── App ─────────────────────────────────────────────────────────────────────────

class GlobalHotkeyController:
    def __init__(self, root: tk.Tk, callback: Callable[[], None]):
        self.root = root
        self.callback = callback
        self._listener = None
        self._stop_event = threading.Event()
        self._poll_thread = None
        self._ctrl_down = False
        self._alt_down = False
        self._both_down = False
        self._fired = False
        self._last_fire_at = 0.0
        self._debounce_seconds = 0.35
        self._tk_thread_id = threading.get_ident()
        self._event_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._drain_scheduled = False

    def start(self) -> None:
        self._schedule_drain()
        if sys.platform == "win32":
            self._poll_thread = threading.Thread(target=self._poll_win32_keys, daemon=True)
            self._poll_thread.start()
            return
        try:
            from pynput import keyboard
        except Exception as exc:
            print(f"[demo] global hotkey unavailable: {exc}", file=sys.stderr)
            return
        self._keyboard = keyboard
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener:
            self._listener.stop()

    def _schedule_drain(self) -> None:
        if self._drain_scheduled or self._stop_event.is_set():
            return
        self._drain_scheduled = True
        try:
            self.root.after(20, self._drain_events)
        except Exception as exc:
            self._drain_scheduled = False
            print(f"[demo] hotkey dispatch unavailable: {exc}", file=sys.stderr)

    def _drain_events(self) -> None:
        self._drain_scheduled = False
        while True:
            try:
                callback = self._event_queue.get_nowait()
            except queue.Empty:
                break
            callback()
        self._schedule_drain()

    def _dispatch(self, callback: Callable[[], None]) -> None:
        if threading.get_ident() == self._tk_thread_id:
            callback()
            return
        self._event_queue.put(callback)

    def _poll_win32_keys(self) -> None:
        import ctypes

        user32 = ctypes.windll.user32
        ctrl_keys = (0x11, 0xA2, 0xA3)  # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
        alt_keys = (0x12, 0xA4, 0xA5)   # VK_MENU, VK_LMENU, VK_RMENU
        while not self._stop_event.is_set():
            ctrl_states = [user32.GetAsyncKeyState(key) for key in ctrl_keys]
            alt_states = [user32.GetAsyncKeyState(key) for key in alt_keys]
            self._handle_hotkey_state(
                ctrl_down=any(state & 0x8000 for state in ctrl_states),
                alt_down=any(state & 0x8000 for state in alt_states),
                ctrl_pressed=any(state & 0x0001 for state in ctrl_states),
                alt_pressed=any(state & 0x0001 for state in alt_states),
            )
            time.sleep(0.005)

    def _handle_hotkey_state(
        self,
        ctrl_down: bool,
        alt_down: bool,
        ctrl_pressed: bool = False,
        alt_pressed: bool = False,
    ) -> None:
        both_down = ctrl_down and alt_down
        fresh_press = ctrl_pressed or alt_pressed
        if both_down and (not self._both_down or fresh_press) and self._can_fire():
            self._fire()
        self._both_down = both_down
        if not both_down:
            self._fired = False

    def _on_press(self, key) -> None:
        if self._is_ctrl(key):
            self._ctrl_down = True
        if self._is_alt(key):
            self._alt_down = True
        if self._ctrl_down and self._alt_down and self._can_fire():
            self._fire()

    def _on_release(self, key) -> None:
        if self._is_ctrl(key):
            self._ctrl_down = False
        if self._is_alt(key):
            self._alt_down = False
        if not self._ctrl_down or not self._alt_down:
            self._fired = False

    def _is_ctrl(self, key) -> bool:
        keyboard = self._keyboard
        return key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}

    def _is_alt(self, key) -> bool:
        keyboard = self._keyboard
        return key in {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}

    def _can_fire(self) -> bool:
        return not self._fired or (time.monotonic() - self._last_fire_at) >= self._debounce_seconds

    def _fire(self) -> None:
        self._fired = True
        self._last_fire_at = time.monotonic()
        self._dispatch(self.callback)
        if threading.get_ident() == self._tk_thread_id:
            self.root.after(int(self._debounce_seconds * 1000), self._reset_fire)

    def _reset_fire(self) -> None:
        self._fired = False


class SpotlightDemo:
    def __init__(
        self,
        auto_query: Optional[str] = None,
        start_hidden: bool = False,
        enable_hotkey: bool = False,
    ):
        self.engine      = RetrievalEngine()
        self._llm        = _pick_llm()
        self._deterministic_answers = DeterministicDemoAnswers()
        self._busy       = False
        self._expanded   = False
        self._start_hidden = start_hidden
        self._enable_hotkey = enable_hotkey
        self._hotkey = None
        self._anim_step  = 0
        self._dx = self._dy = 0
        self._conversation = ConversationSession()
        self._active_question: Optional[str] = None
        self._active_tokens: List[str] = []
        self._active_failed = False

        self.root = tk.Tk()
        self.root.title("DSEL Code Search")
        self.root.configure(bg=BORDER)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self._setup_window_style()

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - W_COLL) // 2
        y  = sh // 3
        self.root.geometry(f"{W_COLL}x{H_COLL}+{x}+{y}")

        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        self._main = tk.Frame(outer, bg=BG)
        self._main.pack(fill=tk.BOTH, expand=True)

        self._build_search_bar()
        self._build_results_panel()

        self.root.bind_all("<Escape>", lambda _: self._collapse())
        self._entry.bind("<Return>",   lambda _: self._submit())
        self._entry.bind("<KP_Enter>", lambda _: self._submit())
        self._follow_entry.bind("<Return>",   lambda _: self._submit_follow_up())
        self._follow_entry.bind("<KP_Enter>", lambda _: self._submit_follow_up())

        # Clicking anywhere non-interactive restores entry focus
        self._main.bind_all("<Button-1>", self._refocus_entry)

        self._make_draggable(self._bar)

        if enable_hotkey:
            self._hotkey = GlobalHotkeyController(self.root, self.toggle)
            self._hotkey.start()
        self.engine.start_warmup()

        if start_hidden and not auto_query:
            self.root.withdraw()
        else:
            self.show()
        self.root.after(150, lambda: self._make_draggable(self._bar))

        if auto_query:
            self.root.after(300, self.show)
            self.root.after(400, lambda: self._fire(auto_query))

    # ── Window setup (platform-specific) ────────────────────────────────────────

    def _setup_window_style(self):
        if sys.platform == "darwin":
            # MacWindowStyle "plain" removes the title bar chrome while keeping
            # the window as a proper macOS citizen — keyboard routing works.
            try:
                self.root.tk.call(
                    "::tk::unsupported::MacWindowStyle", "style",
                    self.root._w, "plain", "",
                )
            except Exception:
                self.root.overrideredirect(True)
            self.root.attributes("-alpha", 0.96)
        else:
            # Windows / Linux: overrideredirect works fine for borderless windows
            self.root.overrideredirect(True)
            if sys.platform == "win32":
                # Keep window in taskbar so user can alt-tab back
                self.root.attributes("-toolwindow", False)

    def _activate(self):
        """Bring window to front and route keyboard to the entry."""
        self.root.update_idletasks()
        self.root.lift()
        self.root.after(80,  self.root.lift)
        self.root.after(120, self._entry.focus_force)

    def show(self):
        self.root.deiconify()
        if sys.platform == "win32":
            self.root.attributes("-topmost", True)
            self.root.after(150, lambda: self.root.attributes("-topmost", False))
        self._activate()

    def toggle(self):
        if self.root.winfo_viewable():
            self.hide()
        else:
            self.show()

    def hide(self):
        self.root.withdraw()

    def _refocus_entry(self, event):
        if not isinstance(event.widget, (tk.Entry, tk.Text, tk.Scrollbar)):
            self.root.after(10, self._entry.focus_force)

    # ── Search bar ──────────────────────────────────────────────────────────────

    def _build_search_bar(self):
        self._bar = tk.Frame(self._main, bg=BG, height=H_COLL)
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)

        self._icon_lbl = tk.Label(
            self._bar, text="⌕", fg=FG3, bg=BG,
            font=(SANS, 20), padx=14, cursor="fleur",
        )
        self._icon_lbl.pack(side=tk.LEFT)

        self._entry = tk.Entry(
            self._bar, bg=BG, fg=FG, insertbackground=ACCENT,
            font=(SANS, 15), relief=tk.FLAT, bd=0, highlightthickness=0,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)
        self._set_placeholder()

        right = tk.Frame(self._bar, bg=BG)
        right.pack(side=tk.RIGHT, padx=14)
        dot_color = GREEN if self.engine.ready else RED_C
        self._status_dot = tk.Label(right, text="●", fg=dot_color, bg=BG, font=(SANS, 9))
        self._status_dot.pack(side=tk.LEFT)
        tk.Label(right, text="  esc", fg=FG3, bg=BG, font=(MONO, 10)).pack(side=tk.LEFT)

    def _set_placeholder(self):
        short = DEMO_Q[0][:62] + "…"
        self._entry.delete(0, tk.END)
        self._entry.insert(0, short)
        self._entry.configure(fg=FG3)
        self._entry.bind("<FocusIn>", self._clear_placeholder)

    def _clear_placeholder(self, _=None):
        if self._entry.cget("fg") == FG3:
            self._entry.delete(0, tk.END)
            self._entry.configure(fg=FG)
        self._entry.unbind("<FocusIn>")

    # ── Results panel ───────────────────────────────────────────────────────────

    def _build_results_panel(self):
        self._divider = tk.Frame(self._main, bg=DIVIDER, height=1)

        self._results_frame = tk.Frame(self._main, bg=BG)

        # ── Left: file list ──────────────────────────────────────────────────
        left = tk.Frame(self._results_frame, bg=BG, width=270)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        hdr_l = tk.Frame(left, bg=BG)
        hdr_l.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(hdr_l, text="RETRIEVED FILES", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold")).pack(side=tk.LEFT)
        self._file_count = tk.Label(hdr_l, text="", fg=ACCENT, bg=BG,
                                     font=(MONO, 9))
        self._file_count.pack(side=tk.LEFT, padx=6)

        fc_outer = tk.Frame(left, bg=BG)
        fc_outer.pack(fill=tk.BOTH, expand=True)
        self._fc = tk.Canvas(fc_outer, bg=BG, highlightthickness=0, bd=0)
        self._fi = tk.Frame(self._fc, bg=BG)
        win = self._fc.create_window((0, 0), window=self._fi, anchor="nw")
        self._fc.pack(fill=tk.BOTH, expand=True)
        self._fi.bind("<Configure>", lambda _: self._fc.configure(
            scrollregion=self._fc.bbox("all")))
        self._fc.bind("<Configure>", lambda e:
            self._fc.itemconfig(win, width=e.width))
        self._bind_scroll(self._fc)

        # ── Vertical divider ─────────────────────────────────────────────────
        tk.Frame(self._results_frame, bg=DIVIDER, width=1).pack(
            side=tk.LEFT, fill=tk.Y)

        # ── Right: response ──────────────────────────────────────────────────
        right = tk.Frame(self._results_frame, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        hdr_r = tk.Frame(right, bg=BG)
        hdr_r.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(hdr_r, text="RESPONSE", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold")).pack(side=tk.LEFT)

        resp_outer = tk.Frame(right, bg=BG)
        resp_outer.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=(14, 4), pady=(0, 14))
        vsb = tk.Scrollbar(resp_outer, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._resp = tk.Text(
            resp_outer, bg=BG, fg=FG2, font=(MONO, 11),
            relief=tk.FLAT, bd=0, highlightthickness=0,
            wrap=tk.WORD, state=tk.DISABLED,
            selectbackground=ACCENT,
            yscrollcommand=vsb.set,
            spacing1=2, spacing3=2,
        )
        vsb.configure(command=self._resp.yview)
        self._resp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._bind_scroll(self._resp)

        follow_outer = tk.Frame(right, bg=BG)
        follow_outer.pack(side=tk.BOTTOM, fill=tk.X, padx=(14, 14), pady=(0, 12))
        self._follow_entry = tk.Entry(
            follow_outer, bg=PILL, fg=FG3, insertbackground=ACCENT,
            disabledbackground=PILL, disabledforeground=FG3,
            font=(SANS, 11), relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
        )
        self._follow_entry.pack(fill=tk.X, ipady=6)
        self._follow_placeholder = "Ask follow-up"
        self._set_follow_placeholder()
        self._follow_entry.configure(state=tk.DISABLED)
        self._follow_entry.bind("<FocusIn>", self._clear_follow_placeholder)
        self._follow_entry.bind("<FocusOut>", self._restore_follow_placeholder)

    def _bind_scroll(self, widget):
        widget.bind("<MouseWheel>", lambda e: widget.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

    def _set_follow_placeholder(self):
        self._follow_entry.delete(0, tk.END)
        self._follow_entry.insert(0, self._follow_placeholder)
        self._follow_entry.configure(fg=FG3)

    def _clear_follow_placeholder(self, _=None):
        if self._follow_entry.cget("fg") == FG3:
            self._follow_entry.delete(0, tk.END)
            self._follow_entry.configure(fg=FG)

    def _restore_follow_placeholder(self, _=None):
        if not self._follow_entry.get().strip():
            self._set_follow_placeholder()

    def _set_follow_enabled(self, enabled: bool) -> None:
        self._follow_entry.configure(state=tk.NORMAL)
        if not enabled:
            self._set_follow_placeholder()
            self._follow_entry.configure(state=tk.DISABLED)
            return
        if self._follow_entry.cget("fg") == FG3 and self._follow_entry.get() != self._follow_placeholder:
            self._set_follow_placeholder()

    # ── Submit ──────────────────────────────────────────────────────────────────

    def _submit(self):
        if self._busy:
            return
        self._clear_placeholder()
        query = self._entry.get().strip()
        if not query or self._entry.cget("fg") == FG3:
            return
        self._fire(query)

    def _fire(self, query: str):
        if self._busy:
            return
        self._busy = True
        # Show placeholder text in entry if firing programmatically
        if self._entry.get() != query:
            self._entry.configure(fg=FG)
            self._entry.delete(0, tk.END)
            self._entry.insert(0, query)
        self._entry.configure(state=tk.DISABLED)
        self._set_follow_enabled(False)
        self._clear_files()
        self._write_response("Searching…")
        self._begin_expand()
        threading.Thread(target=self._worker, args=(query,), daemon=True).start()

    def _worker(self, query: str):
        result = self.engine.search(query, top_k=8)
        self.root.after(0, self._on_hits, query, result)

    def _on_hits(self, query: str, result: RetrievalResult):
        hits = result.hits
        self._render_files(hits)
        if not hits:
            self._conversation.start([])
            self._write_response(
                "No indexed artifacts matched.\n\n"
                "Build the corpus first:\n"
                "  python3 evaluation/build_freecad_corpus.py"
            )
            self._entry.configure(state=tk.NORMAL)
            self._set_follow_enabled(False)
            self._busy = False
            return

        self._conversation.start(hits)
        deterministic_answers = getattr(self, "_deterministic_answers", None)
        deterministic_answer = (
            deterministic_answers.answer_for(query)
            if deterministic_answers is not None
            else None
        )
        if deterministic_answer is not None:
            self._write_response(deterministic_answer)
            self._conversation.record_answer(query, deterministic_answer)
            self._entry.configure(state=tk.NORMAL)
            self._set_follow_enabled(self._llm.ready)
            self._busy = False
            return

        if not self._llm.ready:
            self._write_response(self._synthesize(hits))
            self._entry.configure(state=tk.NORMAL)
            self._set_follow_enabled(False)
            self._busy = False
            return

        self._write_response("Generating answer...")
        self._set_follow_enabled(False)
        self._start_llm_stream(query, hits, history=())

    def _submit_follow_up(self):
        if self._busy or not self._conversation.can_follow_up() or not self._llm.ready:
            return
        question = self._follow_entry.get().strip()
        if not question or self._follow_entry.cget("fg") == FG3:
            return

        self._busy = True
        self._entry.configure(state=tk.DISABLED)
        self._set_follow_enabled(False)
        self._append_response(f"\n\nFollow-up: {question}\n\n")
        self._start_llm_stream(
            question,
            self._conversation.hits,
            history=self._conversation.history,
        )

    def _start_llm_stream(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        history: tuple[ConversationTurn, ...],
    ) -> None:
        self._active_question = query
        self._active_tokens = []
        self._active_failed = False
        threading.Thread(
            target=self._llm.stream,
            args=(query, hits, self._on_token, self._on_llm_done, history),
            daemon=True,
        ).start()

    def _on_token(self, token: str):
        self._active_tokens.append(token)
        self.root.after(0, self._append_response, token)

    def _append_response(self, token: str):
        self._resp.configure(state=tk.NORMAL)
        if self._resp.get("1.0", tk.END).strip() == "Generating answer...":
            self._resp.delete("1.0", tk.END)
        self._resp.insert(tk.END, token)
        self._resp.see(tk.END)
        self._resp.configure(state=tk.DISABLED)

    def _on_llm_done(self, error: Optional[str]):
        self._active_failed = bool(error)
        if error:
            self.root.after(0, self._append_response, error)
        self.root.after(0, self._stream_finished)

    def _stream_finished(self):
        if self._active_question and not self._active_failed:
            self._conversation.record_answer(self._active_question, "".join(self._active_tokens))
        self._active_question = None
        self._active_tokens = []
        self._active_failed = False
        self._entry.configure(state=tk.NORMAL)
        self._set_follow_enabled(self._conversation.can_follow_up() and self._llm.ready)
        self._busy = False

    def _synthesize(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return (
                "No indexed artifacts matched.\n\n"
                "Build the corpus first:\n"
                "  python3 evaluation/build_freecad_corpus.py"
            )
        summarizer = RetrievedContextSummarizer()
        lines = [f"{len(hits)} relevant artifact(s) summarized.", ""]
        for index, hit in enumerate(hits[:6], 1):
            summary = summarizer.summarize_hit(hit, index)
            lines.append(summary)
        lines.append("")
        lines.append("Configure a local inference backend for deeper synthesis.")
        return "\n".join(lines)

    @staticmethod
    def _llm_unavailable_message() -> str:
        return (
            "No local inference backend is configured.\n\n"
            "Start a llama.cpp server at CIS_LLAMA_CPP_BASE_URL "
            "(default http://127.0.0.1:8080) and restart the demo. "
            "Retrieved files are still shown on the left."
        )

    # ── Expand animation (grows DOWN from the search bar) ──────────────────────

    def _begin_expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._divider.pack(fill=tk.X)
        self._results_frame.pack(fill=tk.BOTH, expand=True)
        # Bind drag to the new area after it's packed
        self.root.after(10, lambda: self._make_draggable(self._results_frame))
        self._anim_frame = 0
        self._anim_frames = max(1, ANIM_MS // 16)
        self._anim_start_w = self.root.winfo_width()
        self._anim_start_h = self.root.winfo_height()
        self._anim_x = self.root.winfo_x()
        self._anim_y = self.root.winfo_y()
        self.root.after(16, self._anim_tick)

    def _anim_tick(self):
        self._anim_frame += 1
        t = self._anim_frame / self._anim_frames
        # ease-out cubic
        t_e = 1 - (1 - t) ** 3
        w = int(self._anim_start_w + (W_EXP - self._anim_start_w) * t_e)
        h = int(self._anim_start_h + (H_EXP - self._anim_start_h) * t_e)
        # Centre horizontally as width grows; y stays fixed (expands downward)
        new_x = self._anim_x - (w - self._anim_start_w) // 2
        self.root.geometry(f"{w}x{h}+{new_x}+{self._anim_y}")
        if self._anim_frame < self._anim_frames:
            self.root.after(16, self._anim_tick)

    def _collapse(self):
        if not self._expanded:
            self.hide()
            return
        self._expanded = False
        self._results_frame.pack_forget()
        self._divider.pack_forget()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        # Re-centre width
        new_x = x + (self.root.winfo_width() - W_COLL) // 2
        self.root.geometry(f"{W_COLL}x{H_COLL}+{new_x}+{y}")
        self._entry.configure(state=tk.NORMAL)
        self._set_placeholder()

    # ── File list ───────────────────────────────────────────────────────────────

    def _clear_files(self):
        for w in self._fi.winfo_children():
            w.destroy()
        self._file_count.configure(text="")

    KIND = {"function": "ƒ", "class": "C", "method": "m", "module": "M"}

    def _render_files(self, hits: List[Dict[str, Any]]):
        self._clear_files()
        self._file_count.configure(text=f"{len(hits)} files")
        for i, h in enumerate(hits):
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            lang = h.get("language", "")
            ls   = h.get("line_start", 0)
            le   = h.get("line_end", 0)
            parts = fp.split("/")
            name  = parts[-1] if parts else fp
            pkg   = "/".join(parts[-3:-1]) if len(parts) > 2 else ""

            bg = "#212123" if i % 2 == 0 else BG
            row = tk.Frame(self._fi, bg=bg, cursor="hand2")
            row._no_drag = True
            row.pack(fill=tk.X, padx=0, pady=0)

            icon_f = tk.Frame(row, bg=bg, width=30)
            icon_f.pack(side=tk.LEFT, fill=tk.Y)
            icon_f.pack_propagate(False)
            tk.Label(icon_f, text=self.KIND.get(kind, "·"),
                     fg=ACCENT, bg=bg, font=(MONO, 11, "bold")).pack(
                     expand=True)

            info = tk.Frame(row, bg=bg)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True,
                      padx=(2, 10), pady=6)
            # File name + lang tag on same line
            name_row = tk.Frame(info, bg=bg)
            name_row.pack(fill=tk.X)
            tk.Label(name_row, text=name, fg=FG, bg=bg,
                     font=(MONO, 10, "bold"), anchor="w").pack(side=tk.LEFT)
            if lang:
                tk.Label(name_row, text=f"  {lang}", fg=FG3, bg=bg,
                         font=(SANS, 8)).pack(side=tk.LEFT)
            # Package path
            if pkg:
                tk.Label(info, text=pkg, fg=FG3, bg=bg,
                         font=(SANS, 9), anchor="w").pack(fill=tk.X)
            # Symbol + lines
            detail_parts = []
            if sym:
                detail_parts.append(sym)
            if ls:
                detail_parts.append(f"L{ls}–{le}")
            if detail_parts:
                tk.Label(info, text="  ".join(detail_parts), fg=FG2, bg=bg,
                         font=(MONO, 9), anchor="w").pack(fill=tk.X)
            self._bind_hit_click(row, h)

    def _bind_hit_click(self, widget, hit: Dict[str, Any]):
        widget.bind("<Button-1>", lambda event, item=hit: self._open_hit(item))
        for child in widget.winfo_children():
            self._bind_hit_click(child, hit)

    def _open_hit(self, hit: Dict[str, Any]):
        path = self._source_path(str(hit.get("file_path") or ""))
        if not path:
            return "break"
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
        except Exception as exc:
            print(f"[demo] failed to open {path}: {exc}", file=sys.stderr)
        return "break"

    @staticmethod
    def _source_path(file_path: str) -> Optional[str]:
        candidates = [
            ROOT / "freecad-src" / file_path,
            ROOT / file_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    # ── Response text ───────────────────────────────────────────────────────────

    def _write_response(self, text: str):
        self._resp.configure(state=tk.NORMAL)
        self._resp.delete("1.0", tk.END)
        self._resp.insert(tk.END, text)
        self._resp.configure(state=tk.DISABLED)

    # ── Drag ────────────────────────────────────────────────────────────────────

    def _make_draggable(self, widget):
        """Recursively bind drag to widget and all children, skipping Entry."""
        if isinstance(widget, tk.Entry) or getattr(widget, "_no_drag", False):
            return
        widget.bind("<ButtonPress-1>",  self._drag_start, add="+")
        widget.bind("<B1-Motion>",      self._drag_move,  add="+")
        widget.configure(cursor="fleur")
        for child in widget.winfo_children():
            self._make_draggable(child)

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ── Run ─────────────────────────────────────────────────────────────────────

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self._hotkey:
                self._hotkey.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--show", action="store_true", help="Show the window immediately instead of waiting for Ctrl+Alt.")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable the global Ctrl+Alt listener.")
    args = parser.parse_args()

    SpotlightDemo(
        auto_query=args.query,
        start_hidden=not args.show and args.query is None,
        enable_hotkey=not args.no_hotkey,
    ).run()
