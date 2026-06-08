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
- **スモークデプロイ済み（使い捨て）**: Cloud Run `agentforge-core-api`
  - URL: https://agentforge-core-api-217469091476.asia-northeast1.run.app
  - `/` は 200 で `{"message":"AgentForge core API is running."}` を返す（＝公開URL稼働＝提出要件のデプロイURLを満たせる状態）
  - Cloud Shell の `~/af-smoke` から `gcloud run deploy --source` で作成（本物のコードは本リポジトリ。後でCI/CDに置換）

### ⚠️ 既知の小問題（要再確認）
- スモークの `/healthz` が 404（`/openapi.json` には `/healthz` が載っているのに）。使い捨て側の貼り付け起因の可能性。**本番デプロイ時に再確認**（ローカルDockerでは /healthz=200 確認済み）。
- まだ未実施: サービスアカウント分離＋IAM、Firebase(Hosting/Auth)初期化、Gemini APIキーの Secret Manager 登録、GitHub→Cloud Build の正式CI/CD。

---

## 5. リポジトリ構成（現状）

```
backend/                FastAPI 雛形（app/main.py=/healthz,/、Dockerfile=本番用、requirements.txt）
.devcontainer/          Dev Container 定義（devcontainer.json, postCreate.sh）
docs/                   説明サイト（index.html + styles.css + pages/*.html、SVG図）
IMPLEMENTATION_GUIDE.md 生きた仕様（§2.5 が実行時アーキ正準）
ENVIRONMENT.md          開発環境＋GCP資源の正式記録
agentforge_*.md / self_evolving_*.md / hackathon_*.md  仕様・要綱・公式記録
HANDOFF.md              このファイル
```

> frontend/ は未作成（Phase 1 で React+Vite を追加予定）。

---

## 6. 次にやること（再開時のTODO）

実装は Phase 制（[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) §4 / docs「実装フェーズ」）。

1. **GitHub→Cloud Build の正式CI/CD**を設定（push で Cloud Run 自動デプロイ）。本リポジトリ（airpocket-soundman/AgentForge）を使う。
2. **Phase 1**: frontend（React+Vite, Firebase Hosting）＋ Firebase Auth ＋ reception モジュール（チャット即応・Firestore保存）。
3. **Phase 2**: Orchestrator（ADK+Gemini）で作業計画JSON → Control Plane registry 登録（ここで必須要件＝Cloud Run＋Gemini を満たす）。
4. サービスアカウント分離＋IAM、Gemini APIキーを Secret Manager 登録、Firebase 初期化。
5. Phase 3〜7（Worker/Cloud Tasks/生成UI manifest → 承認→active→Task API → Rollback/Audit → CI/CD仕上げ → 提出物）。

### 役割分担
- **人間（ユーザー）**: GCP/Firebaseコンソール操作・課金、認証同意、GitHub操作、デモ動画/ProtoPedia提出。
- **Claude**: それ以外の実装すべて（コード・Dockerfile・CI/CD・gcloudコマンドの用意）。

### 注意（秘密情報）
- Gemini APIキー等はチャットに貼らない。**Secret Manager** に登録して使う。`.gitignore` は `*-key.json` / `service-account*.json` / `.env` を除外済み。
