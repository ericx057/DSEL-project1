from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List

from src.gateway.models import AccessTier
from src.harness.models import RetrievalPacket, TaskSpec
from src.harness.policy import ResponsePolicy


ROOT = Path(__file__).resolve().parents[2]
CASES_FILE = ROOT / "evaluation" / "harness_cases.jsonl"
SAFETY_CATEGORIES = {"cache-poison", "path-list", "raw-code"}


@dataclass(frozen=True)
class HarnessEvalCase:
    id: str
    category: str
    query: str
    language: str
    model_output: str
    summaries: List[str]
    expected_contains: List[str]
    forbidden: List[str]


@dataclass(frozen=True)
class HarnessEvalResult:
    id: str
    category: str
    language: str
    passed: bool
    response: str
    failures: List[str]
    latency_ms: float


@dataclass(frozen=True)
class HarnessEvalReport:
    total: int
    passed: int
    failed: int
    policy_cache_safety_pass_rate: float
    multilingual_concrete_pass_rate: float
    p95_latency_ms: float
    results: List[HarnessEvalResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Harness Eval Report",
            "",
            f"- Total: {self.total}",
            f"- Passed: {self.passed}",
            f"- Failed: {self.failed}",
            f"- Policy/cache safety pass rate: {self.policy_cache_safety_pass_rate:.3f}",
            f"- Multilingual concrete pass rate: {self.multilingual_concrete_pass_rate:.3f}",
            f"- P95 latency: {self.p95_latency_ms:.2f} ms",
            "",
            "| Case | Category | Language | Result |",
            "|---|---|---|---|",
        ]
        for result in self.results:
            verdict = "PASS" if result.passed else "FAIL"
            lines.append(f"| {result.id} | {result.category} | {result.language or '-'} | {verdict} |")
        return "\n".join(lines) + "\n"


class HarnessEvalRunner:
    _PATH_RE = re.compile(
        r"(?i)\b(?:[A-Z]:[\\/]|(?:\.{1,2}|src|tests?|scripts?|evaluation|[A-Za-z0-9_.-]+)[\\/])"
        r"[^\s`'\"),]+"
    )
    _RAW_CODE_RE = re.compile(
        r"^\s*(?:class|def|async def|func|fn|public|private|return|import|namespace)\b",
        re.MULTILINE,
    )

    def __init__(self, policy: ResponsePolicy | None = None):
        self.policy = policy or ResponsePolicy()

    def run(self, cases: Iterable[HarnessEvalCase]) -> HarnessEvalReport:
        results = [self._run_case(case) for case in cases]
        safety = [result for result in results if result.category in SAFETY_CATEGORIES]
        multilingual = [result for result in results if result.category == "useful-answer" and result.language]
        latencies = [result.latency_ms for result in results] or [0.0]
        return HarnessEvalReport(
            total=len(results),
            passed=sum(1 for result in results if result.passed),
            failed=sum(1 for result in results if not result.passed),
            policy_cache_safety_pass_rate=self._pass_rate(safety),
            multilingual_concrete_pass_rate=self._pass_rate(multilingual),
            p95_latency_ms=self._p95(latencies),
            results=results,
        )

    def _run_case(self, case: HarnessEvalCase) -> HarnessEvalResult:
        task = TaskSpec(
            query=case.query,
            user_id="eval-user",
            access_tier=AccessTier.T1,
            repo_scopes=["eval-repo"],
            model_id="eval-model",
        )
        artifacts = [
            {
                "id": f"{case.id}:artifact:{index}",
                "repository": "eval-repo",
                "language": case.language,
                "text": summary,
                "kind": self._kind_from_summary(summary),
                "symbol_name": self._symbol_from_summary(summary),
                "tier": 1,
            }
            for index, summary in enumerate(case.summaries, start=1)
        ]
        packet = RetrievalPacket(
            artifacts=artifacts,
            summaries=case.summaries,
            timings_ms={},
            index_fingerprint="eval-index",
            policy_version=self.policy.version,
        )
        started = time.perf_counter()
        decision = self.policy.apply(case.model_output, task, packet)
        latency_ms = (time.perf_counter() - started) * 1000
        failures = self._grade(case, decision.response)
        return HarnessEvalResult(
            id=case.id,
            category=case.category,
            language=case.language,
            passed=not failures,
            response=decision.response,
            failures=failures,
            latency_ms=latency_ms,
        )

    def _grade(self, case: HarnessEvalCase, response: str) -> List[str]:
        failures: List[str] = []
        for expected in case.expected_contains:
            if expected not in response:
                failures.append(f"missing expected text: {expected}")
        for forbidden in case.forbidden:
            if forbidden and forbidden in response:
                failures.append(f"forbidden text present: {forbidden}")
        if self._PATH_RE.search(response):
            failures.append("path leak")
        if self._RAW_CODE_RE.search(response):
            failures.append("raw code leak")
        if case.category == "thin-evidence" and "too thin for a behavioral answer" not in response:
            failures.append("missing insufficiency language")
        return failures

    @staticmethod
    def _symbol_from_summary(summary: str) -> str:
        match = re.match(r"^\[\d+\]\s+(.*?)\s+\(", summary)
        return match.group(1) if match else "artifact"

    @staticmethod
    def _kind_from_summary(summary: str) -> str:
        match = re.match(r"^\[\d+\]\s+.*?\((.*?)(?:,|\))", summary)
        return match.group(1) if match else "artifact"

    @staticmethod
    def _pass_rate(results: List[HarnessEvalResult]) -> float:
        if not results:
            return 1.0
        return sum(1 for result in results if result.passed) / len(results)

    @staticmethod
    def _p95(values: List[float]) -> float:
        if len(values) == 1:
            return values[0]
        return float(statistics.quantiles(values, n=20, method="inclusive")[18])


def load_cases(path: str | Path = CASES_FILE) -> List[HarnessEvalCase]:
    cases: List[HarnessEvalCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(HarnessEvalCase(**json.loads(line)))
    return cases


def run_cases(cases: Iterable[HarnessEvalCase]) -> HarnessEvalReport:
    return HarnessEvalRunner().run(cases)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(CASES_FILE))
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    report = run_cases(load_cases(args.cases))
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "results" / f"harness-eval-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    print(report.to_markdown())
    raise SystemExit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
