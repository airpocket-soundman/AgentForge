"""Timeout 3-choice detectors (pure, no Firestore) — workers.html §3(b)."""
from app.reception import service


def test_wait_detected():
    assert service.is_wait("もう少し待つ")
    assert service.is_wait("②")
    assert service.is_wait("そのまま継続")
    assert not service.is_wait("やめて")


def test_retry_detected():
    assert service.is_retry("停止して再トライ")
    assert service.is_retry("リトライ")
    assert service.is_retry("③")
    assert service.is_retry("やり直して")
    assert not service.is_retry("もう少し待つ")


def test_cancel_still_distinct_from_wait_retry():
    assert service.is_cancel("キャンセル")
    assert not service.is_wait("キャンセル")
    assert not service.is_retry("キャンセル")


def test_force_stop_threshold_is_two():
    assert service._TIMEOUT_FORCE_STOP_N == 2


def test_keep_going_counts_as_wait():
    assert service.is_wait("もっと続けて")
    assert service.is_wait("続行")
