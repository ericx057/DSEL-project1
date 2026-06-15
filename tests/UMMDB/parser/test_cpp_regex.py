from pathlib import Path

from src.UMMDB.parser.cpp import CppSignatureParser


def test_cpp_signature_parser_extracts_qualified_methods(tmp_path: Path):
    source = tmp_path / "TopoShapePyImp.cpp"
    source.write_text(
        "\n".join(
            [
                "Py::List TopoShapePy::getVertexes() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_VERTEX);",
                "}",
                "",
                "Py::List TopoShapePy::getEdges() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_EDGE);",
                "}",
                "",
                "Py::List TopoShapePy::getWires() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_WIRE);",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = CppSignatureParser().parse(str(source), "cpp")

    interface_chunks = {chunk.symbol_name: chunk for chunk in chunks if chunk.tier == 1}
    implementation_chunks = {chunk.symbol_name: chunk for chunk in chunks if chunk.tier == 3}

    assert {"getVertexes", "getEdges", "getWires"} <= set(interface_chunks)
    assert interface_chunks["getEdges"].metadata["qualified_name"] == "TopoShapePy::getEdges"
    assert interface_chunks["getEdges"].kind == "method"
    assert implementation_chunks["getWires"].kind == "method-implementation"
    assert "TopAbs_WIRE" in implementation_chunks["getWires"].content
