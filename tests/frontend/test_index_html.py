from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_sends_response_mode_without_rewriting_query():
    html = (ROOT / "src" / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "response_mode: state.depth" in html
    assert "query: `${state.depth}: ${query}`" not in html


def test_frontend_blocks_submit_without_bearer_token():
    html = (ROOT / "src" / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "Add a bearer token before submitting a query." in html
    assert "if (!authHeaders().Authorization)" in html
