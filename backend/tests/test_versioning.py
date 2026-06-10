"""Pure-logic tests for 巻き戻し (version rollback). No Firestore needed."""
from app.control_plane.approvals import plan_rollback


def _v(seq, title):
    return {"seq": seq, "manifest": {"title": title, "feature": "counter"}, "action": "publish"}


def test_rollback_none_when_empty():
    restored, result = plan_rollback([])
    assert result == "none" and restored is None


def test_rollback_disables_when_single_version():
    # one version = the creation; undoing it removes the feature
    restored, result = plan_rollback([_v(1, "v1")])
    assert result == "disabled" and restored is None


def test_rollback_restores_previous():
    restored, result = plan_rollback([_v(1, "v1"), _v(2, "v2")])
    assert result == "restored"
    assert restored["title"] == "v1"


def test_rollback_is_linear_down_the_stack():
    versions = [_v(1, "v1"), _v(2, "v2"), _v(3, "v3")]
    restored, result = plan_rollback(versions)
    assert result == "restored" and restored["title"] == "v2"
    # after popping v3, rolling back again restores v1
    restored2, result2 = plan_rollback(versions[:-1])
    assert result2 == "restored" and restored2["title"] == "v1"
