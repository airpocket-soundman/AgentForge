"""Context compaction (pure logic) tests — spec §9."""
from app.control_plane.worker_context import plan_compaction


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
