# AgentForge 機能生成の標準ポリシー（必ず順守）

このファイルはアプリ内の組み込みAIワーカー（Orchestrator / UI Designer 等）が
機能を生成するときに参照する「標準ルール」です。リポジトリで管理し、実行時に
プロンプトへ注入されます。人間向けの正準仕様は IMPLEMENTATION_GUIDE.md §2.5。

1. 新しい機能を追加するときは、その機能を管理する「機能AIワーカー（専門ワーカー）」を既定で設定する。
2. 機能AIワーカーへの指示入力エリア（アプリチャット）は **`has_worker=true` を付与すると、シェルが画面下部に
   別パネルとして用意する**。**生成する HTML（アプリ表示エリア）にはチャット／メッセージ入力／AIアシスタント欄を
   作らない**（作ると上部アプリ内と下部パネルでチャットが二重になる）。アプリエリア＝中身のみ、チャット＝下部の別パネル、と分離する。
   - 注：`has_worker` は<strong>パイプラインが view 登録時に付与するフラグ</strong>であり、UI Designer が出力する
     生成物 JSON（マニフェスト：feature/title/description/theme/html/commands/worker_state_mode/state_schema 等）には<strong>含めない</strong>。
     レビューで「生成物に has_worker が無い」と指摘するのは誤り。
3. ユーザーが「ワーカー不要 / ワーカーなし」等を明示した場合のみ `has_worker=false` にする（その場合は下部パネルも出ない）。
4. 安定・決定的な操作は API 化し（CRUD等・LLM不使用）、自然言語での運用・整理・設定変更は
   機能AIワーカーに委ねる（境界LLM＋決定的API＋動的UI）。
   - APIはユーザーが言いそうな自然文から逆算して設計する。単純な追加だけでなく、削除、更新、
     一括操作、対象指定、Undo/クリア、メモ追記、設定変更などを具体的に想定する。
     既存フィールドへ文章を入れる依頼（「メモに〜を記入」「本文に〜を書いて」「詳細に〜を追記」）は、
     set/update と append、または state 直接編集で標準的に扱えるようにする。
     「探して/調べて/最新情報をまとめて本文に入れて」は、生成HTMLから直接fetchせず、
     Specialist Worker の backend Web検索ツールが検索結果を要約して state/command に反映する前提で設計する。
     「予定を追加して、そのメモに〜を入れて」「タスクを作って、詳細に〜を書いて」のように
     1文に複数の操作が含まれる依頼は、可能なら `create -> update/append` のように小さな操作列へ分解して順に処理する。
     コマンドだけで表現しにくいデータ中心アプリは state 直接編集を使い、1回の応答で複数 entity / 複数 field を安全に更新できる設計にする。
     決定的なルールは「確信できる場合の近道」とし、過剰に固定文言へ縛って処理を止めない。
     対象や危険操作が曖昧な場合だけ聞き返し、本文生成・検索要約・軽い補完は Specialist Worker に判断させる。
     本文/メモ/詳細へ入れる内容は単なる転記にしない。短い断片でも、必要に応じてラベル、箇条書き、確認事項、
     持ち物、場所、TODO などに整理して、ユーザーが後で読みやすい形で保存する。
   - データ中心アプリは commands だけに閉じ込めず、`worker_state_mode`（`state` / `hybrid`）と
     `state_schema` を manifest に含める。専門ワーカーは現在の `AF.load()/AF.save()` state を
     schema に沿って直接編集でき、未知の新アプリにも個別API追加なしで対応できる。
   - 生成manifestには専門ワーカー用の `worker_instructions` と `worker_examples` を含め、
     API/state の使い分け、誤分類しやすい表現、情報不足時の聞き返し方をアプリごとに明記する。
     例には本文/メモ欄への記入・追記、Web検索結果の要約記入、断片的依頼の整理、追加と更新を組み合わせた複合命令を含める。
   - 生成manifestには `worker_eval_cases`、`clarification_policy`、`dangerous_action_policy` も含める。
     `worker_eval_cases` は追加/更新/削除/一括操作/曖昧な対象/異常値/担当外の構造変更など、
     専門ワーカーが誤りやすい自然言語指示を具体的に想定する。
5. AI は生成物を pending 登録するのみ。active 化・本番反映・rollback は人間の承認を要する
   （AIに強権限を渡さない / Control Plane 経由・全操作を監査）。
   - パイプライン中の判断・進捗・検証・レビュー・リトライ・承認は Agent Harness の `pipeline_runs`
     に記録する。ユーザーには raw trace ではなく、短い進捗、判断理由、承認前サマリーとして表示する。
