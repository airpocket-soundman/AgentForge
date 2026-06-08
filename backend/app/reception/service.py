"""Reception business logic, separated from the HTTP layer so it can be unit
tested and later swapped to call Gemini Flash (Phase 2)."""
from app.firestore import get_db
from app.models.reception import ChatMessage

# Conversation documents live under: conversations/{conversation_id}
#   conversations/{id}.messages : ordered list of {role, text, created_at}
# The browser subscribes to this doc for live updates (no backend polling).
_COLLECTION = "conversations"

# Keywords that signal an "app building" request the Orchestrator will own (P2).
_BUILD_KEYWORDS = ("追加", "作って", "つくって", "ほしい", "欲しい", "add", "create", "build")
_FEATURE_KEYWORDS = {
    "task": ("タスク", "todo", "task"),
    "pdf_memo": ("pdf", "メモ", "memo", "要約"),
}
# Conversational control commands (the spec's demo: 「反映して」承認 / 「戻して」rollback).
_APPROVE_KEYWORDS = ("反映", "承認", "approve", "apply")
_ROLLBACK_KEYWORDS = ("戻し", "戻す", "ロールバック", "rollback", "取り消", "無効化")

_FEATURE_LABELS = {"task": "タスク管理", "pdf_memo": "PDFメモ", "unknown": "ご要望の機能"}


def feature_label(feature: str) -> str:
    return _FEATURE_LABELS.get(feature, feature)


def classify(text: str) -> str:
    """Coarse intent for Reception routing: approve / rollback / build_feature:* / chat."""
    if any(k in text for k in _APPROVE_KEYWORDS):
        return "approve"
    if any(k in text for k in _ROLLBACK_KEYWORDS):
        return "rollback"
    return detect_intent(text) or "chat"


def conversation_id_for(project_id: str) -> str:
    """One rolling conversation per project for the MVP."""
    return f"conv_{project_id}"


def append_message(conversation_id: str, message: ChatMessage) -> None:
    doc = get_db().collection(_COLLECTION).document(conversation_id)
    payload = message.model_dump(mode="json")
    # ArrayUnion keeps the single-doc model simple and atomic for the MVP volume.
    from google.cloud import firestore  # local import: keeps module import cheap

    doc.set(
        {"messages": firestore.ArrayUnion([payload]), "project_id": conversation_id},
        merge=True,
    )


def detect_intent(text: str) -> str | None:
    """Very small rule-based intent detector (placeholder for Gemini Flash)."""
    lowered = text.lower()
    if not any(k in lowered for k in _BUILD_KEYWORDS):
        return None
    for feature, kws in _FEATURE_KEYWORDS.items():
        if any(k in lowered for k in kws):
            return f"build_feature:{feature}"
    return "build_feature:unknown"


def compose_reply(text: str, intent: str | None) -> str:
    """Deterministic reply. Replaced by Gemini-routed responses in Phase 2."""
    if intent and intent.startswith("build_feature:"):
        feature = intent.split(":", 1)[1]
        label = {
            "task": "タスク管理",
            "pdf_memo": "PDFメモ",
            "unknown": "ご要望の",
        }.get(feature, "ご要望の")
        return (
            f"「{label}」機能の追加リクエストを受け付けました。"
            "これから設計エージェント（Orchestrator）が作業計画を作成し、"
            "進捗はこの画面にリアルタイムで表示されます。"
            "（※現在 Phase 1：Orchestrator 連携は Phase 2 で有効化されます）"
        )
    return (
        "メッセージを受け取りました。"
        "「タスク管理を追加して」のように、追加したい機能を伝えてください。"
    )
