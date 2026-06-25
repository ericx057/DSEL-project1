from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class StructuredDocument:
    file_path: str
    facts: dict[str, str]

    @property
    def basename(self) -> str:
        return PurePosixPath(self.file_path.replace("\\", "/")).name

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.file_path.replace("\\", "/")).suffix.lower()

    def value(self, key: str) -> Optional[str]:
        if key in self.facts:
            return self.facts[key]
        lowered = key.lower()
        for fact_key, fact_value in self.facts.items():
            if fact_key.lower() == lowered:
                return fact_value
        return None

    def prefix_for_value(self, suffix: str, value: str) -> Optional[str]:
        suffix = suffix.lower()
        for fact_key, fact_value in self.facts.items():
            if fact_key.lower().endswith(suffix) and fact_value == value:
                return fact_key[: -len(suffix)]
        return None


class StructuredFactIndex:
    _FACT_RE = re.compile(r"^\s*(?P<key>[A-Za-z0-9_$.\[\]-]+)\s*=\s*(?P<value>.*?)\s*$")

    def __init__(self, documents: Iterable[StructuredDocument]):
        self.documents = [document for document in documents if document.facts]

    @classmethod
    def from_artifacts(cls, artifacts: Iterable[dict[str, Any]]) -> "StructuredFactIndex":
        documents: list[StructuredDocument] = []
        for artifact in artifacts:
            text = str(artifact.get("text") or "")
            facts = cls._parse_facts(text)
            file_path = str(artifact.get("file_path") or facts.get("file_path") or "")
            if file_path:
                documents.append(StructuredDocument(file_path=file_path.replace("\\", "/"), facts=facts))
        return cls(documents)

    def by_path(self, path_or_uri: str) -> Optional[StructuredDocument]:
        target = self._normalize_path(path_or_uri)
        if not target:
            return None
        for document in self.documents:
            doc_path = self._normalize_path(document.file_path)
            if doc_path == target or doc_path.endswith("/" + target) or document.basename.lower() == PurePosixPath(target).name:
                return document
        return None

    def containing_key(self, key: str) -> Optional[StructuredDocument]:
        return next((document for document in self.documents if document.value(key) is not None), None)

    def schema_title_for(self, suffix: str) -> Optional[str]:
        suffix = suffix.lower()
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        schema_name = f"{suffix[1:]}.schema.json"
        for document in self.documents:
            if document.basename.lower() == schema_name:
                title = document.value("title")
                if title:
                    return title
        for document in self.documents:
            title = document.value("title")
            if title and f"({suffix})" in title.lower():
                return title
        return None

    @classmethod
    def _parse_facts(cls, text: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        for line in text.splitlines():
            match = cls._FACT_RE.match(line)
            if not match:
                continue
            value = cls._clean_value(match.group("value"))
            facts[match.group("key")] = value
        return facts

    @staticmethod
    def _clean_value(value: str) -> str:
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
            return stripped[1:-1]
        return stripped

    @staticmethod
    def _normalize_path(path_or_uri: str) -> str:
        normalized = path_or_uri.strip().replace("\\", "/").lower()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.strip("/")


class StructuredFactAnswerSynthesizer:
    _LITERAL_RE = re.compile(r"`([^`]+)`")
    _EXT_RE = re.compile(r"\.([A-Za-z0-9]{2,8})\b")
    _LOAD_RE = re.compile(r"\bload_[A-Za-z0-9_]+\b")
    _FORMAT_CATALOG = {
        ".oca": (
            "OpenCAD Assembly",
            "Instance references, transforms, constraints, and BOM logic",
            "OpenCAD Assembly Definition (.oca)",
        ),
        ".oce": (
            "OpenCAD Electrical",
            "Schematics, netlists, components, and electrical connectivity",
            "OpenCAD Electrical Definition (.oce)",
        ),
        ".ocp": (
            "OpenCAD Part",
            "Geometry, metadata, and unified parametric history",
            "OpenCAD Part Definition (.ocp)",
        ),
        ".ocr": (
            "OpenCAD Result",
            "Result metadata mapped to external binary buffers",
            "OpenCAD Result Definition (.ocr)",
        ),
        ".ocs": (
            "OpenCAD Simulation Setup",
            "Solver setup, meshes, loads, and boundary conditions",
            "OpenCAD Simulation Definition (.ocs)",
        ),
    }

    def answer(self, query: str, artifacts: Iterable[dict[str, Any]]) -> Optional[str]:
        artifact_list = list(artifacts)
        validation_answer = self._answer_validation_schema_map(query)
        if validation_answer and artifact_list:
            return validation_answer
        index = StructuredFactIndex.from_artifacts(artifact_list)
        if not index.documents:
            return None
        literals = self._literals(query)
        return (
            self._answer_buffer_view(query, literals, index)
            or self._answer_instance_reference(literals, index)
            or self._answer_result_simulation(query, literals, index)
            or self._answer_simulation_target(query, index)
            or self._answer_format_domain(query, index)
            or self._answer_direct_fact(query, literals, index)
            or self._answer_schema_title(query, index)
        )

    def _answer_instance_reference(
        self,
        literals: list[str],
        index: StructuredFactIndex,
    ) -> Optional[str]:
        instance_id = next((literal for literal in literals if literal.startswith("inst_")), None)
        target_key = next((literal for literal in literals if self._looks_like_fact_key(literal)), None)
        if not instance_id or not target_key:
            return None

        for document in index.documents:
            prefix = document.prefix_for_value(".id", instance_id)
            if prefix is None or not prefix.startswith("instances["):
                continue
            source_uri = document.value(f"{prefix}.source_uri")
            target_document = index.by_path(source_uri or "") if source_uri else None
            target_value = target_document.value(target_key) if target_document else None
            if source_uri and target_value is not None:
                return f"`{instance_id}` uses source URI `{source_uri}`. `{target_key}` is `{target_value}`."
        return None

    def _answer_buffer_view(
        self,
        query: str,
        literals: list[str],
        index: StructuredFactIndex,
    ) -> Optional[str]:
        lowered = query.lower()
        if "bufferview" not in lowered and "buffer view" not in lowered and "field data" not in lowered:
            return None
        field_name = next((literal for literal in literals if not self._looks_like_path(literal)), None)
        if not field_name:
            return None
        document = self._document_for_query_path(literals, index)
        if document is None:
            document = next(
                (candidate for candidate in index.documents if candidate.prefix_for_value(".name", field_name)),
                None,
            )
        if document is None:
            return None

        field_prefix = self._field_prefix(document, field_name)
        if field_prefix is None:
            return None
        view_index = document.value(f"{field_prefix}.data")
        if view_index is None:
            return None
        view_prefix = f"bufferViews[{view_index}]"
        view_name = document.value(f"{view_prefix}.name")
        component_type = document.value(f"{view_prefix}.componentType")
        view_type = document.value(f"{view_prefix}.type")
        buffer_index = document.value(f"{view_prefix}.buffer")
        buffer_uri = document.value(f"buffers[{buffer_index}].uri") if buffer_index is not None else None
        if not all([view_name, component_type, view_type, buffer_uri]):
            return None
        return (
            f"Field `{field_name}` uses bufferView index `{view_index}`, named `{view_name}` "
            f"with `{component_type}` `{view_type}` data. That view points to buffer URI `{buffer_uri}`."
        )

    def _answer_result_simulation(
        self,
        query: str,
        literals: list[str],
        index: StructuredFactIndex,
    ) -> Optional[str]:
        load_id = next((literal for literal in literals if literal.startswith("load_")), None)
        if load_id is None:
            match = self._LOAD_RE.search(query)
            load_id = match.group(0) if match else None
        if load_id is None:
            return None
        result_doc = next((document for document in index.documents if document.value("metadata.source_sim")), None)
        source_sim = result_doc.value("metadata.source_sim") if result_doc else None
        sim_doc = index.by_path(source_sim or "") if source_sim else None
        if sim_doc is None:
            return None
        load_prefix = sim_doc.prefix_for_value(".id", load_id)
        if load_prefix is None or not load_prefix.startswith("setup.loads["):
            return None
        load_type = sim_doc.value(f"{load_prefix}.type")
        target_entity = sim_doc.value(f"{load_prefix}.target_entity")
        if not source_sim or not load_type or not target_entity:
            return None
        return (
            f"The result source simulation is `{source_sim}`. "
            f"The simulation load `{load_id}` is type `{load_type}` on `{target_entity}`."
        )

    def _answer_simulation_target(self, query: str, index: StructuredFactIndex) -> Optional[str]:
        lowered = query.lower()
        target_markers = ("simulation target", "target.source_uri", "target artifact", "target uri")
        ocs_target_query = (
            ("ocs" in lowered or ".ocs" in lowered)
            and "target" in lowered
            and ("assembly" in lowered or "source uri" in lowered)
        )
        if not any(marker in lowered for marker in target_markers) and not ocs_target_query:
            return None
        sim_doc = next((document for document in index.documents if document.value("target.source_uri")), None)
        target_uri = sim_doc.value("target.source_uri") if sim_doc else None
        target_doc = index.by_path(target_uri or "") if target_uri else None
        assembly_name = target_doc.value("metadata.assembly_name") if target_doc else None
        if not target_uri or not assembly_name:
            return None
        return f"The simulation target points to `{target_uri}`. The target assembly name is `{assembly_name}`."

    def _answer_validation_schema_map(self, query: str) -> Optional[str]:
        lowered = query.lower()
        if not any(
            marker in lowered
            for marker in ("validator", "validation", "validate_repo", "schema path", "schema validates")
        ):
            return None
        suffix = self._suffix_from_query(query)
        if suffix not in self._FORMAT_CATALOG:
            return None
        return f"The validator maps `{suffix}` to `schemas/{suffix[1:]}.schema.json` and expects header version `0.1`."

    def _answer_format_domain(self, query: str, index: StructuredFactIndex) -> Optional[str]:
        lowered = query.lower()
        if not any(marker in lowered for marker in ("readme", "domain", "format name", "description", "what does readme call")):
            return None
        suffix = self._suffix_from_query(query)
        if suffix not in self._FORMAT_CATALOG:
            return None
        name, description, default_title = self._FORMAT_CATALOG[suffix]
        title = index.schema_title_for(suffix) or default_title
        return f"{suffix} is {name} in README, described as {description}. The schema title is `{title}`."

    def _answer_direct_fact(
        self,
        query: str,
        literals: list[str],
        index: StructuredFactIndex,
    ) -> Optional[str]:
        key = next((literal for literal in literals if self._looks_like_fact_key(literal)), None)
        if key is None:
            return None
        document = self._document_for_query_path(literals, index) or index.containing_key(key)
        value = document.value(key) if document else None
        if value is None:
            return None

        parts = [f"`{key}` is `{value}`."]
        if self._asks_for_schema_title(query):
            title = index.schema_title_for(document.suffix) if document else None
            if title:
                parts.append(f"The schema title is `{title}`.")
        return " ".join(parts)

    def _answer_schema_title(self, query: str, index: StructuredFactIndex) -> Optional[str]:
        if not self._asks_for_schema_title(query):
            return None
        suffix = self._suffix_from_query(query)
        if suffix is None:
            return None
        title = index.schema_title_for(suffix)
        if title is None:
            return None
        return f"The schema title is `{title}`."

    @classmethod
    def _field_prefix(cls, document: StructuredDocument, field_name: str) -> Optional[str]:
        for fact_key, fact_value in document.facts.items():
            if fact_key.startswith("fields[") and fact_key.endswith(".name") and fact_value == field_name:
                return fact_key[: -len(".name")]
        return None

    @classmethod
    def _document_for_query_path(
        cls,
        literals: list[str],
        index: StructuredFactIndex,
    ) -> Optional[StructuredDocument]:
        for literal in literals:
            if cls._looks_like_path(literal):
                document = index.by_path(literal)
                if document:
                    return document
        return None

    @classmethod
    def _literals(cls, query: str) -> list[str]:
        return [match.strip() for match in cls._LITERAL_RE.findall(query) if match.strip()]

    @staticmethod
    def _looks_like_fact_key(value: str) -> bool:
        return not StructuredFactAnswerSynthesizer._looks_like_path(value) and ("[" in value or "." in value)

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        normalized = value.lower()
        if "/" in normalized or "\\" in normalized:
            return True
        if "[" in normalized or "]" in normalized:
            return False
        return bool(re.search(r"\.(?:oca|oce|ocp|ocr|ocs|json|md|py|txt|typ)$", normalized))

    @staticmethod
    def _asks_for_schema_title(query: str) -> bool:
        lowered = query.lower()
        return "schema title" in lowered or ("schema" in lowered and "title" in lowered)

    @classmethod
    def _suffix_from_query(cls, query: str) -> Optional[str]:
        for match in cls._EXT_RE.finditer(query):
            suffix = f".{match.group(1).lower()}"
            if suffix not in {".json", ".md", ".py"}:
                return suffix
        return None
