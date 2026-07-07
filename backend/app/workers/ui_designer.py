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
_PERSISTENCE_KEYWORDS = (
    "保存", "復元", "途中", "リロード", "画面遷移", "履歴", "メモ", "タスク", "todo",
    "フォーム", "設定", "ゲーム", "テトリス", "tetris", "盤面", "スコア", "レベル",
    "ライン", "手番", "クイズ", "進捗", "家計簿", "日記", "予定", "スケジュール",
)

_PLAN_SCHEMA = '''ユーザーの要求から「設計案」だけをJSONで出力してください（コードはまだ書かない・JSONのみ・前後の説明やコードフェンス不要）:
{
  "feature": "<英小文字スラッグ。例: paint, calculator, task_manager>",
  "title": "<日本語の機能名>",
  "summary": "<2〜3文。どんなアプリで、何が中心の体験かを具体的に>",
  "features": ["<実装する主な機能を4〜8個、具体的な箇条書きで。例: ペンと消しゴムの切替 / 10色のパレット>"],
  "persistence": true,
  "theme": "default|warm|forest|ocean",
  "acceptance": ["<動作で検証できる受け入れ条件を3〜6個。例: 『=を押すと計算結果が表示される』『リロードしてもタスクが残る』>"]
}

- persistence: 画面遷移・リロード後に途中状態を復元すべきアプリは true。タスク/メモ/家計簿だけでなく、
  ゲーム（テトリス等の盤面・スコア・進行状態）、クイズ、タイマー、設定、入力途中のフォームも true。
  不要なのは、電卓のように途中状態を保持しなくても機能価値が落ちない一時操作、時計のような現在値表示などに限る。
- お絵描き・ゲーム・電卓などインタラクティブな要求は、その操作内容を features に具体的に書く（「実際に描ける」等）。
- acceptance: 完成品で Tester が1つずつ検証する。曖昧な表現（「使いやすい」等）でなく、動作として判定できる文にする。
- 外部API連携アプリでは、画像サムネイルや外部リンクを直接表示できると安易に約束しない。
  生成HTMLは外部URLを `src` / `href` で読めないため、外部画像は「画像あり」「alt」「件数」などのテキスト表示を基本にする。
  画像実体を表示する設計にするのは、承認済みの backend/Blob 取得経路がある場合だけ。
- スラッグは英小文字。テーマは内容に近いもの（曖昧なら default）。'''

