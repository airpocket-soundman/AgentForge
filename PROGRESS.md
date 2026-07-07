# AgentForge 進捗トラッキング

> 実装の現在地。各 Phase の「ゴール」は [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) §4 準拠。
> 最終更新: 2026-07-07

凡例: ✅ 完了 / 🚧 着手中 / ⬜ 未着手

---

## 最新スナップショット（2026-07-07）

- ✅ **本番/デモ公開中**: Firebase Hosting `agentforge-devops.web.app` → Cloud Run `agentforge-core-api`
- ✅ **Cloud Run 最新 revision**: `agentforge-core-api-00018-jc9`（100% traffic）
- ✅ **Firebase Hosting 最新 release**: `sites/agentforge-devops/releases/1783390141966000`
- ✅ **Google ログイン修正済み**:
  - `authDomain` は標準 `agentforge-498808.firebaseapp.com` を使用
  - OAuth redirect URI に `https://agentforge-devops.web.app/__/auth/handler` を追加済み
  - hash route 起因の `redirect_uri_mismatch` / invalid action を回避
- ✅ **審査/デモ用ゲスト入口を Google アカウント不要化**:
  - 「審査員用ゲストログイン」から任意のユーザー名だけで入場
  - 同じユーザー名なら同じゲスト project を再開
  - backend は `X-AgentForge-Guest-Id` / `X-AgentForge-Guest-Name` を `GUEST_ACCESS_ENABLED=true` のときだけ受理
- ✅ **ローカル開発向けと本番向けの Firestore を分離**:
  - `APP_ENV=prod` では Firestore emulator 使用を拒否
  - `APP_ENV=local/demo/test` では emulator 必須
  - `docker-compose.dev.yml` は `agentforge-local-dev`
- ✅ **デフォルトテンプレートの最新規約対応**:
  - 全デフォルトテンプレート（`calculator`, `task_manager`, `schedule`, `memo`, `household_budget`, `translate`, `paint`, `retouch`, `bluesky`）を static Reviewer / Safety Harness で確認
  - 古いテンプレートの `worker_eval_cases` / `clarification_policy` / `dangerous_action_policy` 不足を補完
  - 電卓は `AF.load()` / `AF.save()`、`state_schema` 整合、`AC` トークン処理、履歴描画の DOM/textContent 化を実施
  - 追加テスト: 全テンプレートが deterministic Reviewer / Safety Harness を通過することを検証
- ✅ **確認済みテスト**:
  - `backend/tests/test_admin.py` → 7 passed
  - `backend/tests/test_templates.py backend/tests/test_safety_harness.py backend/tests/test_gates.py` → 30 passed
  - フロント `npm run build` → passed

---

## Phase 0: 基盤セットアップ ✅
- ✅ GCP プロジェクト `agentforge-498808` / asia-northeast1 / 課金有効
- ✅ API 有効化一式・Firestore(native)・Storage バケット・Artifact Registry・Cloud Tasks `worker-queue`
- ✅ スモークデプロイ（使い捨て Cloud Run `agentforge-core-api`、公開URL 200）
- ✅ 本番 Dockerfile / requirements.txt 検証、ヘルスを `/health` に確定
- ✅ Dev Container 定義（`.devcontainer/`）
- ✅ Gemini APIキーの Secret Manager 登録、Firebase Hosting/Auth 初期化
- ⬜ サービスアカウント分離＋IAMの本格化、GitHub→Cloud Build 正式CI/CD

## Phase 1: Web Shell + Reception 🚧
- ✅ **ローカル Docker 開発環境**（`docker-compose.dev.yml`: backend hot reload + Firestore emulator + frontend）。3サービス疎通・E2E検証済み
- ✅ backend モジュール化（`app/config.py`, `app/firestore.py`, `app/reception/`）
- ✅ Reception REST: `POST /api/reception/messages`（会話を Firestore 永続化＋即応＋簡易intent検出）。emulator 相手に動作確認済み
- ✅ frontend スキャフォールド（React+Vite+TS チャットUI、`/api` プロキシ、Firebase 初期化stub）
- ✅ backend 初期ユニットテスト（当時 pytest 4件 green。現在の確認済みテストは最新スナップショット参照）
- ✅ Firebase 実プロジェクト（`agentforge-498808`）に Web アプリ登録、`frontend/.env.local` 配線
- ✅ Firebase Auth（Googleログイン）：Google プロバイダ有効化＋フロント実装。**ブラウザで実ログイン動作確認済み（2026-06-08）**。IDトークンを API に添付
- 🚧 Gemini クライアント（[backend/app/llm/gemini.py](backend/app/llm/gemini.py)）：キー無しスタブで動作確認済み（`gemini-api-key` は Secret Manager 登録済）
- ✅ Firebase コンソールで Google プロバイダ有効化
- ✅ backend で Firebase ID トークン検証（通常ログイン）＋名前付きゲストヘッダ検証（ゲスト入口）
- ⬜ ブラウザの Firestore リアルタイム購読（現在は REST 応答を表示）
- ⬜ Reception の Gemini Flash ルーティング（現在は決定的テンプレ応答）

