"""Unit tests for Orchestrator plan generation (pure, no Firestore).

The reception -> orchestrator -> Control Plane registration path is covered by the
docker-compose integration loop (it needs the Firestore emulator).
"""
from app.models.orchestrator import PlanRequest
from app.orchestrator import service


def test_infer_feature():
    assert service.infer_feature("タスク管理を追加して") == "task"
    assert service.infer_feature("PDFのメモと要約がほしい") == "pdf_memo"
    assert service.infer_feature("在庫管理を作って") == "unknown"


def test_stub_task_plan_shape():
    plan = service.generate_plan(PlanRequest(project_id="p", goal="タスク管理を追加して"))
    assert plan.feature == "task"
    assert plan.generated_by == "stub"  # no API key in CI
    assert len(plan.plan) == 5
    api_ids = {a.api_id for a in plan.planned_apis}
    assert api_ids == {"task_list_api", "task_create_api", "task_update_api"}
    assert plan.planned_views[0].view_id == "task_list_view"
    # The view must bind to APIs that the plan actually creates.
    assert set(plan.planned_views[0].required_apis) <= api_ids
    assert plan.approval_required_before_active is True


def test_stub_pdf_memo_plan():
    plan = service.generate_plan(PlanRequest(project_id="p", goal="PDFメモ機能がほしい"))
    assert plan.feature == "pdf_memo"
    assert any(a.api_id == "pdf_summarize_api" for a in plan.planned_apis)


def test_summary_mentions_pending():
    plan = service.generate_plan(PlanRequest(project_id="p", goal="タスク管理を追加して"))
    summary = service._summarize(plan)
    assert "pending" in summary
    assert "task_list_api" in summary


def test_classify_stub_treats_connection_investigation_as_chat():
    result = service._classify_stub(
        "Blueskyアプリで接続に失敗するので原因を確認してください",
        {"bluesky_viewer": "Bluesky縦書きビューア"},
        "bluesky_viewer",
    )
    assert result == {"action": "chat", "feature": None}
