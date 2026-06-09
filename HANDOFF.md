# AgentForge 引き継ぎ資料（セッション/PC間ハンドオフ）

最終更新: 2026-06-08

このファイルは、別セッション・別PCで作業を継続するための現在地まとめ。詳細は各リンク先を参照。

---

## 0. 目的（最重要）

- **提出先**: DevOps × AI Agent Hackathon 2026（主催 Findy／メインスポンサー Google Cloud Japan）
- **提出締切**: **2026-07-10 23:59**（ProtoPedia）。最終ピッチ 8/19 渋谷、決勝10チーム発表 7/30。
- **作品**: AgentForge ＝「自然言語でアプリを育てると、裏で AI エージェント群が DevOps（設計→実装→デプロイ→承認→巻き戻し）を回す **DevOps AI Agent Workbench**」。
- **対象ユーザー/課題**: 社内の非エンジニア業務担当者が、社内ツールを自分で作れず開発待ちになる課題。
- **最初の生成機能**: タスク管理 →（次に）PDFメモ。

参照: [要綱まとめ](agentforge_hackathon_contest_brief.md) / [公式原文](hackathon_official_source_record.md) / [実装ガイド](IMPLEMENTATION_GUIDE.md)

---

## 1. ドキュメントの正準（どこを見るか）

- **生きた仕様（最新・正準）**: [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) — 特に **§2.5 実行時アーキテクチャ確定事項**
- **説明サイト（図解）**: [docs/index.html](docs/index.html) をブラウザで開く（左目次＋右iframe、SVG図12セクション）
- **元仕様3本（履歴＋改定追記）**: `agentforge_contest_submission_spec_audited.md` / `agentforge_hackathon_google_cloud_spec_with_control_plane.md` / `self_evolving_super_app_spec.md`
- **自動メモリ**（クロスセッション）: `~/.claude/projects/.../memory/` … contest-constraints / focus-strategy / dev-environment-policy / runtime-architecture-decisions

---

## 1.5 現在地スナップショット（2026-06-08 セッション終了時点・新セッション必読）

### 実装済み（main = `airpocket-soundman/AgentForge`）
- **ローカル開発**: `docker compose -f docker-compose.dev.yml up`（FastAPI reload + Firestore emulator + Vite）。詳細 [README.md](README.md)
- **Phase 1**: Firebase Google ログイン（実機確認済）→ チャット → Firestore 永続化
- **Phase 2**: Orchestrator（要求→作業計画JSON, 実Gemini）→ Control Plane が api/ui/approval を **pending 登録** ＋ 監査
- **Phase 4/5**: 承認→active化→**Task API（決定的CRUD）**／soft-disable ロールバック／audit。会話でも「反映して」「戻して」可
- **UI**: トップバー＋左ナビ（機能の目次）＋右メイン切替。タスクは表→行クリックで詳細（上=整理内容/下=タスクのワーカー会話）。トップバーに**巻き戻し**と**初期化(dev)**ボタン（人間専用）
- **機能AIワーカー（標準仕様）**: 各機能画面に運用指示チャット（`FeatureWorkerPanel`）。`has_worker` で ON/OFF。タスクは指示でタスク生成可
- **組み込みワーカーの指示＝リポジトリ管理ファイル**: `backend/app/agents/*.md`（policy/orchestrator/reception/ui_designer/feature_worker）をローダーが実行時に読み込みプロンプト注入。**プロンプト＝設定**
- backend pytest 11件 green

### デプロイURL
- **公開Webアプリ（提出URL候補）**: https://agentforge-devops.web.app （Firebase Hosting, site=`agentforge-devops`, `/api/**`→Cloud Run rewrite）
- **Cloud Run API**: https://agentforge-core-api-217469091476.asia-northeast1.run.app （実Gemini接続済）

