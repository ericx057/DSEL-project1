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


def test_cpp_parser_extracts_generic_class_inheritance_and_methods(tmp_path: Path):
    source = tmp_path / "shape.hpp"
    source.write_text(
        "\n".join(
            [
                "namespace geom {",
                "class Shape : public Drawable, private Cached {",
                "public:",
                "    void draw(Renderer& renderer) const;",
                "    int vertexCount() const {",
                "        return countVertices();",
                "    }",
                "};",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = CppSignatureParser().parse(str(source), "cpp")

    class_chunk = next(chunk for chunk in chunks if chunk.kind == "class")
    method_chunks = {chunk.metadata["qualified_name"]: chunk for chunk in chunks if chunk.kind == "method"}
    impl_chunks = {
        chunk.metadata["qualified_name"]: chunk
        for chunk in chunks
        if chunk.kind == "method-implementation"
    }

    assert class_chunk.symbol_name == "Shape"
    assert class_chunk.metadata["qualified_name"] == "geom::Shape"
    assert class_chunk.inherits == ("Drawable", "Cached")
    assert "geom::Shape::draw" in method_chunks
    assert "geom::Shape::vertexCount" in method_chunks
    assert impl_chunks["geom::Shape::vertexCount"].calls == ("countVertices",)


def test_cpp_parser_preserves_overloaded_signatures(tmp_path: Path):
    source = tmp_path / "shape.cpp"
    source.write_text(
        "\n".join(
            [
                "void Shape::move(int x) {",
                "    translate(x);",
                "}",
                "",
                "void Shape::move(double x) {",
                "    translateFloat(x);",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = CppSignatureParser().parse(str(source), "cpp")

    methods = [chunk for chunk in chunks if chunk.kind == "method"]
    hashes = {chunk.metadata["signature_hash"] for chunk in methods}
    signatures = {chunk.metadata["signature"] for chunk in methods}

    assert len(methods) == 2
    assert len(hashes) == 2
    assert signatures == {"Shape::move(int x)", "Shape::move(double x)"}


def test_cpp_parser_qualifies_namespace_free_functions(tmp_path: Path):
    source = tmp_path / "geometry.cpp"
    source.write_text(
        "\n".join(
            [
                "namespace geom {",
                "double length(const Point& point) {",
                "    return norm(point);",
                "}",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = CppSignatureParser().parse(str(source), "cpp")

    function_chunk = next(chunk for chunk in chunks if chunk.symbol_name == "length" and chunk.tier == 1)
    assert function_chunk.kind == "function"
    assert function_chunk.metadata["qualified_name"] == "geom::length"
    assert function_chunk.metadata["signature"] == "geom::length(const Point& point)"
    assert function_chunk.calls == ("norm",)
