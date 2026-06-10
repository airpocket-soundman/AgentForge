# 実装移行計画（現行コード → ワーカー仕様への適合）

> 正本は [docs/pages/workers.html](docs/pages/workers.html)（ワーカー定義・運用ルール）と
> [docs/pages/code-conventions.html](docs/pages/code-conventions.html)（コード規約）。
> 本ファイルは、現行コードをその仕様に寄せるための**フェーズ別チェックリスト**。
> 実装したら各項目にチェックを入れ、必要なら正本側も更新する。
> 最終更新: 2026-06-10

---

## 0. 現状サマリ（実装の今）

- **モノリシック FastAPI**。「動いているワーカー」の実体は、会話ドキュメントの `build.status == "designing"`
  なバックグラウンド Thread（`control_plane/monitor.py: running_workers`）。**ワーカー種別ごとの独立セッションではない。**
- **Receptor 相当** = `reception/`（名称は reception）。
- **Orchestrator 相当** = `orchestrator/service.py` の関数群（`classify_request` / `generate_plan` / `_gemini_plan` / `plan_and_register`）。
  実ビルドは `workers/ui_designer.py`（`plan_feature` 設計案 ＋ `design` コード生成）。
- **承認** = `control_plane/approvals.py`（`approve`/`reject`/`disable_active_features`）。`reception/router.py` が「反映して/戻して」を捌く。
- **不在**：Reviewer・Tester、Specialist の「ワーカー」化、worker 種別ごとの status/model 記録・起動停止 API、
  MCP 的 request/report・wake-up、context 保存ファイル、版スナップショット、変更履歴 UI、Specialist の構造変更ルーティング。

---

## 1. ギャップ一覧（仕様 → 現状 → アクション）

| 仕様（workers.html） | 現状 | アクション | Phase |
|---|---|---|---|
| PRO 正準 = Opus ↔ Gemini Pro | compose で `CLAUDE_PRO_MODEL=sonnet` | 正準を Opus とし、sonnet はデモ override と明記（動作はそのまま可） | 0 |
| codegen は PRO 1 回 | `plan_and_register` が PRO を2回（`generate_plan`＋`design`） | `generate_plan` の PRO 呼び出しを廃し承認済み plan から組む | 0 |
| ステータスに使用モデル | build 記録にモデル無し | 記録＋ monitor 表示 | 0 |
| Reviewer（規約適合ゲート） | 無し | `agents/reviewer.md`＋`workers/reviewer.py`、パイプラインに組込 | 1 |
| Tester（動作検証ゲート） | 無し | `workers/tester.py`（サンドボックス実行＋判定）、組込 | 1 |
| デプロイ前に検証・レビュー両方 | 生成→即 pending | 両ゲート通過後に pending、NG は差し戻し | 1 |
| 公開ごとに版スナップショット | 無し | approve 時に HTML/設定を版保存 | 2 |
| 巻き戻し=直前版へ即時復元 | `disable_active_features`（無効化） | 版復元に置換 | 2 |
| 変更履歴（ユーザー向け） | `audit_logs` はあるが UI 無し | `GET /api/control-plane/history` | 2 |
| worker 種別ごとの status/model/最終更新 | build 単位のみ | worker レジストリ＋status 記録 | 3 |
| 起動・停止 API／MCP request-report／wake-up | in-process Thread | ワーカー基盤を新設 | 3 |
| 非常駐・context 保存/rehydrate/compaction | 部分（task_worker の要約のみ） | 全ワーカー共通の context 永続化 | 3 |
| Orchestrator を正式ワーカー化 | 関数群 | セッション化（R6 のサブ分割もここで判断） | 3 |
| Specialist の構造変更→メイン取り次ぎ | 無し | 検知＆ルーティング | 4 |
| タイムアウト3択UX（Receptor・N=2） | `diagnose_build` は stuck で自動解除 | 3択確認フローへ | 4 |
| 固着回収（reaper） | `diagnose_build` の stuck 判定 | status の最終更新で停止扱い | 3/4 |

---

## 2. フェーズ別チェックリスト

### Phase 0 — すぐ直せる（設定・小、低リスク）
- [ ] **PRO=Opus 正準の明文化**：`backend/app/config.py` のコメント/既定方針を「PRO 正準=Opus、demo は override」に。`docker-compose.dev.yml` の `CLAUDE_PRO_MODEL=sonnet` は override コメントを付けて維持。
- [ ] **codegen 二重 PRO 解消**：`backend/app/orchestrator/service.py` `plan_and_register` で `generate_plan(req)` の PRO 呼び出しをやめ、承認済み `design_plan`（＋決定的 `_stub_plan`）から `WorkPlan` を組む。PRO は `ui_designer.design` の 1 回のみ。
- [ ] **status にモデル**：`reception/service.py` の `_set_build` 等に使用モデル名を載せ、`control_plane/monitor.py: running_workers` の出力に含める。
- [ ] 動作確認：[ENVIRONMENT.md](ENVIRONMENT.md) §2(C) の pytest が緑。codegen が体感で短縮。

