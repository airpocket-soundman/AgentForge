# 開発環境 正式記録（AgentForge）

> 別PCでも同一環境を再現できるよう、開発環境はすべてこのリポジトリに**コードとして記録**する。
> 本番（Cloud Run）はコンテナ実行のため、開発もコンテナ（Dev Container）に統一して parity を担保する。
> 最終更新: 2026-06-08

---

## 1. 確定方針

- **本番ランタイム**: Docker コンテナ on Cloud Run（`backend/Dockerfile` が真実の定義）
- **開発環境**: **Dev Container（Docker）** — `.devcontainer/` で宣言。別PCでも同一再現
- **バージョンはすべてピン留め**し、このファイル＋設定ファイルで管理

## 2. 別PCでの再現手順（これだけ）

1. そのPCに **Docker Desktop** をインストール（Windowsは WSL2 バックエンド有効化。要管理者権限・1回のみ）
2. `git clone <このリポジトリ>`
3. VS Code で開き **「Reopen in Container」**（Dev Containers拡張）を実行
   - 初回は自動で Python/Node/gcloud/firebase と依存を構築（`.devcontainer/postCreate.sh`）
4. 完了。`backend/.venv` と `frontend/node_modules` はコンテナ内に自動構築される

> Dev Container を使わない「ネイティブ再現」も可能（§5 フォールバック参照）。

## 3. 採用バージョン（ピン留め）

| ツール | バージョン | 定義場所 |
|---|---|---|
| Python | 3.12.x（基準 3.12.7） | `.devcontainer` ベースイメージ / `backend/Dockerfile` |
| Node.js | 24.x（基準 24.11.1） | `.nvmrc` / devcontainer feature |
| npm | 11.x（基準 11.6.2） | Nodeに同梱 |
| git | 2.51.x | devcontainer ベースイメージ |
| Google Cloud CLI (gcloud) | latest（コンテナ内に導入） | devcontainer feature |
| firebase-tools | latest（npm global） | `.devcontainer/postCreate.sh` |
| Python依存 | `backend/requirements.txt` でピン | 同ファイル |
| フロント依存 | `frontend/package-lock.json` でピン | Phase 1で作成 |

## 4. ホストPC実測（参考・2026-06-08 / Windows 11 26200）

このPC（初期開発機）で検出した状態。Dev Container 採用後はコンテナ内が正となる。

| ツール | ホスト実測 |
|---|---|
| node / npm | v24.11.1 / 11.6.2（あり） |
| git | 2.51.2.windows.1（あり） |
| python | 3.12.7（本記録時にユーザースコープで導入） |
| gcloud | ホスト未導入（コンテナ内で利用） |
| firebase | npm global で導入済み |
| docker | ホスト未導入（Dev Container利用には Docker Desktop が必要） |

> 注: ホストのPython/firebaseはフォールバック用。標準作業は Dev Container 内で行う。

## 5. フォールバック：Dockerを使わないネイティブ再現

Docker を使えないPCでも、以下のピン版を入れれば再現可能（parity はDockerに劣る）。

1. Python 3.12.7（user scope）/ Node 24.x / git をインストール
2. `cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
3. `cd frontend && npm ci`
4. gcloud は **Cloud Shell（ブラウザ）** で代替可

## 6. クラウド側の環境（記録）

| 項目 | 値 |
|---|---|
| GCP プロジェクトID | `agentforge-498808`（永続・変更不可） |
| GCP プロジェクト番号 | `217469091476` |
| リージョン | asia-northeast1（東京） |
| デプロイ | GitHub → Cloud Build → Cloud Run / Firebase Hosting |
| シークレット | Secret Manager（Gemini APIキー 等） |

### 作成済みリソース（Phase 0 / 2026-06-08）

- API有効化：run / cloudbuild / artifactregistry / firestore / cloudtasks / secretmanager / storage / aiplatform / generativelanguage / firebase / iam
- Firestore：Native mode・asia-northeast1（`(default)`・無料枠）
- Cloud Storage バケット：`agentforge-498808-artifacts` / `-uploads` / `-snapshots` / `-build-source`
- Artifact Registry：`agentforge`（docker・asia-northeast1）
- Cloud Tasks キュー：`worker-queue`（asia-northeast1）
- 課金：有効（無料トライアル／無料枠）

> サービスアカウント名・Cloud Run サービス URL・Secret 名は、作成しだいこの節へ追記する。
