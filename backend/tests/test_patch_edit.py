"""Diff/patch editing (pure) — fast path for edits & gate repairs."""
from app.workers.ui_designer import apply_patches, design_patch

HTML = "<!DOCTYPE html><html><body><h1>Counter</h1><button id='inc'>+1</button><script>var n=0;</script></body></html>"


def test_apply_single_patch():
    out = apply_patches(HTML, [{"search": ">+1<", "replace": ">+10<"}])
    assert out is not None and ">+10<" in out and ">+1<" not in out


def test_apply_sequential_patches():
    out = apply_patches(HTML, [
        {"search": "<h1>Counter</h1>", "replace": "<h1>カウンター</h1>"},
        {"search": "var n=0;", "replace": "var n=0,step=1;"},
    ])
    assert out and "カウンター" in out and "step=1" in out


def test_miss_returns_none():
    assert apply_patches(HTML, [{"search": "NOT-IN-DOC", "replace": "x"}]) is None


def test_ambiguous_search_returns_none():
    html = HTML + "<script>var n=0;</script>"  # 'var n=0;' now appears twice
    assert apply_patches(html, [{"search": "var n=0;", "replace": "var n=1;"}]) is None


def test_invalid_shapes_return_none():
    assert apply_patches(HTML, []) is None
    assert apply_patches(HTML, [{"search": "", "replace": "x"}]) is None
    assert apply_patches(HTML, [{"replace": "x"}]) is None
    assert apply_patches(HTML, [{"search": ">+1<", "replace": "y"}] * 11) is None  # cap 10


def test_design_patch_offline_falls_back():
    # No LLM (stub provider) → None, so callers use the full-rewrite path.
    cur = {"feature": "counter", "title": "カウンター", "theme": "default", "html": HTML, "commands": []}
    assert design_patch("ボタンを大きく", cur) is None