_SCHEMA = '''ユーザーの要求を「忠実に・省略せず」実装した、単一の完結したHTMLアプリを作ってください。
出力はJSONのみ（前後の説明やコードフェンスは不要）:
{
  "feature": "<英小文字スラッグ。例: paint, calculator, task_manager>",
  "title": "<日本語の機能名>",
  "description": "<1〜2文。何ができるアプリかを説明>",
  "theme": "default|warm|forest|ocean",
  "html": "<!DOCTYPE html> から始まる完結した単一HTML文書",
  "commands": [{"name": "<英小文字スラッグ>", "description": "<日本語の説明>", "inputSchema": {"type": "object", "properties": {"<引数名>": {"type": "string|number|boolean", "description": "<説明>"}}}}],
  "worker_state_mode": "commands|state|hybrid",
  "state_schema": {"type": "object", "properties": {"<AF.saveするstateのキー>": {"type": "array|object|string|number|boolean", "description": "<意味>"}}},
  "worker_instructions": "<専門ワーカー向け。ユーザーが言いそうな操作意図、各APIの使い分け、足りない情報の聞き返し方を具体的に書く>",
  "worker_examples": [{"user": "<想定ユーザー指示>", "command": {"name": "<commandsのname または空>", "arguments": {}}, "reply": "<短い返答または聞き返し>"}],
  "worker_eval_cases": [{"input": "<自然言語のテスト指示>", "expected_behavior": "<add/update/delete/ask_clarification/forward_to_main等>", "expected_state_diff": "<期待されるstate差分または空>", "expected_message_contains": "<聞き返しや返答に含むべき短文または空>"}],
  "clarification_policy": "<情報不足・異常値・対象不明のとき、実行せず何を聞き返すか>",
  "dangerous_action_policy": "<一括削除・初期化・復元不能操作などをどう確認するか>"
}

worker_state_mode / state_schema の要件（重要・未知アプリ対応）:
- データ中心アプリ（予定、タスク、メモ、在庫、顧客管理、家計簿、日記、フォーム、記録、一覧、台帳、CRM、学習カード等）は、
  専門ワーカーが狭いAPIに縛られず state を直接更新できるよう `worker_state_mode` を `hybrid` または `state` にする。
- `state_schema` には、AF.save で保存する state の主要構造を JSON Schema 風に具体化する。
  例: {"type":"object","properties":{"events":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"date":{"type":"string"},"time":{"type":"string"},"title":{"type":"string"},"memo":{"type":"string"}}}}}}
- HTML は `AF.load()` でこの state を読み、UI 操作時も同じ構造を `AF.save(state)` で保存する。state_schema と実際の保存形式を一致させる。
- `state` は、専門ワーカーが persisted state を直接編集するモード。`commands` は空配列でもよい。
- `hybrid` は、データ更新は state 直接編集、ペン色変更・電卓入力・ゲーム操作など UI 操作は commands を併用するモード。
- `commands` は、状態データではなく「今表示中のUIへ送った方が自然な操作」に使う。データ中心アプリでは全CRUDをcommandsだけに閉じ込めず、state_schemaを必ず用意する。
- お絵描き・ゲーム・電卓など、状態全体をLLMが直接書き換えるより UI 操作APIの方が安全なアプリは commands を併用してよい。
  ただしゲーム・お絵描きなど状態を持つものは `AF.load()` / `AF.save()` または Blob API で必ず復元できるようにし、
  `worker_state_mode` は `hybrid` を基本にする。`commands` のみにして保存を省略してはいけない。

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
- APIは「ユーザーが自然に言いそうな依頼」から逆算して設計する。
  作成/追加、更新/変更/移動、削除/消去/一括削除、完了/未完了、並べ替え、絞り込み、メモ追記、
  設定変更、初期化/クリア、Undo など、そのアプリ領域で起こりやすい操作を具体的に想定する。
  例: スケジュールなら「22日の予定を全部消して」に対応する delete_event{date, all:true} のように、
  タイトル指定だけでは表せない自然な依頼もAPI化する。
- worker_instructions には、専門ワーカーが迷わずAPIを選べるように以下を書く:
  1. このアプリで扱う対象物と専門ワーカーの役割。
  2. state_schema のどの配列/オブジェクトをどう変えるか。commands を使う場合は各 command の意味、必須引数、任意引数、自然言語の言い換え。
  3. 削除語・更新語・追加語など、誤分類しやすい表現の扱い。
  4. 情報不足・対象不明・異常値のときに実行せず聞き返す文例。
  5. 直近の確認にユーザーが「はい」「それで」と返した時に、履歴から補って実行する方針。
  6. ユーザー送信直後の「作業に入っています」表示はシェルのアプリチャット標準で出るため、生成HTML内に受付中表示を作らず、最終返答では完了内容・聞き返し・取次内容を短く具体的に返す方針。
- worker_examples には、そのアプリで実際に来そうな指示を8〜12件入れる。
  正常系だけでなく、削除、一括操作、曖昧な対象、異常値、確認質問への返答も含める。
- worker_eval_cases には、その専門ワーカーが誤りやすい自然言語テストを5〜8件入れる。
  追加/更新/削除/一括削除/曖昧な対象/異常値/確認質問/担当外の構造変更を含める。
  例（スケジュール）: 「22日の予定を全部消して」→ delete、「15:65にテスト」→ ask_clarification。
- clarification_policy と dangerous_action_policy には、聞き返しと危険操作確認の方針を具体的に書く。
- 操作が無いミニアプリ（純粋表示のみ等）は空配列でよい。

html の要件（重要）:
- ユーザーが求めた機能を「実際に動く形で」すべて実装する。フォーム＋一覧で代替したり、機能を削ったりしない。
  例: 「お絵描きツール」→ canvas に実際に描ける（ペン/消しゴム/色/太さ/Undo/全消去など要求された機能）。
      「電卓」→ 実際に計算できる。「タスク管理」→ 追加・完了・削除ができ、保存される。「〇×ゲーム」→ 実際に遊べ、盤面・手番・結果が保存される。
- <style> と <script> を内包し、外部CDN・外部通信なしで単体で動く（外部リソースは読み込めない）。
- body は margin:0 でビューポートいっぱいに広げ、モダンで見やすいUIにする。ボタンは押しやすく。
- **PC とスマホの両方で使えるレスポンシブ**にする：`<meta name="viewport" content="width=device-width,initial-scale=1">` を必ず入れ、
  固定幅にせず flex/grid・% で画面幅に追従させる。必要なら `@media`（目安 600px）でスマホ向けに
  レイアウトを最適化（縦並び・大きめのタップ領域）。スマホ縦持ちでも操作できること。
- 入力はマウスとタッチの両対応（pointer イベント推奨）。
- **チャットUI・メッセージ入力欄・AIアシスタント欄を html 内に作らない。** 専門ワーカーとの対話は、
  画面下部に別パネル（アプリチャット）としてアプリの外側に用意される。アプリ表示エリアにチャットを
  重複させないこと（成果物はアプリの中身だけ。会話UIは含めない）。
- 複数画面・複数タブ・詳細画面など、1つのアプリ内に複数の作業文脈がある場合は、画面遷移時に必ず
  `AF.setChatContext("screen-or-object-id", "表示名")` を呼ぶ。専門ワーカーの会話履歴は
  アプリ(feature)ごと、さらにこの context ごとに分割保存される。例:
    一覧画面 `AF.setChatContext("list", "一覧")`
    設定画面 `AF.setChatContext("settings", "設定")`
    レコード詳細 `AF.setChatContext("detail_"+id, title)`
  画面が1つだけのアプリは呼ばなくてよく、既定の `default` コンテキストを使う。
- 下部のアプリチャット欄は既定で表示される。**ユーザーが「この画面ではチャット欄を出さない」等、
  画面単位の表示/非表示を指定した場合**は、その画面への遷移時に `AF.setChatVisible(false)`、
  戻る時に `AF.setChatVisible(true)` を呼ぶ（ワーカー自体は常にアプリに1つ付いたまま。
  指定が無ければ呼ばなくてよい）。
- ミニアプリの基本仕様: **画面遷移・リロード・別メニューへ移動して戻った後も、途中状態を復元できること。**
  状態を持つアプリ（タスク・メモ・ゲームの盤面/スコア/落下中ピース/一時停止状態・クイズの進捗・設定・入力途中フォームなど）は、
  用意されたサーバ側永続化APIを必ず使う:
    const state = await AF.load();   // 保存済みの状態(任意のJSON)。無ければ null。
    await AF.save(state);            // 状態(JSONにできる値)を保存する。
  ※ localStorage / cookie / fetch / 外部通信 / 別ウィンドウ は使えない（サンドボックス）。保存は必ず AF を使う。
  ※ 外部サービスを使う必要がある場合も fetch は使わない。アプリ内に接続設定UIを作り、
    ユーザー入力を `AF.defineConnector({...})` で feature-scoped connector として登録する。
    呼び出しは登録済み action に限り `await AF.api("connector_id.action_id", params)` で行う。
    token/API key/password は `AF.save()` state に保存せず、登録後は入力欄を空にして再表示しない。
    action には query_template / body_template を指定できる。テンプレート値はリテラル、
    "$params.name"（AF.api 呼び出し時の引数）、"$secret.password" / "$secret.token" /
    "$secret.username"（connector auth に保存済みの secret）を使える。
    例:
      await AF.defineConnector({connector_id:"my_api",label:"My API",base_url:"https://api.example.com",auth:{type:"bearer",token},actions:{list_items:{method:"GET",path:"/items",side_effect:"read",query_template:{limit:"$params.limit"}}}});
      const res = await AF.api("my_api.list_items", {limit: 20});
    接続設定だけを扱う画面は、それ自体を worker_state_mode='hybrid' にしない。connector 定義は
    AF.defineConnector 側で永続化されるため、state_schema に base_url、token、認証ヘッダ、
    connector 定義を入れない。公開済み接続の表示は AF.listConnectors() から復元する。
    session 発行や refresh で保存済み secret を body に入れる必要がある場合は、HTML state に secret を戻さず
    body_template:{password:"$secret.password"} のように backend 側で差し込む。
    AF.api() の戻り値は外部 API のレスポンス本体をトップレベルにも展開し、同じ値を data にも保持する。
    例: session API が {accessJwt:"..."} を返す場合は res.accessJwt と res.data.accessJwt の両方で読める。
    Bluesky/AT Protocol の認証が必要な API は、App Password を Bearer token として使わない。
    App Password は connector secret として保存し、POST /xrpc/com.atproto.server.createSession の action は
    body_template:{identifier:"$params.identifier",password:"$secret.password"} で呼び、
    返った accessJwt を auth:{type:"bearer", token: accessJwt} の connector に入れて
    GET /xrpc/app.bsky.feed.getTimeline 等を呼ぶ。App Password と accessJwt は AF.save() state に保存しない。
    接続状態は credential_saved / session_ready / last_test_ok / last_error を分け、
    接続確認に失敗しても connector 保存済みなら未保存扱いに戻さない。
    外部API由来の投稿本文・表示名・URL・alt などを DOM に入れるときは、`innerHTML` へ直接連結しない。
    `textContent` / `createTextNode` を使うか、`escapeHtml()` で `& < > " '` をエスケープしてから入れる。
    `safeText()` のように String 化するだけでは HTML エスケープにならない。
    外部画像URLやリンクURLを `<img src="${...}">` / `<a href="${...}">` / `element.src = url` / `element.href = url`
    として直接使わない。リンクを開く必要がある場合は、ユーザーのクリック操作で `AF.openExternal(url)` を呼ぶ。
    画像は原則として「画像あり」「alt」「URL文字列」などのテキストで表示する。
    画像実体を扱う場合は承認済み backend/Blob 経路で取得し、`AF.loadBlob()` が null のときは
    「画像データがこの端末にありません」「再取得が必要です」のような欠落表示を必ず出す。
  ※ 保存する状態は JSON 化できる小さなデータにする（例: 盤面配列、現在ピース、次ピース、スコア、設定、入力値）。
  ※ 電卓・時計など、本当に途中状態を保持しなくてもよい一時操作だけは AF を使わなくてよい。
- **大きいファイル（PDF・画像・音声など）は AF.save の状態に入れない**（状態は約1MB上限。巨大 base64 を
  入れると保存に失敗しリロードで消える）。ファイルは専用 Blob API を使う:
    await AF.saveBlob(name, dataUrlOrBase64);  // 端末内(ブラウザ)に保存（name は識別子）
    const data = await AF.loadBlob(name);       // 取り出し（無ければ null）
    const names = await AF.listBlobs();         // 名前一覧 / await AF.deleteBlob(name)
  ・状態(AF.save)には**メタ情報だけ**（ファイル名/サイズ/抽出テキスト/blob の name 等）。原本は saveBlob。
    表示は loadBlob の結果から blob URL / データURL を作って行う。
  ・**Blob は端末ローカル**（別デバイスやデータ消去後は無い）。`loadBlob` が null のときは
    「原本はこの端末にのみ保存（メタは同期）」のように**欠落前提で優しく表示**する。
  ・文書を解説/要約する類は、原本 base64 に依存せず**抽出テキストを状態に保存**して使う。
- スラッグは英小文字。テーマは内容に近いもの（曖昧なら default）。'''


