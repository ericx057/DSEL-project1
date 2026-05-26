from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _service_section(compose_text: str, service_name: str) -> str:
    marker = f"  {service_name}:"
    start = compose_text.index(marker)
    lines = compose_text[start:].splitlines()
    section = []
    for index, line in enumerate(lines):
        if index > 0 and line.startswith("  ") and not line.startswith("    "):
            break
        section.append(line)
    return "\n".join(section)


def test_llamacpp_compose_service_is_internal_only():
    compose_text = (ROOT / "docker-compose.yml").read_text()
    llamacpp_section = _service_section(compose_text, "llamacpp")

    assert "\n    expose:" in llamacpp_section
    assert "\n    ports:" not in llamacpp_section


def test_llamacpp_entrypoint_validates_context_window():
    entrypoint = (ROOT / "scripts" / "llamacpp-entrypoint.sh").read_text()

    assert "CIS_LLAMA_CPP_CONTEXT_WINDOW must be a positive integer" in entrypoint
    assert "*[!0-9]*" in entrypoint
    assert "-le 0" in entrypoint