### ⚠️ 最重要：本番バックエンドが main より古い（要再デプロイ）
- **Hosting（フロント）は最新**だが、**Cloud Run（バックエンド）は revision 00003（Phase 4世代）のまま**。
- 未反映の backend 機能：**agents/ポリシー読込・タスク詳細/ワーカー・初期化(reset)・会話承認・機能ワーカーAPI**。
- → これらは**ハードコード前提でフロントから呼ぶと 404**。**次の最初の作業＝バックエンド再デプロイ**（手順 [DEPLOY.md](DEPLOY.md) §3 / 下記）。
  ```bash
  cd ~/AgentForge && git pull && cd backend
  gcloud run deploy agentforge-core-api --source . --region=asia-northeast1 \
    --allow-unauthenticated --min-instances=0 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=agentforge-498808,GOOGLE_CLOUD_REGION=asia-northeast1,ALLOWED_EMAILS=yamashita.3154@gmail.com" \
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest"
  ```
- **アクセス制限**: `ALLOWED_EMAILS`（`;`区切り）で**許可メールのみ利用可**。許可外は API 403／UIは「アクセス権限がありません」。空＝制限なし。審査員に見せるなら審査員メールを追加。
- **未確認の人間作業**: Firebase Auth 承認済みドメインに `agentforge-devops.web.app` を追加（未だと本番でログイン不可 `auth/unauthorized-domain`）。

### 環境メモ（ハマりどころ）
- backend ローカルは host 8000（host 8080 は WSL relay 占有）。frontend `.env.local` は gitignore（Firebase web config）。
- 本番検証は **PowerShell `Invoke-RestMethod`** が確実（Git Bash の curl は一部不安定／日本語表示が cp932 で化けるが実データは正常）。
- Cloud Run の GFE は **空POSTでも Content-Length 必須**（curl は `--data ''`。ブラウザ fetch は自動付与）。
- firebase CLI は host に導入済・ログイン済（`firebase deploy --only hosting` で公開）。gcloud は host 未導入＝Cloud Shell 使用。

---

## 1.6 コーディングパイプライン現状 ＋ 次タスク（2026-06-09 記録）

### 用語（確定）
- **ミニアプリ**＝ユーザー要求で生成される個々の機能（kind=app の生成HTML、または kind=data）。
- **専門ワーカー**＝ミニアプリごとの管理ワーカー。**メインの生成パイプラインから切り離し済み**。中身（描画/テキスト/データ）の編集だけ担当。構造変更は「メインチャットへ」と誘導。

### 現状のパイプライン（コード実測）
```
Reception(受付) → Orchestrator(判定) → UI Designer(設計案→コード生成) → Control Plane(承認→公開)
                                                       ＋ 実行時：専門ワーカー(中身編集・MCP形式ツール)
```
- **Reception**（reception/service.py）＝ほぼ**配管**：キーワードで粗く意図判定（LLMでない）＋フロー管理(plan→built)＋進捗/チェック/エラーのチャット報告＋承認/戻す/中止＋スタック復旧。LLM使用は building_status_reply の1箇所。
- **Orchestrator**（orchestrator/service.py）＝**実LLM判定が主脳**：`classify_request` が create/edit/chat を判定＋指示語解決。**ただし `generate_plan` が作る作業計画のワーカー羅列（api_designer/programmer/test_agent/devops_agent）は“飾り”で実行されない**。
- **UI Designer**（workers/ui_designer.py）＝**実働の主役**：`plan_feature`(設計案/Flash)→`design`(HTML生成/Pro)。生成HTMLに MCP形式の `applyAgentCommand` ＋ `commands` を埋め込む（専門ワーカー用ツール契約）。
- **Control Plane**＝承認→active化・監査（LLMでない統制）。

### このセッションで入れた変更（未整理・要レビュー）
- 専門ワーカーをメインパイプラインから**分離**（構造変更はメイン、専門ワーカーは中身のみ）。
- **MCP形式のツール契約**（ミニアプリが `name/description/inputSchema` を宣言＝`commands`、呼び出しは `{name, arguments}`、トランスポートは manifest＋postMessage で常駐接続なし）。
- ローカルLLM速度：codegen=Sonnet / 軽処理=Haiku（CLI既定のOpusは遅いため。docker-compose.dev.yml）。
- 生成中の**進捗・チェック・エラーをチャットに随時報告**（reception の _progress/_check_report、role=system）。

