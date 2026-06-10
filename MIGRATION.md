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

### Phase 0 — すぐ直せる（設定・小、低リスク）— ✅ テスト環境で検証済み
- [x] **PRO=Opus 正準の明文化**：`backend/app/config.py` のコメントを「PRO 正準=Opus、demo は sonnet override」に。`docker-compose.dev.yml` の `CLAUDE_PRO_MODEL=sonnet` は override として維持。
- [x] **codegen 二重 PRO 解消**：`orchestrator/service.py` `plan_and_register` を、`generate_plan(req)`（PRO）廃止 → 決定的 `_stub_plan` 骨格 ＋ 承認済み `design_plan` から組む。PRO は `ui_designer.design` の 1 回のみ。
- [x] **status にモデル**：providers に `model_for(tier)`、`llm/gateway.py` に `model_label(tier)`、`reception/service.py` の build 記録に `model`、`control_plane/monitor.py: running_workers` に `model` を含める。
- [x] **タイムアウト不整合の修正（発見）**：`llm_timeout_seconds` 180→**300**（ブリッジの `CLAUDE_TIMEOUT=300` より短く、フルアプリ生成が 180s 超でブリッジ完了前に stub フォールバックしていた）。
- [x] **テスト環境 検証**：pytest 19 passed。codegen 実走で実アプリ生成（`generated_by=claude-cli`, html~10.8KB, commands=4, ~112s）、monitor に `claude-cli:pro:sonnet` 表示。
- [ ] **本番デプロイ＋検証**：全フェーズのテスト確認完了後にまとめて実施（§5）。Phase 0 分の本番確認項目：`/health`=200・`generated_by="gemini"`・monitor に Gemini モデル名。

### Phase 1 — デプロイ前ゲート（Reviewer ＋ Tester）— ✅ テスト環境で実装・検証
- [x] **Reviewer**：`agents/reviewer.md`＋`workers/reviewer.py`。静的規約チェック＋LLM（FLASH）→ `{verdict: ok|needs_revision, findings[]}`。
- [x] **Tester**：`agents/tester.md`＋`workers/tester.py`。本番相当 Docker エミュレータ（モデルのみ claude）で、ロード可否＋構造＋commands結線の静的検証＋LLM（FLASH）の要求充足判定 → `{verdict: pass|fail, checks[], errors[]}`。（ヘッドレス実走は後続拡張）
- [x] **パイプライン組込**：`orchestrator/service.py` を `build_app`/`register_app` に分割。`reception/service.py: _run_codegen`・`_run_edit` で 生成→**ゲート（Tester+Reviewer を並列実行）**→通過で `register_app`、NG は feedback 付きで再生成（Phase 1 は `_GATE_MAX_ATTEMPTS=2` で暫定バウンド／Phase 4 でタイムアウト・ユーザー制御へ）。
- [x] **可視化**：検証/レビューの「実行中」「合否・指摘」を会話（system メッセージ）に出力。
- [x] **テスト**：`tests/test_gates.py`（7件）。pytest **26 passed**。
- [x] **ライブ確認**：ゲートが実走し、**壊れた生成物（HTML途中切れ）を検知して差し戻し**→ built 到達・指摘報告を確認。
- [x] **タイムアウト方針（能力↔時間トレードオフ）**：`llm_timeout_seconds` 300→**600**、bridge `CLAUDE_TIMEOUT` 300→**600**、Receptor の `_PHASE_BUDGET` codegen/editing 130→**300**。高能力モデルの長考を短く打ち切らない（停止判断はユーザー）。
- [ ] **happy-path クリーン通過のライブ採取**：本日はブリッジ（claude セッション）遅延で 300s 窓内に未採取。ブリッジが軽いとき or 本番 Gemini（高速）で確認。pass ロジックは単体テスト済み。

### Phase 2 — 版管理・巻き戻し・変更履歴 — ✅ テスト環境で実装・検証
- [x] **版スナップショット**：`registry.snapshot_version`／`list_versions`／`pop_version`（`feature_versions/{pid}_{feat}` に線形スタック）。`approvals.approve`（新規公開）と `publish_edit`（改変公開）で push。`_RESET_COLLECTIONS` に追加。
- [x] **巻き戻し再定義**：`approvals.rollback_feature`＝直前版を再有効化（純粋ロジック `plan_rollback`）。版が1つだけなら作成取り消し＝無効化。`reception/router.py` の「戻して」を `registry.get_last_changed` の対象 feature に対する版巻き戻しへ接続（分岐なし・直線）。
- [x] **変更履歴 API**：`GET /api/control-plane/history/{project_id}`（`audit_logs` に `project_id` を付与し時系列・newest-first）。`GET /api/control-plane/versions/{project_id}/{feature}`（版メタ一覧）。
- [x] **テスト**：`tests/test_versioning.py`（純粋ロジック4件）＋ 全 **30 passed**。エミュレータ実走で v1→v2公開→巻き戻し(v1復元)→再巻き戻し(無効化)→history を確認（VERDICT: PASS）。
- [ ] フロント：変更履歴／版ビューの UI（後続）。