def _slug(goal: str) -> str:
    return "gen_" + hashlib.sha1(goal.encode("utf-8")).hexdigest()[:8]


def _requires_persistence(goal: str, plan: dict | None = None, requirements: list[str] | None = None) -> bool:
    if plan and plan.get("persistence") is True:
        return True
    hay = "\n".join([
        goal or "",
        json.dumps(plan or {}, ensure_ascii=False),
        "\n".join(requirements or []),
    ]).lower()
    return any(k.lower() in hay for k in _PERSISTENCE_KEYWORDS)


# A real generated app is an HTML document, not an apology/explanation string the
# LLM sometimes returns in the `html` field. Require a structural tag + a closing
# tag so prose like "申し訳ありません… <略>" doesn't get published as the live app.
_HTML_TAG_RE = re.compile(
    r"<(?:html|body|div|canvas|svg|button|form|table|main|section|header|h[1-6]|ul|ol|input|p)\b",
    re.I,
)
_AF_SAVE_OBJECT_RE = re.compile(r"\bAF\.save\s*\(\s*\{(?P<body>.*?)\}\s*\)", re.S)
_JS_OBJECT_KEY_RE = re.compile(r"(?:^|[,{\s])([A-Za-z_$][\w$]*)\s*(?::|,|$)")


def _is_valid_app_html(html: object) -> bool:
    if not isinstance(html, str):
        return False
    s = html.strip()
    return len(s) > 80 and "</" in s and bool(_HTML_TAG_RE.search(s))


