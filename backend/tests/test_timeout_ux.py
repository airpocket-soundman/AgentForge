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


def test_onegai_shimasu_is_plan_ok():
    assert service.is_plan_ok("お願いします")
    assert service.is_plan_ok("お願いします。")
    assert service.is_plan_ok("おねがいします")


def test_status_query_detected():
    assert service.is_status_query("いまの状況を調べて")
    assert service.is_status_query("進捗どう？")
    assert service.is_status_query("確認結果の報告をして")
    assert not service.is_status_query("状況を管理するアプリを作って")  # build, not a query
    # Strong phrases are detected even in a longer sentence (the bug we just hit).
    assert service.is_status_query("パイプライン状況APIを利用してください。利用できない場合は状況を報告してください")
    assert service.is_status_query("いま論文解説アプリの改修はどうなってるか教えて")