### Phase 3 — ワーカー基盤（構造・最大の山）— ✅ 基盤実装・検証／一部は後続
- [x] **worker レジストリ＋status**：`control_plane/worker_status.py`（`workers` コレクション：種別・状態 active/idle/stopped・**model**・**最終更新**）。`/api/control-plane/workers` に `registry` を追加。
- [x] **固着回収（reaper）**：`_effective_status`＝active かつ最終更新が `_STALE_SEC`(900s) 超なら stopped 扱い・`stale` フラグ。
- [x] **起動・停止 API**：`POST /worker/{type}/start`・`/stop`（他ワーカーから呼べる）。
- [x] **MCP 的（MCP-like）request/report**：`models/worker_protocol.py`（`WorkerRequest`/`WorkerReport`：`task_id`/`message_id`/`in_reply_to`/`intent`/`status`、`from` エイリアス）＋ `control_plane/worker_bus.py`（スキーマ検証＝不正は `rejected`、メッセージログ、相関）。※実 MCP ではなく内部の MCP 風契約。
- [x] **context 永続化**：`control_plane/worker_context.py`（save/load/rehydrate＋純粋 `plan_compaction`）。
- [x] **status 記録の配線**：Receptor（router）・Orchestrator（plan/codegen/edit）・Tester/Reviewer（gate）が要所で `record_status`。
- [x] **テスト**：protocol 5・context 4（純粋）＝計 **39 passed**。
- [ ] **後続（より大きな構造変更）**：全パイプラインを worker_bus 経由の**非同期 request/report＋停止中 wake-up** に載せ替え／**Orchestrator を関数群からセッション化**（R6：UI/API/検証のサブワーカー分割の是非）。今は contract と status 基盤まで。

### Phase 4 — 体験（UX）
- [ ] **Specialist 構造変更ルーティング**：`generated_app/*` のアプリチャットで構造変更を検知し、メインチャット（Receptor→Orchestrator）へ取り次ぐ。
- [ ] **タイムアウト3択UX**：`reception` の `diagnose_build` を、自動解除ではなく **①停止/②待つ/③停止して再トライ（直前成功段階から）** の確認に。**N=2** で強制停止＋報告。
- [ ] **透明性**：自動判定・内部情報を Receptor 経由で詳しくフィードバック。
- [ ] **ステータスモニターUI**：worker 一覧＋状態＋**使用モデル**表示。

---

## 3. 環境展開と検証サイクル（各フェーズ共通）

> **方針（確定）：本番デプロイは全フェーズのテスト環境動作確認が完了してから一括で行う。**
> 各フェーズはまず「テスト環境で実装・検証」まで進め、本番（提出 URL）への反映は最後にまとめて実施する。

各フェーズは次のステップで進める（当面はステップ 1–2 まで／3–4 は全フェーズ完了後）。

| # | ステップ | 環境 | 手段（参照） |
|---|---|---|---|
| 1 | **実装・起動** | テスト（ローカル） | `docker compose -f docker-compose.dev.yml up -d backend firestore`。LLM=claude CLI ブリッジ（`python scripts/claude_bridge.py`）／オフラインは `LLM_PROVIDER=stub` |
| 2 | **検証（テスト）** | テスト | 自動：pytest（[ENVIRONMENT.md](ENVIRONMENT.md) §2(C)）。手動：ローカル UI/API スモーク＋パイプライン実走 |
| 3 | **デプロイ** | 本番（Cloud Run） | `gcloud run deploy --source`（[DEPLOY.md](DEPLOY.md)）。LLM=Gemini、Firestore=本番 |
| 4 | **検証（本番）** | 本番 | `/health`=200、`/api/**` スモーク、`generated_by="gemini"`、公開 URL で e2e |
| 5 | **記録** | — | 変更履歴／監査（Phase 2 以降は本機能で）。本ファイルのチェックを更新 |

### テスト環境 検証コマンド（雛形）
```bash
# 自動テスト（リポジトリルート）
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml run --rm --no-deps \
  -v "${PWD}/backend/tests:/app/tests" \
  -e APP_ENV=test -e LLM_PROVIDER=stub -e FIRESTORE_EMULATOR_HOST= -e GOOGLE_CLOUD_PROJECT= \
  backend python -m pytest /app/tests -q

# 手動スモーク（バックエンド起動後）
curl -s http://localhost:8000/health
```

