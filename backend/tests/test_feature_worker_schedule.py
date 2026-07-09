"""Feature-worker behavior for the default schedule app."""

from app.generated_app import features
from app.tools.web_search import SearchResult


def test_schedule_worker_updates_single_event_memo_from_flexible_request(monkeypatch):
    saved = {}
    state = {
        "events": [
            {
                "id": "e1",
                "date": "2026-07-13",
                "time": "11:00",
                "title": "仙台出張",
                "memo": "",
            }
        ]
    }

    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅の牛たん店"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台名物ずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台駅近く"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "メモに、仙台駅から近い仙台名物の食事処を3つ探して記入して",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "メモを更新" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    memo = saved["state"]["events"][0]["memo"]
    assert "牛たん通り" in memo
    assert "伊達の牛たん本舗" in memo
    assert "ずんだ茶寮" in memo


def test_schedule_worker_treats_candidate_write_as_current_event_memo(monkeypatch):
    saved = {}
    state = {
        "events": [
            {
                "id": "e1",
                "date": "2026-07-13",
                "time": "11:00",
                "title": "仙台出張",
                "memo": "",
            }
        ]
    }

    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅徒歩圏の牛たん"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台駅構内のずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台名物料理"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "仙台駅から徒歩圏内で仙台の名物料理が食べられるレストランを探して3件候補を記入して",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "メモを更新" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    memo = saved["state"]["events"][0]["memo"]
    assert "牛たん通り" in memo
    assert "伊達の牛たん本舗" in memo
    assert "ずんだ茶寮" in memo


def test_schedule_worker_uses_whole_lookup_request_when_memo_phrase_is_at_end(monkeypatch):
    saved = {}
    state = {
        "events": [
            {"id": "e1", "date": "2026-07-13", "time": "11:00", "title": "仙台出張", "memo": ""}
        ]
    }

    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅徒歩圏の牛たん"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台駅構内のずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台名物料理"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "仙台駅周辺で、仙台名物を食べられるレストランを調べて候補を3件メモに記入して",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "メモを更新" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    memo = saved["state"]["events"][0]["memo"]
    assert "牛たん通り" in memo
    assert "伊達の牛たん本舗" in memo
    assert "ずんだ茶寮" in memo


def test_schedule_worker_splits_add_event_and_memo_lookup(monkeypatch):
    saved = {}
    state = {"events": []}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅徒歩圏の牛たん"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台駅構内のずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台名物料理"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "7月14日にも仙台出張の予定を入れて、メモに仙台駅周辺の仙台名物が食べられるレストランを調べて3件入れておいて",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "追加し、メモも更新" in reply
    assert [c["op"] for c in changed] == ["create", "update"]
    event = saved["state"]["events"][0]
    assert event["date"] == "2026-07-14"
    assert event["title"] == "仙台出張"
    assert "牛たん通り" in event["memo"]
    assert "伊達の牛たん本舗" in event["memo"]
    assert "ずんだ茶寮" in event["memo"]


def test_schedule_worker_asks_when_memo_target_is_ambiguous(monkeypatch):
    state = {
        "events": [
            {"id": "e1", "date": "2026-07-13", "title": "仙台出張", "memo": ""},
            {"id": "e2", "date": "2026-07-14", "title": "会議", "memo": ""},
        ]
    }
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "メモに持ち物を書いて",
    )

    assert result is not None
    reply, changed, command = result
    assert "どの予定" in reply
    assert changed == []
    assert command is None


def test_schedule_worker_uses_open_event_context_for_memo_update(monkeypatch):
    saved = {}
    state = {
        "events": [
            {"id": "e1", "date": "2026-07-13", "title": "東京出張", "memo": ""},
            {"id": "e2", "date": "2026-07-14", "title": "仙台出張", "memo": ""},
        ]
    }
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅徒歩圏の牛たん"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台駅構内のずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台名物料理"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "いま開いている予定のメモに仙台駅周辺の仙台名物が食べられるレストランを調べて3件入れておいて",
        context_id="event_e2",
        context_label="仙台出張 のメモ",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "仙台出張" in reply
    assert changed == [{"entity_id": "e2", "op": "update"}]
    events = saved["state"]["events"]
    assert events[0]["memo"] == ""
    assert "牛たん通り" in events[1]["memo"]
    assert "ずんだ茶寮" in events[1]["memo"]


