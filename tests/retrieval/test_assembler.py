import pytest
from retrieval.assembler import PromptAssembler
from retrieval.context_summary import ResponseShaper, RetrievedContextSummarizer

def test_u_shape_order():
    assembler = PromptAssembler()
    chunks = [
        {"id": "1", "score": 0.9},
        {"id": "2", "score": 0.8},
        {"id": "3", "score": 0.7},
        {"id": "4", "score": 0.6},
        {"id": "5", "score": 0.5},
    ]
    ordered = assembler._u_shape_order(chunks)
    ids = [c["id"] for c in ordered]
    assert ids == ["1", "3", "5", "4", "2"]

def test_u_shape_order_even():
    assembler = PromptAssembler()
    chunks = [
        {"id": "1", "score": 0.9},
        {"id": "2", "score": 0.8},
        {"id": "3", "score": 0.7},
        {"id": "4", "score": 0.6},
    ]
    ordered = assembler._u_shape_order(chunks)
    ids = [c["id"] for c in ordered]
    assert ids == ["1", "3", "4", "2"]

def test_assemble_prompt():
    assembler = PromptAssembler("System rule.")
    chunks = [
        {
            "id": "1",
            "text": "def save_document():\n    write_objects()",
            "file_path": "src/app/a.py",
            "language": "python",
            "tier": 0,
            "symbol_name": "save_document",
            "kind": "function",
        },
        {
            "id": "2",
            "text": "class RepositoryIndexer:\n    pass",
            "file_path": "src/app/b.py",
            "language": "python",
            "tier": 1,
            "symbol_name": "RepositoryIndexer",
            "kind": "class",
        },
    ]
    prompt = assembler.assemble("How to do X?", chunks)
    
    assert "System rule." in prompt
    assert "Retrieved summaries:" in prompt
    assert "--- File:" not in prompt
    assert "src/app/a.py" not in prompt
    assert "def save_document()" not in prompt
    assert "class RepositoryIndexer:" not in prompt
    assert "save_document" in prompt
    assert "RepositoryIndexer" in prompt
    assert "Query: How to do X?" in prompt

def test_assemble_empty_chunks():
    assembler = PromptAssembler()
    prompt = assembler.assemble("Query?", [])
    assert "Context:" not in prompt
    assert "Query: Query?" in prompt


def test_summarizer_does_not_echo_path_like_symbols():
    summary = RetrievedContextSummarizer().summarize_chunks(
        [
            {
                "symbol_name": r"src\app\service.py",
                "kind": "chunk",
                "language": "python",
                "line_start": 1,
                "line_end": 8,
                "text": "class Service:\n    def handle(self):\n        return expensive_call()",
            }
        ]
    )

    assert r"src\app\service.py" not in summary
    assert "src/app/service.py" not in summary
    assert "Service" in summary
    assert "expensive_call" in summary


def test_summarizer_prioritizes_implementation_declarations_over_constants():
    summary = RetrievedContextSummarizer().summarize_chunks(
        [
            {
                "symbol_name": "RepositoryIndexer",
                "kind": "class-implementation",
                "language": "python",
                "line_start": 1,
                "line_end": 50,
                "text": "\n".join(
                    [
                        "class RepositoryIndexer:",
                        "    DEFAULT_EXCLUDES = ('.git', '.venv', '__pycache__', 'node_modules')",
                        "    def __init__(self, store):",
                        "        self.store = store",
                        "    def index_repository(self, repository, repo_path):",
                        "        for path in self._iter_files(repo_path):",
                        "            self._index_file(repository, path)",
                        "    def _iter_files(self, root):",
                        "        yield from root.rglob('*')",
                        "    def _index_file(self, repository, file_path):",
                        "        return self.store.upsert_artifacts([])",
                    ]
                ),
            }
        ]
    )

    assert "index_repository" in summary
    assert "_iter_files" in summary
    assert "_index_file" in summary
    if "DEFAULT_EXCLUDES" in summary:
        assert summary.index("index_repository") < summary.index("DEFAULT_EXCLUDES")


def test_response_shaper_summarizes_legacy_raw_file_blocks():
    raw = "\n".join(
        [
            r"--- File: src\app\service.py | Language: python | Tier: 1 ---",
            "class Service:",
            "    def handle(self):",
            "        value = expensive_call()",
            "        return value",
        ]
    )

    shaped = ResponseShaper().shape(raw)

    assert "Service is a Python class tied to handle and expensive_call." in shaped
    assert r"src\app\service.py" not in shaped
    assert "src/app/service.py" not in shaped
    assert "class Service:" not in shaped
    assert "def handle" not in shaped
    assert "value = expensive_call()" not in shaped
    assert "Service" in shaped
    assert "expensive_call" in shaped


def test_response_shaper_explains_when_cached_context_is_declaration_only():
    raw = "\n".join(
        [
            "--- File: src/ingestion/indexer.py | Language: python | Tier: 1 ---",
            "class RepositoryIndexer:",
            "    pass",
        ]
    )

    shaped = ResponseShaper().shape(raw)

    assert "RepositoryIndexer is a Python class." in shaped
    assert "only identifies the class" in shaped
    assert "does not show methods or behavior" in shaped
    assert "src/ingestion/indexer.py" not in shaped
    assert "class RepositoryIndexer:" not in shaped


def test_response_shaper_removes_windows_relative_paths_from_cached_text():
    shaped = ResponseShaper().shape(
        r"The answer is in src\gateway\main.py and tests\gateway\test_main.py. Service handles it."
    )

    assert r"src\gateway\main.py" not in shaped
    assert r"tests\gateway\test_main.py" not in shaped
    assert "Service handles it." in shaped


def test_response_shaper_removes_path_list_shells_not_just_paths():
    shaped = ResponseShaper().shape(
        "\n".join(
            [
                "Relevant files:",
                "- src/app/service.py",
                "- tests/test_service.py",
                "Service handles checkout validation and retries.",
            ]
        )
    )

    assert shaped == "Service handles checkout validation and retries."


def test_response_shaper_rejects_raw_code_residue_without_summary():
    shaped = ResponseShaper().shape(
        "\n".join(
            [
                r"Answer comes from src\gateway\main.py",
                "class Service:",
                "    def handle(self):",
                "        return value",
            ]
        )
    )

    assert shaped == "The cached response matched code artifacts but did not contain a usable behavioral summary."