### Phase 1 — デプロイ前ゲート（Reviewer ＋ Tester）
- [ ] **Reviewer**：`backend/app/agents/reviewer.md`（規約=code-conventions と同一規範）＋ `backend/app/workers/reviewer.py`。入力=生成物、出力=`{verdict: ok|needs_revision, findings[]}`（FLASH）。
- [ ] **Tester**：`backend/app/workers/tester.py`。生成HTMLをサンドボックス実行（**実行基盤は要決定**：ヘッドレスブラウザ or 軽量ロード＋LLM判定）。出力=`{verdict: pass|fail, checks[], errors[]}`。
- [ ] **パイプライン組込**：`reception/service.py: _run_codegen` / `orchestrator/service.py: plan_and_register` を、生成→**Tester＋Reviewer 通過→pending 登録**に。どちらか NG は再生成（差し戻しループ、自動回数で打ち切らない）。
- [ ] **可視化**：検証/レビューの開始・結果を会話（Receptor 経由）に流す。
- [ ] テスト追加：ゲート通過/差し戻しの単体テスト。

### Phase 2 — 版管理・巻き戻し・変更履歴
- [ ] **版スナップショット**：`control_plane/approvals.py: approve` で、公開する HTML/設定を版として保存（`generated_views` のサブコレクション or Cloud Storage＋Firestore ポインタ）。
- [ ] **巻き戻し再定義**：現行の `disable_active_features` ベースを、**直前版を再有効化**する処理に置換（`approvals`/`registry`）。会話「戻して」を版復元に接続（`reception/router.py`）。分岐なし・直線。
- [ ] **変更履歴 API**：`control_plane/router.py` に `GET /api/control-plane/history`（`audit_logs` を「いつ・誰が・何を・なぜ」で整形）。
- [ ] フロント：変更履歴ビュー（後続）。

### Phase 3 — ワーカー基盤（構造・最大の山）
- [ ] **worker レジストリ＋status**：Firestore に worker 種別・状態（活動/待機/停止）・**model**・**最終更新時刻**。`monitor` を build 単位から worker 単位へ拡張。
- [ ] **固着回収（reaper）**：status の最終更新が閾値超で停止扱い（Receptor/モニター）。
- [ ] **起動・停止 API**：worker を起こす/止める。**他ワーカーから呼べる**。
- [ ] **MCP 的 request/report**：`task_id`/`message_id`/`in_reply_to`、`intent`(plan/build/edit/verify/review/operate)、スキーマ検証（不正=`rejected`）、**基本は待ち＋誤停止時 wake-up**。
- [ ] **context 永続化**：各ワーカーの保存ファイル・rehydrate・コンパクト化（`task_worker` の整理済み要約を雛形に共通化）。
- [ ] **Orchestrator 正式ワーカー化**：`orchestrator/` の関数群をセッション化。**R6 判断**：UI/API/検証などサブワーカーへ分割するか。

### Phase 4 — 体験（UX）
- [ ] **Specialist 構造変更ルーティング**：`generated_app/*` のアプリチャットで構造変更を検知し、メインチャット（Receptor→Orchestrator）へ取り次ぐ。
- [ ] **タイムアウト3択UX**：`reception` の `diagnose_build` を、自動解除ではなく **①停止/②待つ/③停止して再トライ（直前成功段階から）** の確認に。**N=2** で強制停止＋報告。
- [ ] **透明性**：自動判定・内部情報を Receptor 経由で詳しくフィードバック。
- [ ] **ステータスモニターUI**：worker 一覧＋状態＋**使用モデル**表示。

---

## 3. 留意・未決
- **Tester 実行基盤**：本番 Cloud Run で生成HTMLを実行する手段（Playwright 等）を置くか、軽量版（ロード＋静的＋LLM判定）にするか。Phase 1 着手時に決定。
- **R6（Orchestrator 肥大／多エージェントの必然性）**：Phase 3 でサブワーカー分割の是非を判断（Tester 追加で多エージェント性は前進済み）。
- **N・閾値・リトライ回数**：タイムアウト N=2、失敗自動リトライ 1〜2 回、固着検出の閾値は実装時に定数化（後で調整可）。