def _state_schema_property_keys(state_schema: object) -> set[str]:
    if not isinstance(state_schema, dict):
        return set()
    props = state_schema.get("properties")
    if not isinstance(props, dict):
        return set()
    return {str(k) for k in props.keys() if str(k).strip()}


def _af_save_object_keys(html: str) -> set[str]:
    """Best-effort top-level key extraction from simple AF.save({ ... }) calls.

    This intentionally handles the common generated forms only. If the app saves a
    state variable (`AF.save(state)`), the schema-to-code relation cannot be proven
    statically here and the deploy gates remain the source of truth.
    """
    keys: set[str] = set()
    for m in _AF_SAVE_OBJECT_RE.finditer(html or ""):
        body = m.group("body") or ""
        # Avoid parsing nested object bodies as top-level state. The regex is a
        # guard rail for common shorthand/object-literal saves, not a JS parser.
        if "{" in body or "}" in body:
            continue
        for km in _JS_OBJECT_KEY_RE.finditer(body):
            key = km.group(1)
            if key and key not in {"true", "false", "null", "undefined"}:
                keys.add(key)
    return keys


def _manifest_consistency_findings(data: dict, goal: str = "", plan: dict | None = None,
                                   requirements: list[str] | None = None) -> list[str]:
    """Pre-gate mechanical checks for failure patterns LLMs commonly repeat.

    Reviewer/Tester still make the final decision. This preflight exists so the
    generator gets a specific repair prompt before we spend a full gate attempt on
    an obviously inconsistent manifest.
    """
    findings: list[str] = []
    html = str(data.get("html") or "")
    state_mode = str(data.get("worker_state_mode") or "commands").strip().lower()
    state_schema = data.get("state_schema") if isinstance(data.get("state_schema"), dict) else {}
    needs_persistence = _requires_persistence(goal, plan, requirements)

    if state_mode in {"state", "hybrid"}:
        if "AF.load" not in html or "AF.save" not in html:
            findings.append(
                "worker_state_mode が state/hybrid なのに HTML に AF.load()/AF.save() が無い。"
                "保存 state を初期化時に AF.load() で復元し、状態変更後に AF.save(state) で保存すること。"
            )
        if not _state_schema_property_keys(state_schema):
            findings.append(
                "worker_state_mode が state/hybrid なのに state_schema.properties が空。"
                "AF.save する永続 state のトップレベルキーを具体的に定義すること。"
            )

    if needs_persistence and ("AF.load" not in html or "AF.save" not in html):
        findings.append(
            "この要求は状態保存が必須だが HTML に AF.load()/AF.save() が無い。"
            "リロード・画面遷移後に途中状態を復元できる実装にすること。"
        )

    schema_keys = _state_schema_property_keys(state_schema)
    save_keys = _af_save_object_keys(html)
    missing = sorted(save_keys - schema_keys)
    if state_mode in {"state", "hybrid"} and missing:
        findings.append(
            "AF.save({ ... }) のトップレベルキーが state_schema.properties に無い: "
            + ", ".join(missing)
            + "。HTML の保存 state 構造と state_schema を一致させること。"
        )
    return findings


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


