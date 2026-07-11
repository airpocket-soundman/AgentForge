# AgentForge / 育てるアプリ

**AgentForge** は、初心者でも安全にアプリを作れるようにするアプリ生成パイプライン / フレームワークです。
Orchestrator を中心に、Receptor、Tester、Reviewer、Specialist Worker、Safety Harness、Agent Harness、
Control Plane を組み合わせ、自然言語の依頼を設計→実装→検証→レビュー→プレビュー→承認公開へ流します。

**育てるアプリ** は、この AgentForge framework を使ったユーザー向けプロダクトです。
メインチャットや各アプリの専門ワーカーと会話しながら、デフォルトアプリを直したり、新しいミニアプリを作ったりして、
自分用に育てていく体験を提供します。

実装上も境界を分けています。バックエンドのプロダクト定義は `backend/app/product.py`、フロントの表示定義は
`frontend/src/product.ts` が入口です。AgentForge のパイプライン本体はプロダクト名を参照せず、プロダクト側が
表示名、タイトル画像、タグライン、デフォルトアプリ構成を選びます。

DevOps × AI Agent Hackathon 2026 提出作品（提出締切 **2026-07-10**）。

- 目的・全体像: [VISION.md](VISION.md), [HANDOFF.md](HANDOFF.md)
- 生きた仕様（正準）: [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
- 進捗: [PROGRESS.md](PROGRESS.md)
- 開発環境の正式記録: [ENVIRONMENT.md](ENVIRONMENT.md)
- 説明サイト（図解）: `docs/index.html` をブラウザで開く

---

## クイックスタート（ローカル Docker 開発環境）

Docker Desktop さえあれば、GCP 認証なしで全スタックがローカルで動きます（Firestore はエミュレータ）。

```bash
docker compose -f docker-compose.dev.yml up --build
```

起動するもの:

| サービス | URL | 内容 |
|---|---|---|
| frontend | http://localhost:5173 | React + Vite チャットUI（HMR） |
| backend  | http://localhost:8000 | FastAPI core API（hot reload） |
| firestore | localhost:8081 | Firestore エミュレータ |

動作確認:

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"agentforge-core-api"}

# ブラウザ http://localhost:5173 を開き「タスク管理を追加して」と送信
```

停止: `docker compose -f docker-compose.dev.yml down`

> backend のホストポートが 8000 なのは、ホストの 8080 を WSL relay が使用していたため。
> コンテナ内部は 8080 のままで、frontend の `/api` プロキシはコンテナ間通信なので影響なし。

### 認証込みローカルデモ

本番と同じ Google ログイン、許可リスト、名前付きゲスト個別環境をローカルで確認する場合は overlay を重ねます。
Firestore は引き続きローカルエミュレータを使います。

```bash
# 事前に frontend/.env.local に Firebase Web app config を設定
docker compose -f docker-compose.dev.yml -f docker-compose.demo.yml up --build
```

- ユーザー画面: http://localhost:5173
- 管理画面: http://localhost:5174/admin.html
- `airpocket.soundman@gmail.com` は管理者/通常ユーザーとして入れます。
- ゲストアクセスが ON のときは、Google アカウント不要で任意のユーザー名から `guest_<id>` の個別環境に入れます。同じユーザー名なら同じゲスト環境を再開します。

### Dev Container（同一ツール環境）
VS Code の「Reopen in Container」（`.devcontainer/`）で Python 3.12 / Node 24 / gcloud / firebase を揃えた開発シェルに入れます。上の compose はアプリ実行用、Dev Container はツール環境用で役割が異なります。

---

## テスト

```bash
# backend（PowerShell / host python）
$env:PYTHONPATH='backend'; python -m pytest backend/tests -q

# backend（Docker Compose dev イメージ内）
docker compose -f docker-compose.dev.yml run --rm --no-deps backend python -m pytest /app/tests -q

# frontend 型チェック＋ビルド
cd frontend && npm run build
```

---

## リポジトリ構成

```
backend/        FastAPI core API（modular monolith）
  app/
    main.py         app factory（health + ルータ束ね）
    product.py      Product profile（表示情報・デフォルトアプリ束）
    config.py       環境変数ベース設定
    firestore.py    Firestore クライアント（emulator 対応）
    agents/         組み込みAIワーカーの基本指示（*.md・リポジトリ管理）＋ローダー
                    policy.md / orchestrator.md / reception.md / ui_designer.md / feature_worker.md
                    → 実行時に読み込みプロンプトへ注入（プロンプト＝設定）
    llm/            Gemini クライアント（モデルルーティング＋スタブfallback）
    models/         Pydantic モデル
    reception/      Phase 1: チャット即応モジュール
    orchestrator/   Phase 2: 要求→作業計画JSON生成
    control_plane/  Phase 2/4/5: registry（pending登録）＋承認/active化/rollback＋audit
    generated_app/  Phase 4: 生成機能の実体（Task API の決定的CRUD）
  tests/        pytest
  Dockerfile        本番（Cloud Run）
  Dockerfile.dev    ローカル開発（reload）
frontend/       React + Vite + TypeScript（Firebase Hosting 配信予定）
  src/product.ts    Product shell の表示設定（VITE_PRODUCT_* で上書き可能）
.devcontainer/  Dev Container 定義
docs/           説明サイト（SVG 図解）
docker-compose.dev.yml   ローカル開発スタック
```
