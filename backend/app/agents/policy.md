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
   - データ中心アプリは commands だけに閉じ込めず、`worker_state_mode`（`state` / `hybrid`）と
     `state_schema` を manifest に含める。専門ワーカーは現在の `AF.load()/AF.save()` state を
     schema に沿って直接編集でき、未知の新アプリにも個別API追加なしで対応できる。
   - 生成manifestには専門ワーカー用の `worker_instructions` と `worker_examples` を含め、
     API/state の使い分け、誤分類しやすい表現、情報不足時の聞き返し方をアプリごとに明記する。
5. AI は生成物を pending 登録するのみ。active 化・本番反映・rollback は人間の承認を要する
   （AIに強権限を渡さない / Control Plane 経由・全操作を監査）。
6. 状態を持つミニアプリは、画面遷移・リロード・別メニューへ移動して戻った後も途中状態を復元できるようにする。
   タスク/メモ/フォーム/設定だけでなく、ゲームの盤面・スコア・進行状態も `AF.load()` / `AF.save()` で
   サーバ側に保存する。`localStorage` / `sessionStorage` / cookie は使わない。
