"""Plan-stage SVG mock sanitizer (pure)."""
from app.workers.ui_designer import _svg_only, design_mock


def test_extracts_svg_and_strips_fences():
    raw = "```svg\n<svg viewBox=\"0 0 420 740\"><rect width=\"10\" height=\"10\"/></svg>\n```"
    out = _svg_only(raw)
    assert out.startswith("<svg") and out.endswith("</svg>")


def test_rejects_scripts_and_external_refs():
    assert _svg_only('<svg><script>alert(1)</script></svg>') == ""
    assert _svg_only('<svg><image href="http://x/y.png"/></svg>') == ""
    assert _svg_only("no svg here") == ""


def test_design_mock_offline_returns_empty():
    assert design_mock("電卓", {"theme": "default"}) == ""