def test_schedule_worker_searches_restaurant_request_instead_of_copying_it(monkeypatch):
    saved = {}
    state = {"events": [{"id": "e1", "date": "2026-07-14", "title": "出張", "memo": ""}]}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅徒歩圏の牛たん"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "仙台駅構内のずんだ"),
            SearchResult("伊達の牛たん本舗", "https://example.com/date", "仙台名物料理"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "仙台駅の近くで名物が食べられるレストランを調べて3件メモして",
        context_id="event_e1",
        context_label="出張 のメモ",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "出張" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    memo = saved["state"]["events"][0]["memo"]
    assert "調べて3件メモして" not in memo
    assert "牛たん通り" in memo
    assert "ずんだ茶寮" in memo


def test_schedule_worker_searches_ramen_request_instead_of_copying_it(monkeypatch):
    saved = {}
    state = {"events": [{"id": "e1", "date": "2026-07-09", "title": "出張", "memo": ""}]}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("仙台駅前ラーメン候補A", "https://example.com/ramen-a", "仙台駅から徒歩圏"),
            SearchResult("仙台駅前ラーメン候補B", "https://example.com/ramen-b", "口コミで人気"),
            SearchResult("仙台駅前ラーメン候補C", "https://example.com/ramen-c", "夜も利用しやすい"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "仙台駅の近くのラーメン屋を探して3件しておいて",
        context_id="event_e1",
        context_label="出張 のメモ",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "出張" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    memo = saved["state"]["events"][0]["memo"]
    assert "探して3件しておいて" not in memo
    assert "仙台駅前ラーメン候補A" in memo
    assert "仙台駅前ラーメン候補B" in memo


def test_llm_state_edit_with_unresolved_search_request_is_rejected():
    old_state = {"events": [{"id": "e1", "memo": ""}]}
    new_state = {
        "events": [
            {
                "id": "e1",
                "memo": "仙台駅の近くで名物が食べられるレストランを調べて3件して",
            }
        ]
    }

    assert features._state_contains_unresolved_instruction(
        "仙台駅の近くで名物が食べられるレストランを調べて3件メモして",
        old_state,
        new_state,
    )


def test_llm_state_edit_with_unresolved_ramen_search_request_is_rejected():
    old_state = {"events": [{"id": "e1", "memo": ""}]}
    new_state = {
        "events": [
            {
                "id": "e1",
                "memo": "仙台駅の近くのラーメン屋を探して3件しておいて",
            }
        ]
    }

    assert features._state_contains_unresolved_instruction(
        "仙台駅の近くのラーメン屋を探して3件しておいて",
        old_state,
        new_state,
    )


def test_schedule_worker_structures_short_memo_fragments(monkeypatch):
    saved = {}
    state = {"events": [{"id": "e1", "date": "2026-07-14", "title": "出張", "memo": ""}]}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "メモに持っていくものとしてノートを追記して",
        context_id="event_e1",
        context_label="出張 のメモ",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "出張" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    assert saved["state"]["events"][0]["memo"] == "持っていくもの: ノート"


def test_schedule_worker_structures_plan_content_fragments(monkeypatch):
    saved = {}
    state = {"events": [{"id": "e1", "date": "2026-07-14", "title": "出張", "memo": ""}]}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_schedule_state_update(
        "default",
        "schedule",
        "メモに昼ご飯の予定を入れて。内容は笹かまぼこ",
        context_id="event_e1",
        context_label="出張 のメモ",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "出張" in reply
    assert changed == [{"entity_id": "e1", "op": "update"}]
    assert saved["state"]["events"][0]["memo"] == "予定: 昼ご飯\n内容: 笹かまぼこ"


def test_memo_worker_writes_search_summary_into_single_note(monkeypatch):
    saved = {}
    state = {"notes": [{"id": "n1", "title": "仙台", "body": "", "updated": 1}]}
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)
    monkeypatch.setattr(
        features.web_search_tool,
        "web_search",
        lambda query, max_results=5: [
            SearchResult("牛たん通り", "https://example.com/gyutan", "仙台駅の牛たん定食"),
            SearchResult("ずんだ茶寮", "https://example.com/zunda", "ずんだ餅とシェイク"),
        ],
    )

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_memo_state_update(
        "default",
        "memo",
        "仙台駅近くの仙台名物の食事処を探して本文に記入して",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "本文を更新" in reply
    assert changed == [{"entity_id": "n1", "op": "update"}]
    body = saved["state"]["notes"][0]["body"]
    assert "Web検索で確認した候補" in body
    assert "牛たん通り" in body
    assert "ずんだ茶寮" in body


def test_memo_worker_asks_when_multiple_notes_are_ambiguous(monkeypatch):
    state = {
        "notes": [
            {"id": "n1", "title": "仙台", "body": "", "updated": 1},
            {"id": "n2", "title": "東京", "body": "", "updated": 1},
        ]
    }
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)

    result = features._default_memo_state_update("default", "memo", "本文に予定を書いて")

    assert result is not None
    reply, changed, command = result
    assert "どのメモ" in reply
    assert changed == []
    assert command is None
