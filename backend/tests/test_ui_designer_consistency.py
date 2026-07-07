"""Pre-gate consistency checks for generated UI manifests."""

from app.workers.ui_designer import _manifest_consistency_findings


def _manifest(**over) -> dict:
    html = (
        "<!DOCTYPE html><html><body><button>save</button>"
        "<script>const state={score:0,lives:3};AF.load().then(function(){});"
        "AF.save({score:state.score,lives:state.lives});"
        "window.applyAgentCommand=function(){};</script></body></html>"
    )
    m = {
        "feature": "retro_invaders",
        "title": "レトロ侵略者",
        "theme": "default",
        "html": html,
        "commands": [{"name": "start", "description": "開始", "inputSchema": {"type": "object"}}],
        "worker_state_mode": "hybrid",
        "state_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "lives": {"type": "number"},
            },
        },
    }
    m.update(over)
    return m


def test_consistency_accepts_matching_af_save_keys():
    findings = _manifest_consistency_findings(_manifest(), "レトロなゲームを作って")
    assert findings == []


def test_consistency_flags_hybrid_without_af_persistence():
    html = (
        "<!DOCTYPE html><html><body><button>start</button>"
        "<script>window.applyAgentCommand=function(){};</script></body></html>"
    )
    findings = _manifest_consistency_findings(_manifest(html=html), "レトロなゲームを作って")
    joined = " ".join(findings)
    assert "AF.load" in joined and "AF.save" in joined


def test_consistency_flags_saved_keys_missing_from_schema():
    findings = _manifest_consistency_findings(
        _manifest(
            html=(
                "<!DOCTYPE html><html><body><script>AF.load().then(function(){});"
                "AF.save({score:1,lives:3,invaderStep:4,lastShotAt:0});"
                "window.applyAgentCommand=function(){};</script></body></html>"
            )
        ),
        "レトロなゲームを作って",
    )
    joined = " ".join(findings)
    assert "invaderStep" in joined
    assert "lastShotAt" in joined


def test_consistency_allows_commands_only_transient_app():
    html = (
        "<!DOCTYPE html><html><body><button>=</button>"
        "<script>window.applyAgentCommand=function(){};</script></body></html>"
    )
    findings = _manifest_consistency_findings(
        _manifest(worker_state_mode="commands", state_schema={}, html=html),
        "電卓を作って",
        plan={"persistence": False},
    )
    assert findings == []
