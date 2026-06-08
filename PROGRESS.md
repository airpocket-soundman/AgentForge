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
- ⬜ 実 Gemini 接続確認（ローカルは stub。Secret Manager 経由は Cloud Run デプロイ時）
- ⬜ Cloud Run へデプロイ＝**必須要件（Cloud Run＋Gemini）クリア＝提出可能状態**（次の大目標）
- ⬜ ADK 採用（現状は google-genai 直叩き。ADK化は加点）

## Phase 3: Worker + Cloud Tasks + 生成UI manifest ⬜
## Phase 4: 承認 → active化 → Task API 稼働 ⬜
## Phase 5: Rollback + Audit + SA分離 ⬜
## Phase 6: CI/CD（GitHub→Cloud Build→Cloud Run）+ 仕上げ ⬜
## Phase 7: 提出物（デモ動画 / アーキ図 / ProtoPedia / デプロイURL固定）⬜

---

## 直近の次アクション
1. **Claude**: Cloud Run へ core-api をデプロイ（Secret Manager の `gemini-api-key` を環境変数注入＋SAに secretAccessor）。これで必須要件クリア＝提出可能ラインに到達。
2. **Claude**: フロントに「作業計画／pending登録／承認待ち」を表示するパネルを追加（task_id/approval_id は既に返却済み）。
3. **Claude**: Phase 4 の承認→active化（approval_requests を承認すると registry を active に）＋ Task API 実体。
4. **人間**: Cloud Run デプロイ時の権限承認クリック（コマンドは Claude が用意）。

> 完了済み: ① Geminiキー登録 ② Firebase一式（Auth実ログイン確認済）。