## Phase 2: Orchestrator + Gemini + Control Plane 🚧
- ✅ Orchestrator（[backend/app/orchestrator/](backend/app/orchestrator/)）: 要求→作業計画JSON生成。Gemini Pro 経路＋決定的テンプレ fallback（task / pdf_memo / unknown）
- ✅ Control Plane registry（[backend/app/control_plane/registry.py](backend/app/control_plane/registry.py)）: task_runs / work_plans / api_registry / ui_view_registry / approval_requests / audit_logs を Firestore に実装
- ✅ 計画と生成予定 API/View を **pending 登録** ＋ 承認リクエスト（pending_user_approval）＋ 全操作を audit_logs に記録
- ✅ reception が build intent を検出→Orchestrator へ連携→計画サマリを返信
- ✅ E2E検証（emulator）：「タスク管理を追加して」→ task_run/work_plan/api×3 pending/view pending/approval/audit 14件。pytest 8件 green
- ✅ **Cloud Run へデプロイ完了（2026-06-08）**。公開URL: https://agentforge-core-api-217469091476.asia-northeast1.run.app
- ✅ **実 Gemini 接続確認**：本番 `/api/orchestrator/plan` で `generated_by="gemini"`（Secret Manager の `gemini-api-key` を環境変数注入、SAに secretAccessor 付与）
- ✅ **🎯 必須要件クリア（Cloud Run 実行 ＋ Gemini API 利用 ＋ 公開デプロイURL）＝最低限の提出可能状態に到達**
- ⬜ ADK 採用（現状は google-genai 直叩き。ADK化は加点）

## Phase 3: Worker + Cloud Tasks + 生成UI manifest ⬜
（現状 Orchestrator は同期実行。Cloud Tasks 非同期化＋UI Designer による view_manifest 生成は後続）

## Phase 4: 承認 → active化 → Task API 稼働 ✅（バックエンド）
- ✅ 承認API（[backend/app/control_plane/approvals.py](backend/app/control_plane/approvals.py)）: approve で api_registry/ui_view_registry を active化＋feature_states フラグ＋task_run active＋監査
- ✅ Task API（[backend/app/generated_app/tasks.py](backend/app/generated_app/tasks.py)）: 一覧/追加/更新の決定的CRUD（Firestore `app_tasks`）。**feature が active でないと 409**（承認の意味付け）
- ✅ E2E（emulator）: 承認前=409 → 承認 → 作成200 → 一覧 → done=true、全部確認。pytest 10件 green
- ✅ **本番（公開URL）でもE2E実証**: 当時 revision 00003 で、計画→承認前409→承認→作成200→一覧→done=true→rollback後409 を確認。現在の本番 revision は `agentforge-core-api-00018-jc9`
- ⬜ フロントに承認ボタン＋Task UI（次：UI連携）

## Phase 5: Rollback + Audit + SA分離 🚧
- ✅ Rollback（soft-disable）: `POST /api/control-plane/features/{project}/{feature}/disable` → 再び 409（delete せず disable＝安全設計）。E2E確認済
- ✅ Audit: 全 Control Plane 操作を audit_logs に記録（plan登録/承認/disable）
- ⬜ checkpoint/snapshot 復帰、Audit のUI表示、SA分離の本格化
## Phase 6: CI/CD（GitHub→Cloud Build→Cloud Run）+ 仕上げ ⬜
## Phase 7: 提出物（デモ動画 / アーキ図 / ProtoPedia / デプロイURL固定）⬜

---

## 直近の次アクション（新セッションはここから）
1. **本番 UI 確認**: https://agentforge-devops.web.app をハード更新し、以下を一連確認。
   - 任意ユーザー名ゲストログイン → アプリ画面へ入れる
   - 「電卓を作って」→ デフォルト電卓が Safety Harness を通過し、プレビューが出る
   - 「反映して」→ 公開、画面遷移/リロード後も電卓状態が復元される
2. **全デフォルトアプリの実働サンプリング**: static gate は全件通過済み。次は UI 上で `task_manager` / `schedule` / `memo` / `household_budget` / `translate` / `paint` / `retouch` / `bluesky` を代表操作だけ確認。
3. **品質ループ強化**: default deploy でも gate 指摘を Orchestrator に戻して小さく直すループはあるが、同じ失敗の繰り返しを避けるため、指摘の重複検出・失敗理由の構造化・テンプレート回帰テストへの自動昇格を検討。
4. **提出準備**: ProtoPedia 記事、タイトル画像、デモ動画、アーキ図を最終化。

> 完了済み: ① Geminiキー登録 ② Firebase Hosting/Auth ③ Cloud Run デプロイ ④ Hosting 公開 ⑤ Phase 4/5・UI刷新・機能AIワーカー・agentsポリシー外部ファイル化 ⑥ 名前付きゲストログイン ⑦ Firestore 環境分離 ⑧ デフォルトテンプレート規約追従。
