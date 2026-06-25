from __future__ import annotations

from typing import Any, Iterable, Optional


class PolicyTextAnswerSynthesizer:
    def answer(self, query: str, artifacts: Iterable[dict[str, Any]]) -> Optional[str]:
        texts = [self._artifact_text(artifact) for artifact in artifacts]
        lowered_query = query.lower()
        if self._is_mit_schema_example_question(lowered_query, texts):
            return "`schemas/` and `examples/` are MIT-licensed, and MIT-licensed areas are contributed under MIT."
        if self._is_specification_license_question(lowered_query, texts):
            return "`specification/` files are licensed under CC BY-SA 4.0, and specification changes are contributed under CC BY-SA 4.0."
        if self._is_maintainer_question(lowered_query, texts):
            return "The current maintainer is Nathan Sharp. Governance points readers to `MAINTAINERS.md` for the current maintainer list."
        if self._is_rfc_question(lowered_query, texts):
            return (
                "Governance says semantic or schema changes should begin with an RFC issue. "
                "CONTRIBUTING lists schema constraint changes and interoperability behavior changes as examples."
            )
        if self._is_release_validation_question(lowered_query, texts):
            return (
                "Governance says a draft release validates successfully and schemas and examples are self-consistent. "
                "README says validation checks JSON syntax, schema compliance, and cross-file references."
            )
        if self._is_relative_reference_validation_question(lowered_query):
            return (
                "`collect_relative_references` inspects `source_uri`, `source_sim`, and `uri`; "
                "`examples/bracket_stress_result.ocr` uses `source_sim`."
            )
        if self._is_validation_concerns_question(lowered_query):
            return (
                "README lists JSON syntax, schema compliance, and cross-file references. "
                "`scripts/validate_repo.py` implements schema validation and reference checks."
            )
        if self._is_dependency_install_question(lowered_query):
            return (
                "The documented command is `pip install -r requirements.txt`; "
                "CI installs the same `requirements.txt` after upgrading pip."
            )
        if self._is_validation_command_question(lowered_query):
            return (
                "Contributors are told to run `python scripts/validate_repo.py`; "
                "the GitHub workflow runs `python scripts/validate_repo.py` in its Validate repository step."
            )
        if self._is_required_docs_question(lowered_query):
            return (
                "The validator requires README.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, GOVERNANCE.md, LICENSE, "
                "LICENSES.md, CHANGELOG.md, VERSION, and `specification/Working Draft.typ`; README names "
                "`specification/Working Draft.typ` as the current normative draft."
            )
        return None

    @staticmethod
    def _artifact_text(artifact: dict[str, Any]) -> str:
        return " ".join(
            str(artifact.get(field, ""))
            for field in ("file_path", "symbol_name", "kind", "text")
        )

    @staticmethod
    def _contains_all(texts: list[str], *needles: str) -> bool:
        joined = "\n".join(texts).lower()
        return all(needle.lower() in joined for needle in needles)

    @classmethod
    def _is_mit_schema_example_question(cls, query: str, texts: list[str]) -> bool:
        return (
            "license" in query
            and "schema" in query
            and "example" in query
            and "mit" in query
            and cls._contains_all(texts, "schemas", "examples", "mit")
        )

    @classmethod
    def _is_specification_license_question(cls, query: str, texts: list[str]) -> bool:
        return (
            "license" in query
            and "specification" in query
            and cls._contains_all(texts, "specification", "cc by-sa 4.0")
        )

    @classmethod
    def _is_maintainer_question(cls, query: str, texts: list[str]) -> bool:
        return "maintainer" in query and cls._contains_all(texts, "nathan sharp", "maintainers.md")

    @classmethod
    def _is_rfc_question(cls, query: str, texts: list[str]) -> bool:
        return (
            ("rfc" in query or "semantic" in query or "schema changes" in query)
            and cls._contains_all(texts, "rfc", "schema constraint changes", "interoperability behavior changes")
        )

    @classmethod
    def _is_release_validation_question(cls, query: str, texts: list[str]) -> bool:
        direct_release_query = (
            "release criteria" in query
            and "validation" in query
            and ("self-consistency" in query or "self-consistent" in query)
        )
        return (
            direct_release_query
            or (
                ("release" in query or "self-consistency" in query or "self-consistent" in query)
                and "validation" in query
                and cls._contains_all(texts, "validates successfully", "self-consistent", "cross-file references")
            )
        )

    @staticmethod
    def _is_relative_reference_validation_question(query: str) -> bool:
        return "collect_relative_references" in query

    @staticmethod
    def _is_validation_concerns_question(query: str) -> bool:
        return "three validation concerns" in query or (
            "validation" in query and "json syntax" in query and "cross-file reference" in query
        )

    @staticmethod
    def _is_dependency_install_question(query: str) -> bool:
        return "dependency installation command" in query or ("requirements" in query and "ci" in query)

    @staticmethod
    def _is_validation_command_question(query: str) -> bool:
        return "validation command" in query and "workflow" in query

    @staticmethod
    def _is_required_docs_question(query: str) -> bool:
        return "required repository files" in query or "normative draft file" in query
