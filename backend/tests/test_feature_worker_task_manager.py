"""Specialist Worker behavior for the default task manager app."""

from app import templates
from app.generated_app import features


def test_paint_canvas_size_fallback_parses_dimensions():
    manifest = templates.get_template("paint")

    result = features._default_app_command("paint", "画像サイズを900x600にして", manifest)

    assert result == (
        "画像サイズを900x600pxに変更します。",
        {"name": "set_canvas_size", "arguments": {"width": 900, "height": 600}},
    )


def test_task_add_request_is_structured_into_title_and_detail_html():
    text = (
        "Hackathonアイデアだしというを追加しておいて。"
        "案として、AgentForge、スーパーアプリに慣れるかもしれないAIエージェント内蔵アプリを書いておいて"
    )

    parsed = features._parse_task_add_request(text)

    assert parsed is not None
    assert parsed["title"] == "Hackathonアイデアだし"
    assert "案" in parsed["detail_html"]
    assert "AgentForge" in parsed["detail_html"]
    assert "追加しておいて" not in parsed["detail_html"]


def test_task_add_command_override_repairs_llm_title_copy():
    manifest = templates.get_template("task_manager")
    text = (
        "Hackathonアイデアだしというを追加しておいて。"
        "案として、AgentForge、スーパーアプリに慣れるかもしれないAIエージェント内蔵アプリを書いておいて"
    )
    bad_command = {
        "name": "add_task",
        "arguments": {
            "title": text,
        },
    }

    result = features._command_override("task_manager", bad_command, text, manifest)

    assert result is not None
    _reply, command = result
    assert command["name"] == "add_task"
    assert command["arguments"]["title"] == "Hackathonアイデアだし"
    assert "detail_html" in command["arguments"]
    assert "AgentForge" in command["arguments"]["detail_html"]
    assert text not in command["arguments"]["title"]


def test_task_default_command_splits_compound_add_request():
    manifest = templates.get_template("task_manager")
    text = (
        "Hackathonアイデアだしというを追加しておいて。"
        "案として、AgentForge、スーパーアプリに慣れるかもしれないAIエージェント内蔵アプリを書いておいて"
    )

    result = features._default_app_command("task_manager", text, manifest)

    assert result is not None
    _reply, command = result
    assert command["name"] == "add_task"
    assert command["arguments"]["title"] == "Hackathonアイデアだし"
    assert "AgentForge" in command["arguments"]["detail_html"]


def test_task_add_separates_title_and_detail_and_removes_instruction_words():
    text = (
        "Hackathonのアイデアだし、というタスクを追加して。"
        "アイデア案として、エージェントがアプリを作ってくれるスーパーアプリ、を記載しておいて"
    )

    parsed = features._parse_task_add_request(text)

    assert parsed is not None
    assert parsed["title"] == "Hackathonのアイデアだし"
    detail = parsed["detail_html"]
    assert detail.startswith("<h2>アイデア案</h2>")
    assert "エージェントがアプリを作ってくれるスーパーアプリ" in detail
    assert "記載しておいて" not in detail


def test_task_command_override_repairs_unstructured_llm_detail():
    manifest = templates.get_template("task_manager")
    text = (
        "Hackathonのアイデアだし、というタスクを追加して。"
        "アイデア案として、エージェントがアプリを作ってくれるスーパーアプリ、を記載しておいて"
    )
    bad_command = {
        "name": "add_task",
        "arguments": {
            "title": "Hackathonのアイデアだし",
            "detail_html": "<h2>詳細</h2><p>アイデア案として、エージェントがアプリを作ってくれるスーパーアプリ、を記載しておいて</p>",
        },
    }

    result = features._command_override("task_manager", bad_command, text, manifest)

    assert result is not None
    _reply, command = result
    detail = command["arguments"]["detail_html"]
    assert detail.startswith("<h2>アイデア案</h2>")
    assert "記載しておいて" not in detail


def test_task_add_general_case_separates_conditions_from_title():
    text = (
        "リリース準備をタスクに追加して。"
        "詳細には金曜までにテスト結果を確認し、問題があれば担当者へ連絡すると書いて"
    )

    parsed = features._parse_task_add_request(text)

    assert parsed is not None
    assert parsed["title"] == "リリース準備"
    assert "金曜までにテスト結果を確認" in parsed["detail_html"]
    assert "担当者へ連絡" in parsed["detail_html"]
    assert "追加して" not in parsed["title"]


def test_task_detail_context_updates_open_task_detail_instead_of_creating_task(monkeypatch):
    saved = {}
    state = {
        "selected_task_id": "t1",
        "tasks": [
            {
                "id": "t1",
                "title": "Hackathonアイデアだし",
                "done": False,
                "detail_html": "<h2>Hackathonアイデアだし</h2><p>このタスクの詳細はまだありません。</p>",
            }
        ],
    }
    monkeypatch.setattr(features, "_load_app_state", lambda project_id, feature: state)

    def save(_project_id, _feature, next_state):
        saved["state"] = next_state

    monkeypatch.setattr(features, "_save_app_state", save)

    result = features._default_task_manager_state_update(
        "default",
        "task_manager",
        "AgentForge AIエージェントが欲しいアプリを作ってくれる。UIをすきにカスタマイズできるスーパーアプリ という内容を追加して",
        context_id="task_t1",
        context_label="詳細: Hackathonアイデアだし",
    )

    assert result is not None
    reply, changed, command = result
    assert command is None
    assert "詳細を更新" in reply
    assert changed == [{"entity_id": "t1", "op": "update"}]
    tasks = saved["state"]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Hackathonアイデアだし"
    assert "<h2>内容</h2>" in tasks[0]["detail_html"]
    assert "AgentForge AIエージェント" in tasks[0]["detail_html"]
    assert "という内容を追加して" not in tasks[0]["detail_html"]
