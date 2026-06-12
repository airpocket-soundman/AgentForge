"""NL worker-chat on/off detection (pure)."""
from app.reception.service import worker_toggle_intent as wt


def test_off_variants():
    assert wt("タスクリスト画面にはワーカーチャット不要") is False
    assert wt("ワーカーチャットを消して") is False
    assert wt("AIワーカーは非表示にして") is False


def test_on_variants():
    assert wt("ワーカーチャットを表示して") is True
    assert wt("ワーカーを付けて") is True


def test_not_a_toggle():
    # mentions ワーカー but no on/off → not a toggle (it's a real instruction)
    assert wt("タスク詳細でワーカーが編集する方式にして") is None
    # no worker word at all
    assert wt("タスクを削除して") is None
    assert wt("色を変えて") is None
