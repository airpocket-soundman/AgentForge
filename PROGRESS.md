# AgentForge 進捗トラッキング

> 実装の現在地。各 Phase の「ゴール」は [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) §4 準拠。
> 最終更新: 2026-06-08

凡例: ✅ 完了 / 🚧 着手中 / ⬜ 未着手

---

## Phase 0: 基盤セットアップ ✅
- ✅ GCP プロジェクト `agentforge-498808` / asia-northeast1 / 課金有効
- ✅ API 有効化一式・Firestore(native)・Storage バケット・Artifact Registry・Cloud Tasks `worker-queue`
- ✅ スモークデプロイ（使い捨て Cloud Run `agentforge-core-api`、公開URL 200）
- ✅ 本番 Dockerfile / requirements.txt 検証、ヘルスを `/health` に確定
- ✅ Dev Container 定義（`.devcontainer/`）
- ⬜ サービスアカウント分離＋IAM、Gemini APIキーの Secret Manager 登録、Firebase(Hosting/Auth) 初期化、GitHub→Cloud Build 正式CI/CD

## Phase 1: Web Shell + Reception 🚧
- ✅ **ローカル Docker 開発環境**（`docker-compose.dev.yml`: backend hot reload + Firestore emulator + frontend）。3サービス疎通・E2E検証済み
- ✅ backend モジュール化（`app/config.py`, `app/firestore.py`, `app/reception/`）
- ✅ Reception REST: `POST /api/reception/messages`（会話を Firestore 永続化＋即応＋簡易intent検出）。emulator 相手に動作確認済み
- ✅ frontend スキャフォールド（React+Vite+TS チャットUI、`/api` プロキシ、Firebase 初期化stub）
- ✅ backend ユニットテスト（pytest 4件 green）
- ✅ Firebase 実プロジェクト（`agentforge-498808`）に Web アプリ登録、`frontend/.env.local` 配線
- ✅ Firebase Auth（Googleログイン）：Google プロバイダ有効化＋フロント実装。**ブラウザで実ログイン動作確認済み（2026-06-08）**。IDトークンを API に添付
- 🚧 Gemini クライアント（[backend/app/llm/gemini.py](backend/app/llm/gemini.py)）：キー無しスタブで動作確認済み（`gemini-api-key` は Secret Manager 登録済）
- ⬜ Firebase コンソールで Google プロバイダ有効化（人間作業・残）
- ⬜ backend で Firebase ID トークン検証（現状フロントのみゲート）
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
- ⬜ フロントに承認ボタン＋Task UI（次：UI連携）

## Phase 5: Rollback + Audit + SA分離 🚧
- ✅ Rollback（soft-disable）: `POST /api/control-plane/features/{project}/{feature}/disable` → 再び 409（delete せず disable＝安全設計）。E2E確認済
- ✅ Audit: 全 Control Plane 操作を audit_logs に記録（plan登録/承認/disable）
- ⬜ checkpoint/snapshot 復帰、Audit のUI表示、SA分離の本格化
## Phase 6: CI/CD（GitHub→Cloud Build→Cloud Run）+ 仕上げ ⬜
## Phase 7: 提出物（デモ動画 / アーキ図 / ProtoPedia / デプロイURL固定）⬜

---

## 直近の次アクション
1. **人間**: Phase 4 を本番に反映するため core-api を**再デプロイ**（[DEPLOY.md](DEPLOY.md) の手順3を再実行）。`git pull` 後に `gcloud run deploy --source`。
2. **Claude**: フロントに「作業計画→承認ボタン→Task UI（一覧/追加/完了）→戻す」を実装し、デモ縦切りを画面で通す。
3. **Claude**: Firestore リアルタイム購読（task_runs / app_tasks）で進捗・一覧をライブ表示。
4. **後続**: Phase 3（Cloud Tasks 非同期 + view_manifest 生成）, Phase 6（CI/CD）, Phase 7（提出物）。

> 完了済み: ① Geminiキー登録 ② Firebase一式（Auth実ログイン確認済） ③ Cloud Run デプロイ（必須要件クリア）。
