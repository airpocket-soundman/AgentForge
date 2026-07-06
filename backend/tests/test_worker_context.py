"""Context compaction (pure logic) tests — spec §9."""
from app.control_plane.worker_context import compact_message_history, plan_compaction, summary_message


def test_no_compaction_within_budget():
    fold, keep = plan_compaction([1, 2, 3], keep_recent=5)
    assert fold == [] and keep == [1, 2, 3]


def test_compaction_folds_old_keeps_recent():
    fold, keep = plan_compaction([1, 2, 3, 4, 5], keep_recent=2)
    assert fold == [1, 2, 3] and keep == [4, 5]


def test_keep_recent_zero_folds_everything():
    fold, keep = plan_compaction([1, 2, 3], keep_recent=0)
    assert fold == [1, 2, 3] and keep == []


def test_exact_boundary_is_noop():
    fold, keep = plan_compaction([1, 2], keep_recent=2)
    assert fold == [] and keep == [1, 2]


def test_compact_message_history_keeps_recent_and_summarizes_old():
    current = [{"role": "user", "text": f"old {i}", "created_at": f"2026-01-0{i}T00:00:00"} for i in range(4)]
    messages, summary, compacted = compact_message_history(
        current,
        [{"role": "assistant", "text": "new"}],
        keep_recent=2,
    )
    assert compacted is True
    assert [m["text"] for m in messages] == ["old 3", "new"]
    assert "old 0" in summary and "old 2" in summary


def test_compact_message_history_noop_within_budget():
    messages, summary, compacted = compact_message_history(
        [{"role": "user", "text": "a"}],
        [{"role": "assistant", "text": "b"}],
        summary="kept",
        keep_recent=5,
    )
    assert compacted is False
    assert [m["text"] for m in messages] == ["a", "b"]
    assert summary == "kept"


def test_summary_message_is_synthetic_system_message():
    msg = summary_message("要約")
    assert msg and msg["role"] == "system"
    assert "要約" in msg["text"]
    assert summary_message("") is None