### 次タスク：パイプラインの整理し直し
1. **判定をOrchestratorに一本化**（Receptionの二重キーワード判定を“制御語の即時ゲート＋配管”に縮小）。
2. **飾りワーカー（api_designer/programmer/test_agent/devops_agent）を撤去**し、作業計画を実態（UI Designerが設計＋実装）に合わせる。
3. ↑を IMPLEMENTATION_GUIDE §2.5/2.6 と agents/*.md にも反映して整合。
4. （任意）エラー→Orchestrator自動リトライの軽量ループ、Test/Review相当の検証ステップ。

---

## 2. 確定した重要設計（要点）

- **通信**: ブラウザ↔Reception は REST/HTTPS（Firebase Auth ID token）。**MCPは不採用**。進捗はブラウザが **Firestore をリアルタイム購読**。
- **コスト**: 全 Cloud Run サービスは **原則 min=0（コールドスタート許容）**。Worker は Cloud Tasks で必要時起動。アイドル≈¥0。
- **生成機能の実行モデル**: 「**境界LLM（小型 Gemini Flash）＋ 決定的API ＋ 動的UI(manifest)**」の三点セット。UI不変時はAPI直叩きで節約。
- **永続化API は機能ごとに増える**: 編集可能なUI要素（チェック/メモ/フォーム）の状態保存に CRUD API が必要。汎用CRUDエンジン＋特化APIのハイブリッド。
- **ワーカー非常駐＋Context永続化**: 文脈は Firestore（Context DB）に保存し起動毎に rehydrate。
- **永続化と再開**: アプリを閉じても裏で作業継続、再開時に閉じていた間のAIメッセージも復元（Firestore永続）。
- **安全**: AIに強権限を渡さない（Control Plane / Tool Gateway / SA分離 / Audit / Rollback、delete禁止・disable優先）。

---

## 3. 開発環境（別PC再現）

- **方針**: 開発＝**Docker Dev Container**、本番＝Cloud Run コンテナ。バージョン全ピン留め。
- **再現**: Docker Desktop を入れて clone → VS Code「Reopen in Container」で同一環境を自動構築。
- **採用バージョン**: Python 3.12 / Node 24 / gcloud・firebase（コンテナ内）。詳細 [ENVIRONMENT.md](ENVIRONMENT.md)。
- **ホスト現状（初期開発機 Win11）**: node24/npm/git あり、Python3.12導入済、firebase(npm global)導入済、Docker Desktop 導入済（本番Dockerfileのビルド＆/healthz=200 をローカル検証済み）。gcloud はホスト未導入（Cloud Shell 利用）。

---

## 4. Google Cloud 現状（Phase 0 ほぼ完了）

- **プロジェクト**: `agentforge-498808`（番号 217469091476）／リージョン **asia-northeast1**／課金有効（無料枠）
- **作成済み**:
  - API 有効化一式（run/build/artifactregistry/firestore/cloudtasks/secretmanager/storage/aiplatform/generativelanguage/firebase/iam）
  - Firestore Native（asia-northeast1, default, 無料枠）
  - Storage バケット: `agentforge-498808-{artifacts,uploads,snapshots,build-source}`
  - Artifact Registry: `agentforge`（docker）／ Cloud Tasks: `worker-queue`
- **本番デプロイ済み（Phase 2 / 2026-06-08）**: Cloud Run `agentforge-core-api`
  - URL: https://agentforge-core-api-217469091476.asia-northeast1.run.app
  - **本リポジトリのコード**を Cloud Shell から `gcloud run deploy --source` で配置（手順 [DEPLOY.md](DEPLOY.md)）
  - `gemini-api-key`（Secret Manager）を `GEMINI_API_KEY` として注入。実行SAに `secretAccessor` / `datastore.user` 付与
  - 確認済: `/health`=200、`/api/orchestrator/plan` で `generated_by="gemini"`（実Gemini接続）
  - **🎯 必須要件（Cloud Run＋Gemini）＋公開デプロイURL を充足＝提出可能ライン到達**。後でGitHub→Cloud Build CI/CDに置換（Phase 6）

### 既知事項（対応状況）
- **【解決済】** スモークの `/healthz` 404 は、**Cloud Run（Google Front End）が `/healthz` パスを横取り**するのが原因（応答は Server 空＋Google の HTML 404 で、コンテナに届かない）。`/health` はアプリに到達する。→ バックエンドのヘルスを **`/health`** に変更済み（[backend/app/main.py](backend/app/main.py)）。教訓メモ: memory `cloud-run-reserved-healthz`。スモーク（`af-smoke`）は使い捨てなので未修正のまま放置でよい。
- **【検証済】** `backend/requirements.txt` はクリーンな Python 3.12 でインストール成功（fastapi/uvicorn/pydantic/google-cloud-firestore/-storage/-tasks/google-genai、依存衝突なし）。
- まだ未実施: サービスアカウント分離＋IAM、Firebase(Hosting/Auth)初期化、Gemini APIキーの Secret Manager 登録、GitHub→Cloud Build の正式CI/CD。

---

## 5. リポジトリ構成（現状）

```
backend/                FastAPI core API（modular monolith）
  app/main.py             app factory（/health,/ ＋ ルータ束ね）
  app/config.py           環境変数ベース設定（pydantic-settings）
  app/firestore.py        Firestore クライアント（emulator 対応）
  app/models/             Pydantic モデル
  app/reception/          Phase 1: チャット即応モジュール（router/service）
  tests/                  pytest（4件 green）
  Dockerfile / Dockerfile.dev  本番(Cloud Run) / 開発(reload)
frontend/               React+Vite+TS（チャットUI、/api プロキシ、Firebase stub）
.devcontainer/          Dev Container 定義（devcontainer.json, postCreate.sh）
docs/                   説明サイト（index.html + styles.css + pages/*.html、SVG図）
docker-compose.dev.yml  ローカル開発スタック（backend + Firestore emulator + frontend）
IMPLEMENTATION_GUIDE.md 生きた仕様（§2.5 が実行時アーキ正準）
ENVIRONMENT.md          開発環境＋GCP資源の正式記録
PROGRESS.md             Phase 別進捗トラッキング
agentforge_*.md / self_evolving_*.md / hackathon_*.md  仕様・要綱・公式記録
HANDOFF.md              このファイル
```

> ローカル開発は `docker compose -f docker-compose.dev.yml up --build`（GCP認証不要・Firestoreはemulator）。詳細は [README.md](README.md) / [PROGRESS.md](PROGRESS.md)。

---

## 6. 次にやること（再開時のTODO）

実装は Phase 制（[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) §4 / docs「実装フェーズ」）。

- **【済】Phase 1 の足場**: ローカル Docker 開発環境、frontend スキャフォールド（チャットUI）、reception REST（`POST /api/reception/messages`・Firestore永続化・即応）、pytest。E2E検証済み。
1. **Phase 1 残り**: Firebase Auth（Googleログイン）連携＋ブラウザの Firestore リアルタイム購読を frontend に実装（現状は REST応答を表示するのみ）。Reception を Gemini Flash ルーティングに（現状は決定的テンプレ）。
2. **Phase 2**: Orchestrator（ADK+Gemini）で作業計画JSON → Control Plane registry 登録（ここで必須要件＝Cloud Run＋Gemini を満たす）。
3. **GitHub→Cloud Build の正式CI/CD**を設定（push で Cloud Run 自動デプロイ）。本リポジトリ（airpocket-soundman/AgentForge）を使う。
4. サービスアカウント分離＋IAM、Gemini APIキーを Secret Manager 登録、Firebase 初期化。
5. Phase 3〜7（Worker/Cloud Tasks/生成UI manifest → 承認→active→Task API → Rollback/Audit → CI/CD仕上げ → 提出物）。

> 詳細な現在地チェックリストは [PROGRESS.md](PROGRESS.md)。

### 役割分担
- **人間（ユーザー）**: GCP/Firebaseコンソール操作・課金、認証同意、GitHub操作、デモ動画/ProtoPedia提出。
- **Claude**: それ以外の実装すべて（コード・Dockerfile・CI/CD・gcloudコマンドの用意）。

### 注意（秘密情報）
- Gemini APIキー等はチャットに貼らない。**Secret Manager** に登録して使う。`.gitignore` は `*-key.json` / `service-account*.json` / `.env` を除外済み。
