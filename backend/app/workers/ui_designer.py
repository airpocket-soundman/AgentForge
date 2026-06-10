"""UI Designer worker — the REAL build-time worker.

Turns a feature request into a COMPLETE, self-contained HTML application by
calling the LLM through the gateway (claude-cli locally / Gemini in prod). The
worker is told to FAITHFULLY and FULLY implement whatever the user asked — a
paint tool, a calculator, a task manager, a game — as one runnable HTML
document. The Generated View Renderer runs it in a sandboxed iframe, so the
screen is genuinely produced by the agent: not hard-coded, and not constrained
to a fixed set of components.

Apps that need to remember data use the injected `AF.load()/AF.save()` bridge
(persisted server-side per feature); the sandbox blocks localStorage/network.
Falls back to a minimal placeholder page when no LLM is reachable so the
pipeline still completes.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re

from app import agents
from app.llm.gateway import ModelTier, get_llm
from app.models.generated import DesignPlan, ViewManifest

_ALLOWED_THEMES = {"default", "warm", "forest", "ocean"}

_PLAN_SCHEMA = '''ユーザーの要求から「設計案」だけをJSONで出力してください（コードはまだ書かない・JSONのみ・前後の説明やコードフェンス不要）:
{
  "feature": "<英小文字スラッグ。例: paint, calculator, task_manager>",
  "title": "<日本語の機能名>",
  "summary": "<2〜3文。どんなアプリで、何が中心の体験かを具体的に>",
  "features": ["<実装する主な機能を4〜8個、具体的な箇条書きで。例: ペンと消しゴムの切替 / 10色のパレット>"],
  "persistence": true,
  "theme": "default|warm|forest|ocean"
}

- persistence: データ保存が必要なら true（タスク/メモ/家計簿など）、不要なら false（お絵描き/電卓/時計/ゲームなど）。
- お絵描き・ゲーム・電卓などインタラクティブな要求は、その操作内容を features に具体的に書く（「実際に描ける」等）。
- スラッグは英小文字。テーマは内容に近いもの（曖昧なら default）。'''

_SCHEMA = '''ユーザーの要求を「忠実に・省略せず」実装した、単一の完結したHTMLアプリを作ってください。
出力はJSONのみ（前後の説明やコードフェンスは不要）:
{
  "feature": "<英小文字スラッグ。例: paint, calculator, task_manager>",
  "title": "<日本語の機能名>",
  "description": "<1〜2文。何ができるアプリかを説明>",
  "theme": "default|warm|forest|ocean",
  "html": "<!DOCTYPE html> から始まる完結した単一HTML文書",
  "commands": [{"name": "<英小文字スラッグ>", "description": "<日本語の説明>", "inputSchema": {"type": "object", "properties": {"<引数名>": {"type": "string|number|boolean", "description": "<説明>"}}}}]
}

commands の要件（重要・標準仕様 / MCP形式のツール契約）:
- これは「ミニアプリ」。その中身を担当する「専門ワーカー」が自然言語で内容を編集できるよう、操作を
  MCP形式のツールとして公開する（各ツール = name / description / inputSchema(JSON Schema)）。
- HTML内に必ず `window.applyAgentCommand = function(name, args){ ... }` を実装する。name に応じて内容を
  実際に変更し（描画/データ/テキスト等）、保存が要るなら AF.save も呼ぶ。未知の name は無視（安全）。
- 公開した操作を上記 commands に列挙（name は applyAgentCommand と一致。args は inputSchema に従う）。
- **アプリの「変更できる主要な内容・プロパティ」を網羅的にツール化する**（ユーザーが言いそうな操作を広めに）。
  例（お絵描き）: set_color{color} / set_brush_size{size} / set_background{color} / set_mode{pen|eraser} / clear / undo
  例（電卓）: input{keys} / clear    例（タスク）: add_item{title} / toggle{index} / remove{index} / clear_done
  例（テキスト/メモ）: set_text{text} / append_text{text} / clear
- 操作が無いミニアプリ（純粋表示のみ等）は空配列でよい。

html の要件（重要）:
- ユーザーが求めた機能を「実際に動く形で」すべて実装する。フォーム＋一覧で代替したり、機能を削ったりしない。
  例: 「お絵描きツール」→ canvas に実際に描ける（ペン/消しゴム/色/太さ/Undo/全消去など要求された機能）。
      「電卓」→ 実際に計算できる。「タスク管理」→ 追加・完了・削除ができ、保存される。「〇×ゲーム」→ 実際に遊べる。
- <style> と <script> を内包し、外部CDN・外部通信なしで単体で動く（外部リソースは読み込めない）。
- body は margin:0 でビューポートいっぱいに広げ、モダンで見やすいUIにする。ボタンは押しやすく。
- 入力はマウスとタッチの両対応（pointer イベント推奨）。
- **チャットUI・メッセージ入力欄・AIアシスタント欄を html 内に作らない。** 専門ワーカーとの対話は、
  画面下部に別パネル（アプリチャット）としてアプリの外側に用意される。アプリ表示エリアにチャットを
  重複させないこと（成果物はアプリの中身だけ。会話UIは含めない）。
- 状態を保存したい場合（タスク・メモ・設定・スコアなど）は、用意された永続化APIを使う:
    const state = await AF.load();   // 保存済みの状態(任意のJSON)。無ければ null。
    await AF.save(state);            // 状態(JSONにできる値)を保存する。
  ※ localStorage / cookie / fetch / 外部通信 / 別ウィンドウ は使えない（サンドボックス）。保存は必ず AF を使う。
  ※ お絵描き・電卓・時計など保存不要なものは AF を使わなくてよい。
- スラッグは英小文字。テーマは内容に近いもの（曖昧なら default）。'''


def _slug(goal: str) -> str:
    return "gen_" + hashlib.sha1(goal.encode("utf-8")).hexdigest()[:8]


# A real generated app is an HTML document, not an apology/explanation string the
# LLM sometimes returns in the `html` field. Require a structural tag + a closing
# tag so prose like "申し訳ありません… <略>" doesn't get published as the live app.
_HTML_TAG_RE = re.compile(
    r"<(?:html|body|div|canvas|svg|button|form|table|main|section|header|h[1-6]|ul|ol|input|p)\b",
    re.I,
)


def _is_valid_app_html(html: object) -> bool:
    if not isinstance(html, str):
        return False
    s = html.strip()
    return len(s) > 80 and "</" in s and bool(_HTML_TAG_RE.search(s))


def _fallback_html(goal: str) -> str:
    g = _html.escape(goal[:120])
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<style>body{margin:0;font-family:system-ui,sans-serif;display:grid;"
        "place-items:center;height:100vh;background:#0e1016;color:#e6e8ef;"
        "text-align:center;padding:24px}h2{margin:0 0 8px}p{color:#9aa1b3}</style>"
        "</head><body><div><h2>この機能は準備中です</h2>"
        f"<p>「{g}」を生成するワーカー(LLM)に到達できませんでした。</p>"
        "<p>少し待って、もう一度お試しください。</p></div></body></html>"
    )


def plan_feature(
    goal: str,
    feedback: str | None = None,
    previous: dict | None = None,
    images: list[dict] | None = None,
) -> DesignPlan:
    """Produce a lightweight design proposal (no code yet) for review.

    When `feedback`/`previous` are given, revise the previous proposal per the
    user's instruction instead of starting from scratch. `images` (attachments)
    are passed to the LLM for vision so the proposal can reflect a screenshot/photo.
    """
    llm = get_llm()
    if llm.enabled:
        try:
            parts = [
                agents.load("ui_designer"),
                agents.policy(),
                f"ユーザー要求: {goal}",
            ]
            if previous and feedback:
                parts.append("前回の設計案:\n" + json.dumps(previous, ensure_ascii=False))
                parts.append(
                    f"ユーザーからの修正指示: {feedback}\n"
                    "この指示を反映して設計案を作り直してください。"
                )
            parts.append(_PLAN_SCHEMA)
            raw = llm.generate("\n\n".join(parts), tier=ModelTier.FLASH, images=images).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]
            d = json.loads(raw)
            feature = re.sub(r"[^a-z0-9_]+", "", str(d.get("feature", "")).lower()) or _slug(goal)
            theme = d.get("theme", "default")
            theme = theme if theme in _ALLOWED_THEMES else "default"
            features = [str(x) for x in d.get("features", []) if str(x).strip()][:10]
            return DesignPlan(
                feature=feature,
                title=(str(d.get("title") or goal))[:60],
                summary=str(d.get("summary", ""))[:400],
                features=features,
                persistence=bool(d.get("persistence", False)),
                theme=theme,
            )
        except Exception:  # noqa: BLE001 — fall back to a minimal proposal
            pass
    return DesignPlan(
        feature=_slug(goal),
        title=goal[:60],
        summary=goal[:200],
        features=[],
        persistence=False,
        theme="default",
    )


def design(
    goal: str,
    plan: dict | None = None,
    current_html: str | None = None,
    images: list[dict] | None = None,
) -> ViewManifest:
    """Build a real, self-contained HTML app that implements `goal`.

    - `plan`: an approved DesignPlan dict — implement that reviewed proposal, and
      keep its slug/title/theme.
    - `current_html`: when EDITING an existing feature, the current app code. `goal`
      is then the change instruction; the worker rewrites the full document with
      only that change applied, preserving everything else.
    - `images`: attachments passed to the LLM for vision (e.g. edit from a screenshot).
    """
    llm = get_llm()
    if llm.enabled:
        try:
            if current_html:
                parts = [
                    agents.load("ui_designer"),
                    agents.policy(),
                    "既存のアプリを、ユーザーの指示どおりに修正してください。指示された箇所だけを的確に直し、"
                    "それ以外の機能・UI・状態保存(AF.load/AF.save)は壊さないこと。",
                    "既存アプリの全コード:\n" + current_html,
                    f"ユーザーの修正指示: {goal}",
                    "修正を反映した完全な単一HTML文書を作り直して、JSONのhtmlに入れてください。",
                    _SCHEMA,
                ]
            else:
                parts = [
                    agents.load("ui_designer"),
                    agents.policy(),
                    f"次の機能を作ってください。\nユーザー要求: {goal}",
                ]
                if plan:
                    parts.append(
                        "ユーザーが承認した設計案（これに忠実に実装すること）:\n"
                        + json.dumps(plan, ensure_ascii=False)
                    )
                parts.append(_SCHEMA)
            prompt = "\n\n".join(parts)
            raw = llm.generate(prompt, tier=ModelTier.PRO, images=images).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]  # drop a leading ```json fence
            data = json.loads(raw)
            html = data.get("html")
            if _is_valid_app_html(html):
                # When an approved plan exists, keep its slug/title/theme so the
                # generated feature matches exactly what the user signed off on.
                feature = re.sub(r"[^a-z0-9_]+", "", str((plan or {}).get("feature") or data.get("feature", "")).lower()) or _slug(goal)
                title = (str((plan or {}).get("title") or data.get("title") or goal))[:60]
                description = str(data.get("description") or (plan or {}).get("summary", ""))[:200]
                theme = (plan or {}).get("theme") or data.get("theme", "default")
                theme = theme if theme in _ALLOWED_THEMES else "default"
                commands = data.get("commands")
                commands = [c for c in commands if isinstance(c, dict) and c.get("name")] if isinstance(commands, list) else []
                return ViewManifest(
                    kind="app",
                    feature=feature,
                    title=title,
                    description=description,
                    theme=theme,
                    html=html,
                    commands=commands,
                    generated_by=llm.name,
                )
        except Exception:  # noqa: BLE001 — any LLM/parse failure -> placeholder page
            pass

    return ViewManifest(
        kind="app",
        feature=_slug(goal),
        title=goal[:60],
        description="ワーカー(LLM)に到達できず、生成できませんでした。",
        theme="default",
        html=_fallback_html(goal),
        generated_by="stub",
    )