def _repair_manifest_json(llm, data: dict, goal: str, plan: dict | None,
                          findings: list[str]) -> dict | None:
    """Ask the model once to repair a generated manifest that failed preflight."""
    try:
        slim = dict(data)
        if isinstance(slim.get("html"), str) and len(slim["html"]) > 70000:
            slim["html"] = slim["html"][:70000] + "\n<!-- truncated for repair prompt -->"
        parts = [
            agents.load("ui_designer"),
            agents.policy(),
            "次の生成物 JSON は公開前の機械チェックに失敗しました。"
            "ユーザー要求と承認済み設計を変えず、指摘だけを修正した完全な JSON を返してください。",
            "修正必須チェック:\n" + "\n".join(f"- {f}" for f in findings),
            "重要: worker_state_mode が state/hybrid の場合、HTML は実際に AF.load() で復元し、"
            "状態変更後に AF.save(state) または AF.save({...}) を呼ぶこと。"
            "state_schema.properties は AF.save する永続 state のトップレベルキーと一致させること。",
            f"ユーザー要求: {goal}",
        ]
        if plan:
            parts.append("ユーザーが承認した設計案:\n" + json.dumps(plan, ensure_ascii=False))
        parts += [
            "修正対象 JSON:\n" + json.dumps(slim, ensure_ascii=False),
            _SCHEMA,
        ]
        raw = llm.generate("\n\n".join(parts), tier=ModelTier.PRO).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        repaired = json.loads(raw)
        if isinstance(repaired, dict) and _is_valid_app_html(repaired.get("html")):
            return repaired
    except Exception:  # noqa: BLE001 — repair is best-effort; gates still run.
        return None
    return None


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
            from app import templates

            parts = [
                agents.load("ui_designer"),
                agents.policy(),
                "完成済みの『デフォルトテンプレート』が次のとおり存在する。要求がこれらに当てはまる/近い場合は、"
                "ゼロから考えず、その実績ある構成を土台に設計する（基本機能は踏襲し、要求の差分だけ上乗せ）:\n"
                + templates.catalogue_text(),
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
            acceptance = [str(x).strip() for x in d.get("acceptance", []) if str(x).strip()][:8]
            return DesignPlan(
                feature=feature,
                title=(str(d.get("title") or goal))[:60],
                summary=str(d.get("summary", ""))[:400],
                features=features,
                persistence=bool(d.get("persistence", False)),
                theme=theme,
                acceptance=acceptance,
            )
        except Exception:  # noqa: BLE001 — fall back to a minimal proposal
            pass
    return DesignPlan(
        feature=_slug(goal),
        title=goal[:60],
        summary=goal[:200],
        features=[
            "要求された中心操作を実際に動かす",
            "PC とスマホの両方で操作できる",
            "必要な状態を保存し、リロード後も復元する",
        ] if _requires_persistence(goal) else [],
        persistence=_requires_persistence(goal),
        theme="default",
        acceptance=[
            "主要操作が画面上で実行できる",
            "リロード後も途中状態が復元される",
        ] if _requires_persistence(goal) else [],
    )


def design(
    goal: str,
    plan: dict | None = None,
    current_html: str | None = None,
    images: list[dict] | None = None,
    requirements: list[str] | None = None,
) -> ViewManifest:
    """Build a real, self-contained HTML app that implements `goal`.

    - `plan`: an approved DesignPlan dict — implement that reviewed proposal, and
      keep its slug/title/theme.
    - `current_html`: when EDITING an existing feature, the current app code. `goal`
      is then the change instruction; the worker rewrites the full document with
      only that change applied, preserving everything else.
    - `images`: attachments passed to the LLM for vision (e.g. edit from a screenshot).
    - `requirements`: the feature's confirmed-requirements ledger (must keep holding).
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
                if requirements:
                    parts.insert(3, "この機能で過去に確定した要求（修正後も必ず維持すること）:\n"
                                 + "\n".join(f"・{r}" for r in requirements[:30]))
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
                if _requires_persistence(goal, plan, requirements):
                    parts.append(
                        "この要求は状態保存が必須です。HTML内で必ず AF.load() と AF.save(state) を使い、"
                        "ゲームならスコア・ゲームオーバー・設定・進行状態などリロード後に復元すべき状態を保存してください。"
                        "manifest は worker_state_mode='hybrid' を基本にし、state_schema に保存する state 構造を具体的に書いてください。"
                    )
                parts.append(_SCHEMA)
            prompt = "\n\n".join(parts)
            raw = llm.generate(prompt, tier=ModelTier.PRO, images=images).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]  # drop a leading ```json fence
            data = json.loads(raw)
            if isinstance(data, dict):
                findings = _manifest_consistency_findings(data, goal, plan, requirements)
                if findings:
                    repaired = _repair_manifest_json(llm, data, goal, plan, findings)
                    if repaired is not None and not _manifest_consistency_findings(repaired, goal, plan, requirements):
                        data = repaired
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
                examples = data.get("worker_examples")
                examples = [e for e in examples if isinstance(e, dict)] if isinstance(examples, list) else []
                eval_cases = data.get("worker_eval_cases")
                eval_cases = [e for e in eval_cases if isinstance(e, dict)] if isinstance(eval_cases, list) else []
                state_mode = str(data.get("worker_state_mode") or "commands")
                state_mode = state_mode if state_mode in {"commands", "state", "hybrid"} else "commands"
                state_schema = data.get("state_schema") if isinstance(data.get("state_schema"), dict) else {}
                return ViewManifest(
                    kind="app",
                    feature=feature,
                    title=title,
                    description=description,
                    theme=theme,
                    html=html,
                    commands=commands,
                    worker_state_mode=state_mode,
                    state_schema=state_schema,
                    worker_instructions=str(data.get("worker_instructions") or "")[:4000],
                    worker_examples=examples[:16],
                    worker_eval_cases=eval_cases[:12],
                    clarification_policy=str(data.get("clarification_policy") or "")[:2000],
                    dangerous_action_policy=str(data.get("dangerous_action_policy") or "")[:2000],
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


# --- Design-stage screen mock (SVG) -------------------------------------------
# A preview AFTER code is built is expensive to act on (a fix = regeneration).
# So at the PLAN stage we draw a cheap FLASH SVG mock of the screen: the user can
# say "ここをこう直して" BEFORE any PRO code is written; revisions just redraw the
# mock in seconds. Non-blocking: any failure returns "" (plan proceeds without it).

_SVG_BANNED = ("<script", "foreignobject", "javascript:", "xlink:href=\"http", "href=\"http", "href='http")


def _svg_only(raw: str) -> str:
    """Extract a safe, standalone <svg>…</svg> from model output; '' if unusable."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s.split("\n", 1)[-1] if "\n" in s else s
    lo = s.find("<svg")
    hi = s.rfind("</svg>")
    if lo < 0 or hi < 0 or hi <= lo:
        return ""
    s = s[lo:hi + len("</svg>")]
    low = s.lower()
    if any(b in low for b in _SVG_BANNED):
        return ""
    if len(s) > 60000:
        return ""
    return s


def design_mock(goal: str, plan: dict) -> str:
    """Draw a screen mock (SVG) of the proposed app for plan-stage review."""
    llm = get_llm()
    if not llm.enabled:
        return ""
    try:
        prompt = (
            "あなたはUIデザイナー。次の設計案のミニアプリ画面を、1枚のSVGモックとして描いてください。\n"
            "- 出力は SVG のみ（説明・コードフェンス禁止）。<svg …> で始まり </svg> で終わること。\n"
            '- viewBox="0 0 420 740"（スマホ縦）。ヘッダ・主要コントロール・ボタン・一覧など、実装イメージが伝わる構成。\n'
            f"- テーマ「{plan.get('theme', 'default')}」の落ち着いた配色。ラベルは日本語で実際の文言を書く。\n"
            "- <script>/foreignObject/外部参照（http）は禁止。図形とテキストだけで描く。\n\n"
            f"設計案: {json.dumps({k: v for k, v in plan.items() if k != 'mock_svg'}, ensure_ascii=False)}\n"
            f"ユーザー要求: {goal}"
        )
        return _svg_only(llm.generate(prompt, tier=ModelTier.FLASH))
    except Exception:  # noqa: BLE001 — mock is best-effort, never block the plan
        return ""


# --- Diff/patch editing (fast path for edits & gate-revision repairs) ---------
# Rewriting the whole document for every tweak is slow (minutes of PRO output),
# token-expensive, and risks regressing unrelated parts. For edits/repairs we
# first ask for SEARCH/REPLACE patches against the current HTML and apply them
# locally; any miss (ambiguous/absent search, invalid result) returns None and
# the caller falls back to a full rewrite. Gates verify the result either way.

_PATCH_SCHEMA = '''既存アプリへの修正を「差分パッチ」で出力してください。JSON のみ（前後の説明・コードフェンス不要）:
{
  "full_rewrite": false,
  "patches": [{"search": "<現コードから一字一句コピーした一意な部分文字列>", "replace": "<置換後>"}],
  "description": "<変更後の説明が変わる場合のみ。1〜2文>",
  "commands": [<操作ツールが増減・変更される場合のみ、全量を再宣言>],
  "worker_state_mode": "commands|state|hybrid（操作方式やstate構造が変わる場合のみ）",
  "state_schema": {<AF.save state の構造が変わる場合のみ、全量を再宣言>},
  "worker_instructions": "<操作ツールや想定指示が変わる場合のみ、全量を再宣言>",
  "worker_examples": [<操作ツールや想定指示が変わる場合のみ、全量を再宣言>],
  "worker_eval_cases": [<操作ツールや想定指示が変わる場合のみ、全量を再宣言>],
  "clarification_policy": "<聞き返し方針が変わる場合のみ>",
  "dangerous_action_policy": "<危険操作確認方針が変わる場合のみ>"
}

パッチの規則（厳守）:
- search は現コードに**そのまま一度だけ**現れる文字列にする（コピーすること。改変・省略・"..."禁止）。
- 1パッチは小さく（数行〜十数行）。パッチは最大10個。
- 変更が大規模で差分にできない場合は {"full_rewrite": true} だけを返す。
- AF.load/AF.save・applyAgentCommand・既存機能を壊さないこと。'''


def apply_patches(html: str, patches: list) -> str | None:
    """Apply SEARCH/REPLACE patches. Returns None on ANY miss (caller falls back):
    every search must be a non-empty string occurring exactly once."""
    if not isinstance(patches, list) or not patches or len(patches) > 10:
        return None
    out = html
    for p in patches:
        if not isinstance(p, dict):
            return None
        search, replace = p.get("search"), p.get("replace", "")
        if not isinstance(search, str) or not search or not isinstance(replace, str):
            return None
        if out.count(search) != 1:
            return None
        out = out.replace(search, replace, 1)
    return out


def design_patch(
    goal: str,
    current: dict,
    feedback: str | None = None,
    requirements: list[str] | None = None,
) -> ViewManifest | None:
    """Patch-based edit of an existing app manifest. Returns the updated manifest,
    or None when patching isn't possible (LLM off, model chose full_rewrite, a
    patch missed, or the result isn't a valid app) — caller falls back to design()."""
    llm = get_llm()
    html = current.get("html") or ""
    if not llm.enabled or not html:
        return None
    try:
        parts = [
            agents.load("ui_designer"),
            agents.policy(),
            "既存アプリの全コード:\n" + html,
            f"ユーザーの修正指示: {goal}",
        ]
        if requirements:
            parts.append("この機能で過去に確定した要求（修正後も必ず維持すること）:\n"
                         + "\n".join(f"・{r}" for r in requirements[:30]))
        if feedback:
            parts.append(f"[前回の検証・レビュー指摘（必ず修正すること）]\n{feedback}")
        parts.append(_PATCH_SCHEMA)
        raw = llm.generate("\n\n".join(parts), tier=ModelTier.PRO).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw)
        if data.get("full_rewrite") or not data.get("patches"):
            return None
        new_html = apply_patches(html, data.get("patches"))
        if new_html is None or not _is_valid_app_html(new_html):
            return None
        commands = data.get("commands")
        commands = ([c for c in commands if isinstance(c, dict) and c.get("name")]
                    if isinstance(commands, list) and commands else (current.get("commands") or []))
        state_mode = str(data.get("worker_state_mode") or current.get("worker_state_mode", "commands"))
        state_mode = state_mode if state_mode in {"commands", "state", "hybrid"} else "commands"
        state_schema = data.get("state_schema") if isinstance(data.get("state_schema"), dict) else current.get("state_schema", {})
        return ViewManifest(
            kind="app",
            feature=current.get("feature") or _slug(goal),
            title=(current.get("title") or goal)[:60],
            description=(str(data.get("description")) if data.get("description") else current.get("description", ""))[:200],
            theme=current.get("theme", "default") if current.get("theme") in _ALLOWED_THEMES else "default",
            html=new_html,
            commands=commands,
            worker_state_mode=state_mode,
            state_schema=state_schema if isinstance(state_schema, dict) else {},
            worker_instructions=str(data.get("worker_instructions") or current.get("worker_instructions", ""))[:4000],
            worker_examples=(
                [e for e in data.get("worker_examples", []) if isinstance(e, dict)][:16]
                if isinstance(data.get("worker_examples"), list)
                else current.get("worker_examples", [])
            ),
            worker_eval_cases=(
                [e for e in data.get("worker_eval_cases", []) if isinstance(e, dict)][:12]
                if isinstance(data.get("worker_eval_cases"), list)
                else current.get("worker_eval_cases", [])
            ),
            clarification_policy=str(data.get("clarification_policy") or current.get("clarification_policy", ""))[:2000],
            dangerous_action_policy=str(data.get("dangerous_action_policy") or current.get("dangerous_action_policy", ""))[:2000],
            generated_by=llm.name,
        )
    except Exception:  # noqa: BLE001 — any failure → fall back to a full rewrite
        return None