6. 状態を持つミニアプリは、画面遷移・リロード・別メニューへ移動して戻った後も途中状態を復元できるようにする。
   タスク/メモ/フォーム/設定だけでなく、ゲームの盤面・スコア・進行状態も `AF.load()` / `AF.save()` で
   サーバ側に保存する。`localStorage` / `sessionStorage` / cookie は使わない。
   外部サービスを使うミニアプリでも、生成 HTML から `fetch` / `XMLHttpRequest` / 任意 URL への通信をしてはいけない。
   外部接続はミニアプリ自身がユーザー入力から `AF.defineConnector({...})` で feature-scoped connector を定義し、
   登録済み action を `AF.api("connector_id.action_id", params)` で呼ぶ。URL、ヘッダ、トークンは backend に保存し、
   生成 HTML の state や画面には保存・再表示しない。GitHub/Notion 等の有名サービスも固定管理者コネクタではなく、
   必要ならミニアプリ内の「接続テンプレート」として定義フォームの初期値にするだけに留める。
   connector 定義は `AF.defineConnector` 側で永続化されるため、接続設定だけを理由に AF.save state や
   `worker_state_mode=hybrid` を作らない。保存済み接続の表示は `AF.listConnectors()` を使う。
   action は `query_template` / `body_template` を持てる。テンプレートでは `$params.xxx`（呼び出し時引数）と
   `$secret.password` / `$secret.token` / `$secret.username`（connector auth に保存済みの secret）だけを参照できる。
   例: 保存済み App Password を JSON body に入れて session を再発行する場合は
   `auth:{type:"none", username:identifier, password:password}` で secret だけ保存し、
   `body_template:{identifier:"$secret.username", password:"$secret.password"}` とし、HTML state に password を戻さない。
   `AF.api()` の戻り値は外部 API のレスポンス本体をトップレベルにも展開し、同じ値を `data` にも保持する。
   例: session API が `{accessJwt:"..."}` を返す場合、`res.accessJwt` と `res.data.accessJwt` の両方で読める。
   接続状態は「保存済み」「接続確認成功」「session 有効」「最終エラー」を分けて表示し、接続確認に失敗しても
   connector 保存済みなら未保存扱いに戻さない。
   外部 API 由来の投稿本文・表示名・URL・alt 等を DOM に入れる場合、`innerHTML` へ未エスケープ文字列を連結しない。
   `textContent` / `createTextNode` か、`& < > " '` を処理する `escapeHtml()` を使う。
   外部画像 URL やリンク URL を `src` / `href` に直接入れない。リンクを開く必要がある場合は
   ユーザーのクリック操作で `AF.openExternal(url)` を呼ぶ。表示上は `<button type="button">` 等を
   下線・リンク色でスタイルしてリンク風に見せてよいが、外部遷移の実処理は必ず `AF.openExternal`
   に集約し、`href` / `window.open` / `element.href = url` は使わない。リンク風ボタンの表示名は
   URL 文字列そのものではなく、検索結果タイトル、記事タイトル、店名、サービス名、または
   「公式サイト」「地図を開く」「詳細を見る」のようなユーザーに意味が伝わる短いラベルを優先する。
   URL しか分からない場合だけ、ホスト名など短く読める形に省略して表示する。画像実体が必要な場合は承認済み
   backend/Blob 経路と `AF.loadBlob()` 欠落表示を用意する。
   Bluesky/AT Protocol の App Password は Bearer token ではない。App Password は connector secret として保存し、
   ログイン用 connector の `auth.type` は `none` にし、Basic 認証ヘッダを出さない。
   `createSession` action では `body_template` で `$secret.username` と `$secret.password` を送る。返った `accessJwt` は
   `auth:{type:"bearer", token: accessJwt}` の短期 API connector に入れて認証が必要な API を呼ぶ。
7. ユーザーがアプリ自体を明示的に削除した場合は、
   「アプリを削除すると、アプリ内で保存したデータもすべて失われます。よろしいですか？」という趣旨で確認し、
   確認後は完全削除する。
   生成ビュー、AF.save の state、エンティティ、アプリチャット履歴、版スナップショット、要求台帳、
   feature_states の該当メタ情報、現在の端末に保存された AF.saveBlob の Blob なども削除する。
   状態を残して左メニューからだけ外す削除は、後の再作成・schema 変更時のエラー源になるため実装しない。
   監査ログは「誰がいつ削除したか」の記録として残す。巻き戻し（rollback）は別操作であり、復元可能性を保つためデータを消さない。
