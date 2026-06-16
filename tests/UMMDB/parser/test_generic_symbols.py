from pathlib import Path

from src.UMMDB.parser.cascade import CascadingParser
from src.UMMDB.parser.generic_symbols import GenericSymbolParser


def test_generic_symbol_parser_extracts_typescript_class_method_and_function(tmp_path: Path):
    source = tmp_path / "checkout.ts"
    source.write_text(
        "\n".join(
            [
                "export class CheckoutService {",
                "  authorize(amount: number): boolean {",
                "    return validate(amount);",
                "  }",
                "}",
                "",
                "export function buildReceipt(id: string): string {",
                "  return formatReceipt(id);",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = GenericSymbolParser().parse(str(source), "typescript")

    symbols = {(chunk.kind, chunk.metadata["qualified_name"]) for chunk in chunks if chunk.tier == 1}
    authorize = next(chunk for chunk in chunks if chunk.metadata.get("qualified_name") == "CheckoutService.authorize")
    build_receipt = next(chunk for chunk in chunks if chunk.metadata.get("qualified_name") == "buildReceipt")

    assert ("class", "CheckoutService") in symbols
    assert ("method", "CheckoutService.authorize") in symbols
    assert ("function", "buildReceipt") in symbols
    assert authorize.calls == ("validate",)
    assert build_receipt.calls == ("formatReceipt",)


def test_cascade_prefers_generic_symbols_for_go_over_module_chunks(tmp_path: Path):
    source = tmp_path / "checkout.go"
    source.write_text(
        "\n".join(
            [
                "package checkout",
                "",
                "type Service struct {}",
                "",
                "func (s *Service) Authorize(amount int) bool {",
                "    return validate(amount)",
                "}",
                "",
                "func BuildReceipt(id string) string {",
                "    return formatReceipt(id)",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = CascadingParser().parse(str(source), "go")

    symbols = {(chunk.kind, chunk.metadata.get("qualified_name")) for chunk in chunks if chunk.tier == 1}
    assert ("class", "Service") in symbols
    assert ("method", "Service.Authorize") in symbols
    assert ("function", "BuildReceipt") in symbols
    assert not all(chunk.kind == "module" for chunk in chunks)


def test_generic_symbol_parser_extracts_rust_impl_methods(tmp_path: Path):
    source = tmp_path / "checkout.rs"
    source.write_text(
        "\n".join(
            [
                "pub struct Service {}",
                "",
                "impl Service {",
                "    pub fn authorize(&self, amount: i32) -> bool {",
                "        validate(amount)",
                "    }",
                "}",
                "",
                "pub fn build_receipt(id: &str) -> String {",
                "    format_receipt(id)",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    chunks = GenericSymbolParser().parse(str(source), "rust")

    symbols = {(chunk.kind, chunk.metadata["qualified_name"]) for chunk in chunks if chunk.tier == 1}
    assert ("class", "Service") in symbols
    assert ("method", "Service.authorize") in symbols
    assert ("function", "build_receipt") in symbols