### 本番 検証コマンド（雛形）
```bash
URL=$(gcloud run services describe agentforge-core-api --region=asia-northeast1 --format='value(status.url)')
curl -s $URL/health ; echo
curl -s $URL/api/orchestrator/health ; echo
# 生成が実 Gemini か（work_plans の generated_by == "gemini"）
```

## 4. フェーズ別 検証マトリクス（テスト環境 / 本番で何を確認するか）

| Phase | テスト環境で確認 | 本番で確認 |
|---|---|---|
| **0** | pytest 緑／codegen が PRO **1 回**（ログ計測）／monitor 応答に **model** ／生成が体感短縮 | `/health`=200／生成で `generated_by="gemini"`／monitor に Gemini モデル名 |
| **1** | 規約NG・動作NG を意図的に作り**差し戻し**が発生／正常系で **Tester＋Reviewer 両通過 → pending**／単体テスト追加 | 実生成でゲート通過・NG 時の差し戻しがユーザーに見える／**Tester 実行基盤が本番で動く** |
| **2** | 公開→版保存→改変→公開→**巻き戻しで直前版に戻る**／`GET /history` が時系列を返す | 同等 e2e／巻き戻しが即時・公開済みに影響なし |
| **3** | worker status/registry・start/stop API・request/report の相関（`task_id`/`in_reply_to`）・**wake-up**・**固着 reaper**・context rehydrate の単体/結合テスト | **既存フロー非破壊**（段階リリース）／monitor に worker 種別・状態・model |
| **4** | Specialist 構造変更→メイン取り次ぎ／タイムアウト**3択**（N=2）／モニターUI | e2e UX 確認／透明性（自動判定が Receptor 経由で見える） |

## 5. 本番への展開 安全策（提出 URL を落とさない）

> 提出 URL（`https://agentforge-devops.web.app` ＝ Cloud Run `agentforge-core-api`）は**審査期間中に停止しない**。

- **必ずテスト環境で検証してからデプロイ**（このアプリ自身の Tester/Reviewer 精神をリポ運用にも適用）。
- Cloud Run は**新リビジョンをデプロイ → ヘルス確認 → トラフィック切替**。問題時は即ロールバック：
  ```bash
  gcloud run services update-traffic agentforge-core-api --region=asia-northeast1 --to-revisions=<PREV>=100
  ```
- **大きな構造変更（Phase 3）は feature flag／段階移行**で既存パスを壊さない。
- フロント（Firebase Hosting）は `npm run build` → `firebase deploy --only hosting`。バックエンドと**前方/後方互換**を保って順次反映。

## 6. 留意・未決
- **ゲートへの生成物の渡し方（決定）：インライン**（プロンプトに HTML をそのまま埋め込む）。本番 Gemini はローカルファイルパスを読めず内容はインラインが前提のため、**テスト環境も本番に準拠してインライン**で統一する。claude-cli 専用のファイルパス渡し最適化は**採用しない**（環境差を作らない）。※ プロンプト肥大による誤検知防止のため、HTML は丸ごと送る（スライス禁止）。上限 100KB 超のみ末尾省略＋「途切れ判定しない」マーカー付与。
- **アプリサイズの上限について**：ゲートのインライン渡しは現実的サイズ（〜数十 KB）なら FLASH の大文脈（Gemini Flash 〜1M / Claude Haiku 200K tok）で問題ない。**真の上限は生成側の出力トークン上限**（PRO が単一 HTML を一度に出力できる量）で、巨大アプリはここで頭打ち＝渡し方に関係なく生成段階で truncate する。スケールが必要になったら、**provider の Files API（Gemini/Claude 双方にあり＝本番でも同一）** で成果物を参照する方式に拡張する（ローカルパスではなく）。当面は不要。
- ~~**Tester 実行基盤**~~（決定済み）：**Docker 内に用意した「本番相当エミュレータ」環境**（`docker-compose.dev` 相当＝Firestore エミュレータ＋backend）で生成アプリを実働させて検証する。**LLM プロバイダのみ claude に差し替え**（コスト節約）、それ以外は本番同等。本番（Cloud Run）デプロイ前に本番同等条件で動作確認できる。
- **R6（Orchestrator 肥大／多エージェントの必然性）**：Phase 3 でサブワーカー分割の是非を判断（Tester 追加で多エージェント性は前進済み）。
- **N・閾値・リトライ回数**：タイムアウト N=2、失敗自動リトライ 1〜2 回、固着検出の閾値は実装時に定数化（後で調整可）。
