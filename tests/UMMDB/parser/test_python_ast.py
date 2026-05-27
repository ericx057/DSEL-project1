from pathlib import Path

from src.UMMDB.parser.python_ast import PythonAstParser


def test_python_ast_parser_extracts_module_interfaces_and_implementations(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_text(
        "\n".join(
            [
                "class Service(BaseService):",
                "    def run(self, payload):",
                "        return helper(payload)",
                "",
                "def helper(value):",
                "    return str(value)",
            ]
        ),
        encoding="utf-8",
    )

    chunks = PythonAstParser().parse(str(source), "python")

    module = next(chunk for chunk in chunks if chunk.kind == "module")
    service = next(chunk for chunk in chunks if chunk.metadata.get("qualified_name") == "Service")
    run = next(chunk for chunk in chunks if chunk.metadata.get("qualified_name") == "Service.run")
    helper_impl = next(
        chunk
        for chunk in chunks
        if chunk.metadata.get("qualified_name") == "helper"
        and chunk.kind == "function-implementation"
    )

    assert module.tier == 1
    assert service.inherits == ("BaseService",)
    assert run.calls == ("helper",)
    assert run.line_start == 2
    assert "return str(value)" in helper_impl.content
    assert all(chunk.fidelity == "L-1" for chunk in chunks)

