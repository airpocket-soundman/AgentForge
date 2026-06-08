# AgentForge Hackathon Edition 仕様書

作成日: 2026-06-08  
対象コンテスト: DevOps × AI Agent Hackathon 2026  
提出テーマ: **AgentForge: スーパーアプリを自己拡張させる DevOps AI Agent Workbench**

---

## 0. この仕様書の位置づけ

本仕様書は、汎用構想「自己拡張型スーパーアプリ基盤」を、DevOps × AI Agent Hackathon 2026 に提出可能な **Google Cloud / Gemini 中心のコンテスト提出版**として再設計したものである。

本版では、以下を明確にする。

- コンテストで提出するMVP範囲
- どの機能をどのGoogle Cloudサービスに載せるか
- 具体的なデプロイ構成
- Google Cloudサービス仕様との整合性
- コンテスト後に解放する拡張余地

重要な方針は、以下である。

> 本コンテスト版では、AIモデルは Gemini / Google Cloud AI 技術を中心に構成する。  
> 他社AI APIキー、BYOK、BYOM、BYOLLM、自作ローカルLLM接続は、Googleサービス活用の主題がぼけるためコンテスト後ロードマップに回す。

---

## 1. 提出コンセプト

### 1.1 一文説明

**AgentForge は、一般ユーザーが自然言語でスーパーアプリを育てられるようにし、その裏側でAIエージェントがAPI設計、UI設計、実装、テスト、デプロイ、監査ログ、巻き戻しまでを行う DevOps AI Agent Workbench である。**

### 1.2 コンテスト向けの主張

本作品は、完成済みのスーパーアプリではない。

提出物の本体は、以下である。

> 最小のチャット窓口から、AIエージェントがアプリを自己拡張するDevOps基盤

スーパーアプリは、この基盤の能力を見せるためのデモ題材である。

つまり、評価してほしい対象は、次の「生成された機能」単体ではない。

- タスク管理
- フィード
- PDFメモ
- 画像アップロード
- SNS風UI

評価してほしいのは、次のプロセスである。

```text
チャットだけの最小アプリ
↓
ユーザーが自然言語で要求
↓
受付係が即応
↓
オーケストレーターが作業計画を作成
↓
UIデザイナー / プログラマー / DevOpsワーカーへ委任
↓
テスト・ビルド・デプロイ
↓
Cloud Run上のアプリに機能が追加
↓
Audit Log / Rollback により戻せる
```

### 1.3 DevOpsの民主化

通常、DevOpsはエンジニアが行う。

```text
要件整理
コード実装
API設計
UI実装
テスト
ビルド
デプロイ
ログ監視
修正
Rollback
```

AgentForgeでは、一般ユーザーが自然言語で「作りたい」「変えたい」「戻したい」と伝えるだけで、裏側のAIエージェント群がこのDevOpsサイクルを回す。

これを本作品では **DevOpsの民主化** と定義する。

---

## 2. コンテスト提出版MVP

### 2.1 MVPの定義

本MVPは、多機能アプリの完成版ではない。

**MVP = Core Agent Layer が動き、自己拡張サイクルを1回以上完了できること**

MVPに含めるもの:

- Chat UI
- Reception Agent
- Orchestrator Agent
- Task State DB
- Context DB
- API Catalog
- Worker Registry
- Tool / API Gateway
- Programmer Agent
- UI Designer Agent
- DevOps Agent
- Test Agent
- Rollback Service
- Audit Log
- Cloud Runへの反映フロー

MVPに含めないもの:

- 本格課金
- 本格Marketplace
- 本格SNSネットワーク
- BYOK / BYOLLM
- 他社AI API対応
- 自作ローカルLLM接続
- OS連携
- マイコン実機書き込み

### 2.2 デモで生成する機能

MVP上で実際に生成・追加するデモ機能は以下とする。

#### Demo Feature 1: タスク管理

ユーザー指示:

```text
タスク管理機能を追加して。タスクの追加、一覧表示、完了切替ができるようにして。
```

生成されるもの:

- Task API
- Firestore `tasks` コレクション
- Task UI
- 変更履歴
- Rollback checkpoint

#### Demo Feature 2: プロジェクトフィード

ユーザー指示:

```text
タスクとメモをまとめて見られるフィードを追加して。時系列順と重要度順を切り替えたい。
```

生成されるもの:

- Feed View
- Feed Source API
- Ranking policy
- 情報オブジェクト表示UI

#### Demo Feature 3: PDFメモ / ファイル登録

ユーザー指示:

```text
PDFをアップロードして、要約と重要ポイントをフィードに流せるようにして。
```

生成されるもの:

- File upload UI
- Cloud Storage保存
- Gemini要約ワーカー
- Summary object
- Feed連携

---

## 3. 全体アーキテクチャ

```text
User
 ↓
Firebase Hosting / Web App
 ↓
Reception Agent API on Cloud Run
 ↓
Orchestrator Agent on Cloud Run / ADK
 ↓
Cloud Tasks
 ↓
Worker Services on Cloud Run
 ├─ UI Designer Agent
 ├─ API Designer Agent
 ├─ Programmer Agent
 ├─ Test Agent
 ├─ DevOps Agent
 ├─ Review Agent
 └─ Indexing / Summary Worker
 ↓
Tool / API Gateway on Cloud Run
 ↓
Google Cloud Services
 ├─ Firestore Native mode
 ├─ Firestore Vector Search
 ├─ Cloud Storage
 ├─ Cloud Build
 ├─ Artifact Registry
 ├─ Cloud Run
 ├─ Cloud Logging
 ├─ Secret Manager
 └─ Firebase Authentication
```

---

## 4. レイヤ構造

### 4.1 Core Agent Layer

自己拡張能力そのものを担う中核。

| 機能 | 役割 |
|---|---|
| Chat UI | ユーザーの自然言語入力 |
| Reception Agent | 常時応答、進捗説明、中止・変更受付 |
| Orchestrator Agent | 要求理解、作業計画、API要否判断、ワーカー選定 |
| Task State DB | 実行中タスクの状態保持 |
| Context DB | 文脈、判断ログ、ユーザー設定、プロジェクト状態 |
| API Catalog | 既存API・生成APIの検索 |
| Worker Registry | 利用可能ワーカー定義 |
| Tool / API Gateway | 副作用操作の安全な実行 |
| Rollback Service | 変更前状態への復旧 |
| Audit Log | 操作履歴と説明責任 |

### 4.2 Generated App Layer

Core Agent Layerが生成するアプリ機能。

| 機能 | ハッカソンMVPでの扱い |
|---|---|
| タスク管理 | デモ対象 |
| プロジェクトフィード | デモ対象 |
| PDFメモ | デモ対象 |
| 画像アップロード | 余裕があればデモ対象 |
| SNS風UI | Social Data Layerの上に生成されるUIとして扱う |

### 4.3 External Capability Layer

外部サーバや共有基盤が必要な機能。ハッカソン版では最小化する。

| 外部機能 | ハッカソン版 | 将来版 |
|---|---|---|
| Social Data Layer | Firestoreで簡易実装 | 本格SNS基盤へ拡張 |
| Notification Service | Cloud Logging / UI通知中心 | Firebase Cloud Messaging / メール / Slack等 |
| File Storage | Cloud Storage | 継続 |
| Search / Index | Firestore Vector Search | Vertex AI Vector Search併用 |
| Public API / Webhook | 原則対象外 | External Gateway化 |
| Device / IoT Gateway | 対象外 | 将来対応 |
| Plugin / Connector | 対象外 | 将来対応 |

### 4.4 Management / Billing Layer

サービス運営用の管理・課金・ユーザー制限機能。ハッカソン版ではダミー実装。

| 機能 | ハッカソン版 |
|---|---|
| 認証 | Firebase Authentication |
| ユーザー管理 | Firestore `users` |
| プラン | Free / Pro dummy |
| 使用量 | Worker run count / token estimate / storage estimate |
| 課金 | 実決済なし |
| BYOK / BYOLLM | コンテスト後 |
| Marketplace決済 | コンテスト後 |

---

## 5. Google Cloudサービス対応表

| システム機能 | 採用Googleサービス | 理由 |
|---|---|---|
| Frontend / Chat UI | Firebase Hosting | SPA/PWAの静的配信、プレビュー、Rollbackと相性がよい |
| 認証 | Firebase Authentication | Webアプリ向け認証、Googleログイン、匿名ログインから開始可能 |
| Reception Agent API | Cloud Run | HTTP APIとして常時即応。未使用時はスケールゼロ可能 |
| Orchestrator Agent | Cloud Run + ADK + Gemini API | ADKでエージェント構成、Geminiで判断、Cloud RunでAPI化 |
| Agent Framework | Google ADK | マルチエージェント・ツール呼び出し・Google Cloudデプロイの文脈に合う |
| LLM推論 | Gemini API / Vertex AI Gemini | Google Cloud AI技術の必須要件に合う |
| Function calling | Gemini function calling | Tool Gateway呼び出しに使う |
| Structured output | Gemini structured output | 作業計画、ワーカー定義、API仕様、UI仕様をJSON化 |
| Task Queue | Cloud Tasks | 非同期作業、リトライ、レート制御、受付応答の高速化 |
| Worker実行 | Cloud Run services | Cloud TasksのHTTP targetとして実行。未使用時はスケールゼロ |
| Batch / cleanup | Cloud Run Jobs | インデックス再構築、クリーンアップなど完了型処理 |
| Context DB | Firestore Native mode | ユーザー/プロジェクト/タスク状態の保存 |
| Vector Search | Firestore Vector Search | APIカタログ、過去タスク、Context検索 |
| Embeddings | Vertex AI Text Embeddings API | Context DBやSNSデータのベクトル化 |
| File / Snapshot | Cloud Storage | 非構造化ファイル、生成物、Rollback snapshot保存 |
| Container image | Artifact Registry | Cloud Run用コンテナイメージ管理 |
| CI/CD | Cloud Build | テスト、コンテナビルド、Artifact Registry保存、Cloud Runデプロイ |
| Logs / Audit補助 | Cloud Logging | Cloud Run / Cloud Build / アプリログの収集・分析 |
| Secrets | Secret Manager | GitHub token等のシークレット管理。Gemini利用は原則IAM経由 |
| IAM | Google Cloud IAM | サービスアカウントごとの最小権限 |

---

## 6. デプロイ対象サービス一覧

### 6.1 Firebase Hosting

| 項目 | 内容 |
|---|---|
| Name | `agentforge-web` |
| 役割 | Chat UI、生成UI表示、進捗画面 |
| 技術 | React / Vite または Next.js static export |
| 接続先 | Cloud Run `reception-api`, `generated-app-api` |
| 備考 | SSRが必要ならCloud Runへ移行可能 |

### 6.2 Cloud Run Services

#### `reception-api`

| 項目 | 内容 |
|---|---|
| 役割 | ユーザー応答、進捗説明、追加指示受付 |
| 起動 | HTTP request |
| 重要性 | 作業中でもユーザー対応を止めないため最重要 |
| 参照DB | Firestore `task_runs`, `worker_runs`, `audit_logs` |
| AI利用 | 軽量Gemini。進捗説明はテンプレート中心でも可 |

#### `orchestrator-api`

| 項目 | 内容 |
|---|---|
| 役割 | 要求理解、作業計画、API要否判断、ワーカー選定 |
| 技術 | ADK + Gemini API |
| 出力 | `work_plan`, `worker_tasks`, `approval_requests` |
| 書込 | Firestore `task_runs`, `work_plans` |
| 非同期化 | Cloud Tasksへタスク投入 |

#### `tool-gateway-api`

| 項目 | 内容 |
|---|---|
| 役割 | Firestore / Cloud Storage / Cloud Build / Cloud Run操作の安全な実行 |
| 特徴 | エージェントに直接強権限を渡さない |
| 必須機能 | 権限確認、使用量確認、監査ログ、承認ゲート |

#### `worker-runner-api`

| 項目 | 内容 |
|---|---|
| 役割 | Cloud Tasksから呼ばれる汎用ワーカー実行口 |
| 処理 | worker_typeに応じてADK workerを起動 |
| Worker例 | UI Designer, Programmer, Test, DevOps, Review, Summary |
| 注意 | Cloud Tasksはat-least-once deliveryなので冪等性が必要 |

#### `generated-app-api`

| 項目 | 内容 |
|---|---|
| 役割 | 生成されたサブシステムAPIを提供 |
| MVP | task API, feed API, file summary API |
| 実装方式 | Extension manifest + generated route modules |
| デプロイ | Cloud Build経由でCloud Runに反映 |

#### `rollback-api`

| 項目 | 内容 |
|---|---|
| 役割 | checkpoint作成、snapshot復旧、Cloud Run revision復旧支援 |
| 権限 | LLM/ワーカーから直接操作不可。ユーザー承認または固定APIのみ |
| 保存先 | Cloud Storage `agentforge-snapshots` |

#### `management-api`

| 項目 | 内容 |
|---|---|
| 役割 | ユーザー、プラン、使用量、実行可否チェック |
| MVP | Dummy Free / Pro、使用量カウンタ |
| 将来 | 課金、BYOK、Marketplace精算 |

#### `social-data-api`

| 項目 | 内容 |
|---|---|
| 役割 | 投稿・メモ・タスク・PDF要約等のSocialObject保存/検索 |
| MVP | 単一ユーザー/プロジェクト内フィード中心 |
| 責務 | UIや推薦思想は持たない。データ保存・検索・権限のみ |

### 6.3 Cloud Run Jobs

| Job | 役割 | 実行タイミング |
|---|---|---|
| `index-rebuild-job` | Firestore Vector Search用embedding再生成 | 手動 / スケジュール |
| `cleanup-preview-job` | 古いpreview成果物削除 | 手動 / スケジュール |
| `snapshot-export-job` | Firestore/Storageメタデータのcheckpoint整備 | 変更前 / 手動 |

MVPではCloud Run Jobsを必須化せず、Cloud Run services + Cloud Tasks中心で実装してよい。長時間・完了型・ユーザー待機不要の処理だけJobsへ逃がす。

---

## 7. Firestore設計

Firestore Native mode を採用する。

### 7.1 主要コレクション

```text
users/{userId}
projects/{projectId}
sessions/{sessionId}
task_runs/{taskId}
worker_runs/{workerRunId}
work_plans/{planId}
api_catalog/{apiId}
worker_registry/{workerId}
context_chunks/{chunkId}
artifacts/{artifactId}
checkpoints/{checkpointId}
audit_logs/{logId}
social_objects/{objectId}
usage_counters/{counterId}
approval_requests/{approvalId}
```

### 7.2 `task_runs`

```json
{
  "task_id": "task_001",
  "user_id": "u_001",
  "project_id": "p_001",
  "status": "running",
  "current_step": "ui_design",
  "progress_message": "UIデザイナーがタスク管理画面を設計中です",
  "created_at": "2026-06-08T00:00:00Z",
  "updated_at": "2026-06-08T00:05:00Z",
  "cancel_requested": false,
  "approval_required": false,
  "checkpoint_id": "cp_001"
}
```

### 7.3 `worker_runs`

```json
{
  "worker_run_id": "wr_001",
  "task_id": "task_001",
  "worker_type": "ui_designer",
  "model": "gemini-flash-or-pro",
  "status": "completed",
  "input_context_refs": ["context:project:summary"],
  "output_refs": ["artifact:ui_spec_001"],
  "token_estimate": 3200,
  "summary": "タスク一覧・追加フォーム・完了切替を持つUI案を作成"
}
```

### 7.4 `api_catalog`

```json
{
  "api_id": "task_api_v1",
  "name": "Task API",
  "path": "/api/tasks",
  "method": "GET/POST/PATCH",
  "input_schema": {},
  "output_schema": {},
  "side_effect_level": "medium",
  "owner_layer": "generated_app",
  "created_by_task": "task_001",
  "embedding": "vector"
}
```

### 7.5 `social_objects`

```json
{
  "object_id": "so_001",
  "type": "task|memo|pdf_summary|image|post",
  "owner_user_id": "u_001",
  "project_id": "p_001",
  "title": "タスク管理機能の実装",
  "body": "...",
  "tags": ["devops", "task"],
  "visibility": "private|project|public",
  "embedding": "vector",
  "created_at": "..."
}
```

---

## 8. Cloud Storage設計

### 8.1 Buckets

| Bucket | 用途 |
|---|---|
| `agentforge-uploads` | PDF、画像、ユーザーアップロード |
| `agentforge-artifacts` | UI仕様、API仕様、生成コードbundle、レポート |
| `agentforge-snapshots` | Rollback用checkpoint |
| `agentforge-build-source` | Cloud Buildへ渡すsource archive |

### 8.2 Rollback向け設定

`agentforge-snapshots` は、以下を推奨する。

- Object Versioning有効化
- Lifecycle ruleで古いcheckpointを整理
- LLM/workerサービスアカウントから削除権限を外す
- `rollback-api` のみ復旧操作権限を持つ

---

## 9. Cloud Tasks設計

### 9.1 Queues

| Queue | Target | 用途 |
|---|---|---|
| `orchestrator-queue` | `orchestrator-api` | 非同期計画生成 |
| `worker-queue` | `worker-runner-api` | UI/Programmer/Test等 |
| `devops-queue` | `worker-runner-api` | Build/Deploy/Log解析 |
| `index-queue` | `worker-runner-api` | embedding生成、検索index更新 |
| `notification-queue` | `reception-api` | 完了・承認待ち通知 |

### 9.2 注意点

Cloud Tasks は非同期処理向けであり、ユーザーが結果を待つ対話処理そのものには使わない。

したがって、ユーザー応答は `reception-api` が即時返し、長時間作業はTask State DBを通じて進捗確認する。

---

## 10. Cloud Build / Artifact Registry / Cloud Run反映フロー

### 10.1 生成機能反映の流れ

```text
Programmer Agent
↓
生成コードbundleをCloud Storageへ保存
↓
Tool GatewayがCloud Buildを起動
↓
Cloud Build:
  1. source取得
  2. unit test
  3. lint / schema validation
  4. container build
  5. Artifact Registryへpush
  6. Cloud Run preview serviceへdeploy
↓
Review Agent / Test Agentが確認
↓
ユーザー承認
↓
Cloud Run active serviceへtraffic切替または新revision deploy
```

### 10.2 Artifact Registry

| Repository | 用途 |
|---|---|
| `agentforge-core` | Core services images |
| `agentforge-generated` | Generated app images |
| `agentforge-workers` | Worker images |

### 10.3 Build approvals

ハッカソンMVPでは、承認はアプリ内の `approval_requests` で表現する。Cloud Buildの承認機能は将来検討とする。

---

## 11. Agent設計

### 11.1 Reception Agent

責務:

- ユーザー応答
- 進捗説明
- 中止/変更受付
- 承認確認
- 現在の作業状態の要約

使用モデル:

- Gemini Flash系を想定
- 進捗説明はテンプレート + 必要時LLM

### 11.2 Orchestrator Agent

責務:

- ユーザー要求の意図理解
- API作成可否判断
- UI設計要否判断
- 既存API / Worker Registry検索
- 作業計画生成
- 専門ワーカーへの委任
- 結果統合

重要:

> オーケストレーターはAPIやUIを直接実装しない。  
> 実装はProgrammer Agent、UI設計はUI Designer Agentへ委任する。

### 11.3 UI Designer Agent

責務:

- 画面構成
- 情報設計
- 導線設計
- コンポーネント仕様
- モバイル/デスクトップ方針

出力:

- `ui_spec.json`
- `view_manifest.json`

### 11.4 Programmer Agent

責務:

- API実装
- UI実装
- Firestoreスキーマ利用
- Cloud Run用コード生成
- テスト作成

出力:

- source bundle
- route definitions
- test files
- build manifest

### 11.5 DevOps Agent

責務:

- Cloud Build起動
- Build log要約
- Cloud Run deploy plan作成
- Cloud Logging参照
- Rollback候補提示

重要:

> DevOps Agentも本番反映は直接行わず、Tool Gatewayと承認ゲートを通す。

### 11.6 Review / Safety Agent

責務:

- 生成差分の危険度評価
- 外部送信の有無確認
- Firestore / Storage権限確認
- シークレット参照検査
- Rollback可能性確認

---

## 12. Tool / API Gateway

Tool Gatewayは、エージェントがGoogle Cloudリソースを直接操作しないための固定レイヤである。

### 12.1 提供ツール

| Tool | 実体 | 制御 |
|---|---|---|
| `read_context` | Firestore read | user/project scope |
| `write_context` | Firestore write | audit必須 |
| `create_checkpoint` | Cloud Storage snapshot | rollback-apiのみ |
| `save_artifact` | Cloud Storage write | artifact bucketのみ |
| `start_build` | Cloud Build | approval / quota確認 |
| `deploy_preview` | Cloud Run | previewのみ自動可 |
| `promote_revision` | Cloud Run | ユーザー承認必須 |
| `read_logs` | Cloud Logging | project scope制限 |
| `create_task` | Cloud Tasks | queue制限 |
| `update_api_catalog` | Firestore write | schema validation必須 |

### 12.2 禁止する直接操作

- Secret Manager直接読み取り
- 課金情報変更
- IAM変更
- snapshot削除
- 他ユーザーデータ参照
- 承認なし本番反映
- 外部公開API作成

---

## 13. IAM / サービスアカウント設計

| Service Account | 用途 | 主な権限 |
|---|---|---|
| `sa-reception` | reception-api | Firestore read/write限定, Cloud Logging write |
| `sa-orchestrator` | orchestrator-api | Firestore read/write, Cloud Tasks enqueue, Vertex AI user |
| `sa-worker` | worker-runner-api | Firestore read/write, Cloud Storage artifact write, Vertex AI user |
| `sa-tool-gateway` | Tool Gateway | Cloud Build起動, Cloud Run deploy preview, Storage限定操作 |
| `sa-devops` | DevOps worker | Cloud Build viewer, Cloud Logging viewer, Artifact Registry reader |
| `sa-rollback` | rollback-api | snapshot bucket read/write, Cloud Run revision read/deploy操作 |
| `sa-build` | Cloud Build | Artifact Registry writer, Cloud Run deployer, Storage read |

最小権限を原則とし、ワーカーには広域管理権限を渡さない。

---

## 14. デプロイ手順

### 14.1 初期セットアップ

1. Google Cloud Project作成
2. Billing有効化
3. Region決定: `asia-northeast1` を基本候補
4. 必要API有効化
   - Cloud Run
   - Cloud Build
   - Artifact Registry
   - Firestore
   - Cloud Tasks
   - Cloud Storage
   - Vertex AI / Gemini API
   - Secret Manager
   - Cloud Logging
   - Firebase Authentication / Hosting

### 14.2 基盤リソース作成

1. Firestore Native mode 作成
2. Storage buckets作成
3. Artifact Registry repositories作成
4. Cloud Tasks queues作成
5. Service accounts作成
6. IAM付与
7. Firebase project連携
8. Firebase Authentication有効化

### 14.3 Core services deploy

1. `reception-api` container build
2. `orchestrator-api` container build
3. `tool-gateway-api` container build
4. `worker-runner-api` container build
5. `rollback-api` container build
6. `management-api` container build
7. Artifact Registry push
8. Cloud Run deploy

### 14.4 Frontend deploy

1. Firebase Hosting初期化
2. API endpoint設定
3. Auth設定
4. `firebase deploy --only hosting`

### 14.5 Generated app deploy

1. 初期 `generated-app-api` をCloud Runへdeploy
2. 初期API catalog登録
3. 初期Social Data Layer登録

### 14.6 CI/CD

1. Cloud Build config作成
2. GitHubまたはCloud Source相当のsource接続
3. Core services用trigger
4. generated app用manual build endpoint
5. preview deploy route
6. promotion approval flow

---

## 15. ハッカソン版デモシナリオ

### 15.1 Demo 0: 初期状態

- ログイン
- チャットだけの最小UI
- 機能一覧は空
- API Catalogにはcore APIのみ

### 15.2 Demo 1: タスク管理生成

ユーザー:

```text
タスク管理機能を追加して
```

表示:

```text
作業計画を作成しました。
1. UI Designer Agent: 画面構成
2. Programmer Agent: Task API / UI実装
3. Test Agent: 基本テスト
4. DevOps Agent: preview deploy
5. 承認後に反映
```

完了後:

- `/tasks` UI追加
- Task API有効化
- Firestore tasks保存
- Audit Log記録
- Rollback checkpoint作成

### 15.3 Demo 2: 進捗確認

作業中にユーザー:

```text
進捗どうですか？
```

Reception Agent:

```text
現在はProgrammer AgentがTask APIを生成済みで、UI実装のテスト中です。
次の工程はCloud Buildによるpreview deployです。
```

### 15.4 Demo 3: フィード生成

ユーザー:

```text
タスクとメモをまとめて見られるフィードを追加して
```

結果:

- SocialObject利用
- Feed UI生成
- 時系列/重要度切替
- Experience Layerとして実装

### 15.5 Demo 4: Rollback

ユーザー:

```text
直前のフィード追加を戻して
```

結果:

- checkpoint選択
- Cloud Run previous revisionまたは前imageへ戻す
- Firestore metadata復旧
- UIからフィード機能が消える
- Audit Logに復旧操作が残る

---

## 16. コンテスト後ロードマップ

### Phase 1: ハッカソン版

- Google Cloud / Gemini中心
- Cloud Run / Firebase / Firestore / Cloud Tasks / Cloud Build
- 最小Marketplaceなし
- 課金なし

### Phase 2: Model Gateway抽象化

- Gemini以外を扱える内部抽象化だけ導入
- ただしサービス提供モデルはまだGemini中心

### Phase 3: BYOK / 他社AI API

- ユーザーのAI API契約を接続
- 無料AI枠は付与しない
- 基盤利用料は課金対象

### Phase 4: BYOLLM / ローカルLLM

- Ollama / llama.cpp / LM Studio / vLLM等
- Local BridgeまたはVPN接続
- 機密データ向け

### Phase 5: Marketplace

- サブシステム販売
- 権限表示
- Safety Review
- 手数料モデル

### Phase 6: Device / IoT Gateway

- MQTT
- Raspberry Pi
- M5Stack
- STM32 / FRDM-MCXN947
- ファーム生成・ビルド・書き込み承認

---

## 17. Googleサービス適合性監査

本節は、仕様作成後にGoogle公式ドキュメントに照らして再監査した結果である。

### 17.1 ハッカソン要件適合

| 要件 | 本仕様の対応 | 判定 |
|---|---|---|
| Google Cloudアプリケーション実行プロダクト利用 | Cloud Run / Firebase Hosting / Cloud Run Jobs | 適合 |
| Google Cloud AI技術利用 | Gemini API / Vertex AI Gemini / ADK | 適合 |
| DevOpsプロセス | Cloud Build / Artifact Registry / Cloud Run deploy / Cloud Logging / Rollback | 適合 |
| AIエージェントが価値の中心 | Orchestrator + Worker agents | 適合 |
| 実運用への配慮 | IAM, Secret Manager, Audit Log, Rollback, Cloud Tasks | 適合 |

### 17.2 Cloud Run

計画:

- Reception API
- Orchestrator API
- Tool Gateway
- Worker Runner
- Generated App API
- Rollback API

監査:

- Cloud Runはコンテナ/関数/コードをGoogleのスケーラブルインフラ上で動かすフルマネージド基盤である。
- Web/API/マイクロサービスに適している。
- 未使用時のスケールゼロが可能で、ワーカー非常駐設計に合う。

判定: **適合**

注意:

- 長時間作業はCloud Tasks timeoutやCloud Run設定に注意する。
- ユーザー応答はReception APIで即時返し、重い作業は非同期化する。

### 17.3 Cloud Run Jobs

計画:

- Index rebuild
- Snapshot export
- Cleanup

監査:

- Cloud Run Jobはリクエストを待ち受けず、タスクを実行して終了する形式である。
- 常時受付が必要なReceptionやOrchestratorには向かない。
- 完了型のバッチ処理に向く。

判定: **適合。ただし補助用途に限定**

### 17.4 Cloud Tasks

計画:

- Orchestrator / Worker / DevOps / Indexing queue

監査:

- Cloud Tasksはユーザーリクエスト外に作業を切り出し、非同期に処理するためのサービスである。
- タスクはat-least-once deliveryであるため、worker処理は冪等にする必要がある。
- 公式にも「ユーザーが結果を待つインタラクティブ用途には不適」とされるため、進捗確認はTask State DB + Reception Agentで対応する。

判定: **適合**

必須対策:

- `task_id` を冪等キーにする
- 同じtaskが再実行されても二重反映しない
- task statusをFirestoreで管理する

### 17.5 Firestore / Firestore Vector Search

計画:

- Context DB
- Task State DB
- API Catalog
- Worker Registry
- Social Data Layer
- Vector Search

監査:

- FirestoreはドキュメントDBとして、task/session/context/API catalogに適する。
- Firestore Vector SearchはKNN検索、vector保存、vector index作成に対応する。
- APIカタログ検索、類似タスク検索、Context検索に適する。

判定: **MVPでは適合**

注意:

- 大規模SNSや大規模RAGに拡大する場合は、Vertex AI Vector Search等への分離を検討する。

### 17.6 Vertex AI Gemini / Gemini API

計画:

- Orchestrator
- UI Designer
- Programmer
- Review
- Summary
- Function calling
- Structured output

監査:

- Gemini APIは生成AI処理に利用できる。
- Function callingは外部システムやAPIとやり取りする生成AIアプリに適する。
- Structured outputは作業計画やUI仕様などJSONスキーマに沿った出力に適する。

判定: **適合**

注意:

- Programmer Agentのコード生成品質はモデル選定に依存する。
- 重要な差分はReview Agentとテストで検証する。

### 17.7 ADK

計画:

- Orchestrator / Worker構成
- Tool定義
- ADK agentをCloud Runへdeploy

監査:

- ADKは信頼性のあるAIエージェントを構築、デバッグ、デプロイするためのオープンソース開発フレームワークである。
- 個人AIアシスタントから業務ワークフローまでのマルチエージェント構成に合う。
- ADK CLIによるCloud Run deployも用意されている。

判定: **適合**

注意:

- ハッカソンMVPでは、すべてのワーカーを完全なADK agentとして分離せず、worker typeごとのrole prompt + toolsetから始めてもよい。

### 17.8 Cloud Storage

計画:

- Uploads
- Generated artifacts
- Build source archive
- Rollback snapshots

監査:

- Cloud Storageは非構造化データのマネージドストレージで、必要に応じて保存・取得できる。
- Object Versioning、保持、削除復元など、Rollback設計と相性がよい。

判定: **適合**

注意:

- Snapshot bucketはLLM workerに削除権限を与えない。

### 17.9 Cloud Build / Artifact Registry

計画:

- Generated code build
- Unit test
- Container build
- Artifact Registry push
- Cloud Run deploy

監査:

- Cloud BuildはGoogle Cloud上でbuildを実行し、テスト、解析、artifact生成に使える。
- Artifact Registryはコンテナイメージやパッケージを管理できる。
- Cloud Runへのデプロイパイプラインと整合する。

判定: **適合**

注意:

- Build権限はTool Gateway / Build service accountに集約する。
- Generated codeをそのまま本番反映せず、previewと承認を挟む。

### 17.10 Firebase Authentication / Hosting

計画:

- Auth
- Chat UI hosting
- Generated UI display

監査:

- Firebase AuthenticationはWebアプリ向け認証、Googleログイン、匿名ログインに対応する。
- Firebase HostingはSPA/PWA向けの高速・安全なホスティングに適する。
- HostingはCloud Runと組み合わせて動的APIやmicroserviceを使える。

判定: **適合**

注意:

- MVPでは匿名ログインまたはGoogleログインから開始可能。
- 管理・課金を本格化する場合はIdentity Platform拡張を検討する。

### 17.11 Cloud Logging

計画:

- Worker logs
- Build logs
- Cloud Run logs
- Reception progress summary

監査:

- Cloud Loggingはログの保存、検索、分析、監視を支援するリアルタイムログ管理システムである。
- Cloud RunやCloud Buildのログ分析、エラー説明、DevOps Agentの入力に適する。

判定: **適合**

注意:

- Audit Logの原本はFirestoreにも保存し、アプリ上の説明責任を確保する。

### 17.12 Secret Manager / IAM

計画:

- GitHub token等
- 外部連携シークレット
- 将来BYOK

監査:

- Secret ManagerはAPIキー、パスワード、証明書等の機密情報保存に適する。
- IAMと組み合わせ、ワーカーへ直接シークレットを見せない設計にできる。

判定: **適合**

注意:

- GeminiをVertex AI経由で使う場合はAPIキーではなくサービスアカウント/IAM中心にする。
- BYOKはコンテスト後。

---

## 18. 監査結果による設計修正

### 修正1: Worker実行はCloud Run JobsではなくCloud Run service中心にする

理由:

- Cloud TasksのHTTP targetとして扱いやすい
- 作業進捗をHTTP handlerがFirestoreへ記録しやすい
- 未使用時はCloud Runがスケールゼロ可能

Cloud Run Jobsは、index rebuildやcleanupなど補助用途に限定する。

### 修正2: Cloud Tasksはユーザー応答には使わない

理由:

- Cloud Tasksは非同期作業向けで、ユーザーが結果を待つ対話用途には向かない。

対応:

- ユーザー応答はReception Agentが即時返す。
- 進捗確認はFirestore `task_runs` を読む。

### 修正3: SNSはFirestoreベースのSocial Data Layerに縮小

理由:

- ハッカソンMVPで本格SNSは過大。
- ただし「UIと推薦ロジックは生成できる」という建付けは見せたい。

対応:

- MVPではproject内SocialObject保存とFeed UI生成まで。
- 公開SNS、フォロー、通知、外部公開は将来対応。

### 修正4: BYOK / BYOLLMは完全にコンテスト後へ回す

理由:

- Google Cloud AI技術の活用が曖昧になる。
- コンテスト版はGemini中心に統一した方が評価軸に合う。

対応:

- Model Gateway抽象化だけ将来ロードマップとして記載。

### 修正5: 課金はdummy usage counterに限定

理由:

- 実決済はハッカソンMVPに不要。
- Management / Billing Layerの設計思想だけ示せれば十分。

対応:

- Firestore `usage_counters` にtoken estimate / worker runs / storage estimateを保存。

---

## 19. 実装チェックリスト

### Week 1: Core skeleton

- [ ] Firebase Hosting + Auth
- [ ] Chat UI
- [ ] reception-api
- [ ] Firestore schema
- [ ] task_runs / audit_logs
- [ ] orchestrator-api minimal
- [ ] Gemini API call

### Week 2: Worker / Tool Gateway

- [ ] Cloud Tasks queues
- [ ] worker-runner-api
- [ ] UI Designer Agent
- [ ] Programmer Agent
- [ ] Tool Gateway
- [ ] Cloud Storage artifacts
- [ ] API Catalog

### Week 3: DevOps pipeline

- [ ] Cloud Build config
- [ ] Artifact Registry
- [ ] generated-app-api
- [ ] preview deploy
- [ ] Cloud Logging integration
- [ ] Rollback checkpoint

### Week 4: Demo polish

- [ ] Task management generation
- [ ] Feed generation
- [ ] PDF summary flow
- [ ] Progress explanation
- [ ] Rollback demo
- [ ] Pitch deck / ProtoPedia素材

---

## 20. 主要リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 生成コードが壊れる | Programmer Agentが不完全なコードを生成 | Cloud Build, tests, preview deploy, Review Agent |
| 作業が長くユーザーが待つ | Workerが数分以上かかる | Reception Agent + Task State DB |
| 二重実行 | Cloud Tasks at-least-once delivery | idempotency key, task status lock |
| シークレット漏洩 | WorkerがSecretへアクセス | Secret Manager + Tool Gateway + IAM制限 |
| Google要件がぼける | BYOK/Local LLMを入れすぎる | コンテスト版はGemini中心 |
| SNSが大きすぎる | 本格SNSを作り込むと散る | Social Data Layer + Generated Feed UIに限定 |
| Rollbackできない変更 | 外部公開や通知は不可逆 | MVPでは外部公開を避ける。承認ゲート |

---

## 21. 参考公式資料

- DevOps × AI Agent Hackathon 2026: https://findy.notion.site/devops-ai-agent-hackathon-2026
- Cloud Run overview: https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run
- Cloud Run product page: https://cloud.google.com/run?hl=ja
- Cloud Run Jobs: https://docs.cloud.google.com/run/docs/create-jobs
- Cloud Tasks overview: https://docs.cloud.google.com/tasks/docs/dual-overview
- Firestore Vector Search: https://docs.cloud.google.com/firestore/native/docs/vector-search
- ADK: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk
- ADK Cloud Run deploy: https://google.github.io/adk-docs/deploy/cloud-run/
- Gemini function calling: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tools/function-calling?hl=ja
- Gemini structured output: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output
- Text Embeddings API: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/text-embeddings-api
- Cloud Storage: https://cloud.google.com/storage?hl=ja
- Cloud Build overview: https://docs.cloud.google.com/build/docs/overview
- Artifact Registry docs: https://docs.cloud.google.com/artifact-registry/docs
- Firebase Authentication: https://firebase.google.com/docs/auth
- Firebase Hosting: https://firebase.google.com/docs/hosting
- Cloud Logging overview: https://docs.cloud.google.com/logging/docs/overview
- Secret Manager docs: https://docs.cloud.google.com/secret-manager/docs

---

## 22. 自動整合チェック結果
仕様書作成後、主要キーワードの存在と設計方針の整合性を機械的に確認した。これは内容監査を補助するチェックであり、最終判断は17章・18章の詳細監査に従う。
| チェック項目 | 必須語 | 結果 |
|---|---|---|
| Google Cloud AI技術 | Gemini API, ADK | OK |
| Googleアプリ実行基盤 | Cloud Run, Firebase Hosting | OK |
| 非同期処理 | Cloud Tasks, Task State DB | OK |
| 永続状態 | Firestore | OK |
| ベクトル検索 | Firestore Vector Search | OK |
| ファイル/スナップショット | Cloud Storage, Rollback | OK |
| CI/CD | Cloud Build, Artifact Registry | OK |
| 監視 | Cloud Logging | OK |
| シークレット | Secret Manager | OK |
| 認証 | Firebase Authentication | OK |
| コンテスト後の自由度 | BYOK, BYOLLM, コンテスト後 | OK |

確認済みの重要整合点:

- Worker実行はCloud Run service中心、Cloud Run Jobsは補助用途として整理済み。
- BYOK / BYOLLM はGoogle中心方針を壊さないよう、コンテスト後に分離済み。
- オーケストレーターは判断・計画・委任に限定し、実装は専門ワーカーへ分離済み。

最終判定: **コンテスト提出版として、Google Cloud / Gemini 中心の設計に整合している。**


---

## 追加監査章: Control Plane / Service Registry による全体制御

### 1. 追加が必要な理由

AgentForge Hackathon Edition では、AIエージェントが単独の機能を生成するだけでは不十分である。生成されたUI、API、Worker、Cloud Run service、Cloud Tasks task、Cloud Build実行、Rollback対象を、全体システムとして登録・実行・停止・反映・復旧できる必要がある。

そのため、Orchestrator が Google Cloud の各サービスを直接操作するのではなく、**Control Plane / Service Registry** を中間層として配置する。

```text
User
↓
Reception Agent
↓
Orchestrator
↓
Control Plane / Service Registry
↓
Tool / API Gateway
↓
Google Cloud Services
```

この構成により、AIエージェントは「判断・計画・申請・状態確認」を担当し、実際のGoogle Cloud操作は Tool / API Gateway と Control Plane が権限チェック後に実行する。

---

### 2. Control Plane / Service Registry の責務

Control Plane / Service Registry は、生成されたサブシステムや実行中タスクを一元管理する制御層である。

```text
Control Plane / Service Registry
├─ service_registry
├─ api_registry
├─ ui_view_registry
├─ deployment_registry
├─ route_registry
├─ task_registry
├─ approval_registry
├─ lifecycle_controller
└─ policy_binding_registry
```

#### 2.1 service_registry

Cloud Run service、生成API service、preview service、active revision を管理する。

保存項目例:

```json
{
  "service_id": "task-api-service",
  "type": "generated_api",
  "cloud_run_service": "agentforge-generated-api",
  "active_revision": "task-api-v3",
  "preview_revision": "task-api-v4-preview",
  "status": "active",
  "owner_project_id": "project_001",
  "created_by_task_id": "task_123",
  "can_disable_by_agent": true,
  "can_delete_by_agent": false
}
```

#### 2.2 api_registry

生成された内部APIを登録する。

保存項目例:

```json
{
  "api_id": "task_create_api",
  "path": "/api/tasks",
  "method": "POST",
  "input_schema": "task_create_v1",
  "output_schema": "task_v1",
  "side_effect_level": "write_project_data",
  "required_permission": "project.task.write",
  "status": "active"
}
```

#### 2.3 ui_view_registry

生成UIを登録する。

保存項目例:

```json
{
  "view_id": "task_list_view",
  "route": "/app/tasks",
  "view_manifest": "gs://agentforge-artifacts/views/task_list_view_v1.json",
  "required_apis": ["task_list_api", "task_create_api", "task_update_api"],
  "status": "active"
}
```

#### 2.4 deployment_registry

Cloud Build、Artifact Registry、Cloud Run preview / active 反映状態を管理する。

保存項目例:

```json
{
  "deployment_id": "deploy_456",
  "source_bundle": "gs://agentforge-build-sources/task_api_v4.zip",
  "cloud_build_id": "build_abc",
  "artifact_image": "asia-northeast1-docker.pkg.dev/project/agentforge/task-api:v4",
  "preview_url": "https://task-api-preview-xxxx.a.run.app",
  "approval_status": "pending_user_approval",
  "rollback_checkpoint_id": "checkpoint_789"
}
```

#### 2.5 task_registry

Cloud Tasks task ID と AgentForge 内部の task_runs を対応付ける。

保存項目例:

```json
{
  "task_id": "task_123",
  "cloud_task_name": "projects/.../locations/.../queues/worker-queue/tasks/...",
  "worker_type": "programmer_agent",
  "status": "running",
  "cancel_requested": false,
  "last_progress": "Task API implementation completed."
}
```

#### 2.6 approval_registry

ユーザー承認が必要な操作を管理する。

対象例:

```text
- preview から active への昇格
- 外部公開APIの有効化
- SNS投稿・通知送信
- Cloud Run service の無効化
- Rollback実行
- 課金対象ワーカー実行
```

---

### 3. Webアプリと生成UIの整合

ハッカソン版では、Webアプリ本体は **固定のWeb Shell** として実装する。生成UIのたびにWebアプリ全体を再デプロイするのではなく、Web Shell が `ui_view_registry` と `view_manifest` を読み込み、生成画面を表示する。

```text
Firebase Hosting / Web App Shell
├─ Chat UI
├─ Progress UI
├─ Generated View Renderer
├─ Route Loader
└─ Approval UI
```

生成UIの流れ:

```text
UI Designer Agent
↓
view_manifest.json を生成
↓
Control Plane が ui_view_registry に登録
↓
Web App Shell が registry を読む
↓
Generated View Renderer が画面表示
```

これにより、タスク管理画面、フィード画面、PDFメモ画面などを、Webアプリ全体の再デプロイなしで追加できる。複雑なUIや独自コンポーネントが必要な場合のみ、Programmer Agent がコンポーネントbundleを生成し、Cloud Build経由でpreview反映する。

---

### 4. Cloud Run service / API instance の必要時起動

Cloud Run は未使用時にスケールゼロできるため、生成APIやWorker Runnerの必要時起動に適している。ただし、すべてを同じ扱いにしてはいけない。サービス種別ごとにライフサイクルポリシーを分ける。

| サービス | 方針 |
|---|---|
| reception-api | ユーザー即応のため停止禁止。必要なら min instances=1 を検討 |
| orchestrator-api | 判断中枢。停止禁止。ただしLLM推論自体は必要時呼び出し |
| tool-gateway-api | Google Cloud操作の実行ゲート。停止禁止 |
| worker-runner-api | Cloud Tasksから必要時起動。scale-to-zero可 |
| generated-app-api | 生成API実行基盤。scale-to-zero可 |
| preview service | 検証用。不要時scale-to-zeroまたはdisable可 |
| core service | AIによる停止・削除禁止 |
| obsolete generated service | 管理者承認後にdisable。deleteは原則禁止 |

重要な制約:

```text
- AIはCloud Run Admin APIを直接叩かない
- Cloud Run service delete は原則禁止
- preview / generated service の disable は Control Plane 経由
- core service の disable / delete はAIから不可
```

Cloud Run service の削除は復元不能な影響を持つため、AIエージェントには許可しない。不要化した生成serviceは、まず `status=disabled` とし、トラフィックを0にして保持する。

---

### 5. Cloud Tasks による非同期実行と停止制御

長時間作業は同期レスポンスで待たせず、Cloud Tasks 経由で Worker Runner を起動する。

```text
User
↓
Reception Agent
↓
Orchestrator
↓
Control Plane
↓
Cloud Tasks
↓
Worker Runner on Cloud Run
```

Cloud Tasks の役割:

```text
- ワーカー実行要求のキューイング
- 再試行
- レート制限
- 非同期実行
- task_runs との対応管理
```

停止制御:

```text
1. ユーザーが「中止して」と指示
2. Reception Agent が task_runs.cancel_requested=true を設定
3. 未dispatchのCloud TaskはControl Plane経由で削除
4. 実行中Workerは task_runs.cancel_requested を確認して協調停止
5. 結果を Audit Log に記録
```

禁止操作:

```text
- AIによるqueue purge
- AIによるqueue pause
- AIによる全体キュー停止
```

`queue purge` は影響範囲が広いため、通常の作業中止には使わない。

---

### 6. Cloud Build / Artifact Registry / Cloud Run 反映フロー

生成APIや複雑なUIは、Cloud Buildで検証し、Artifact Registryに保存し、Cloud Run previewとして反映する。

```text
Programmer Agent
↓
source bundle / build manifest を Cloud Storage に保存
↓
Control Plane が deployment_registry に pending 登録
↓
Tool Gateway が Cloud Build trigger を実行
↓
Cloud Build が test / build を実行
↓
Artifact Registry に container image を保存
↓
Cloud Run preview revision に deploy
↓
Review Agent / Test Agent が検証
↓
ユーザー承認
↓
active revision へ昇格
```

このとき、Orchestrator は Cloud Build や Cloud Run を直接操作しない。必ず Tool Gateway / Control Plane を経由する。

---

### 7. AIエージェントができること / できないこと

#### 7.1 AIエージェントができること

AIエージェントは、以下を申請・計画・実行要求できる。

```text
- 作業計画の作成
- UI設計
- API仕様設計
- プログラマーエージェントへの実装依頼
- worker task 作成
- 生成API登録申請
- 生成UI登録申請
- Cloud Build開始申請
- preview deploy申請
- feature disable申請
- task cancel申請
- Rollback申請
- ユーザー承認要求の作成
- 進捗説明
```

#### 7.2 AIエージェントが直接やらないこと

以下はAIエージェントが直接実行してはいけない。

```text
- Google Cloud Admin APIの直接操作
- IAM変更
- Secretの直接読み取り
- core service の停止
- core service の削除
- Cloud Run service delete
- Cloud Tasks queue purge
- 課金設定変更
- ユーザー権限変更
- Management / Billing Layer の改変
- Rollback Store の削除
```

これらは固定の管理システム、Policy Engine、人間承認、または管理者操作に限定する。

---

### 8. サービス間認証

Cloud Run service 間の通信は、IAMとID tokenによるサービス間認証を前提とする。

```text
reception-api
↓
orchestrator-api
↓
tool-gateway-api
↓
worker-runner-api
```

各サービスには個別のService Accountを割り当て、最小権限で運用する。

例:

```text
reception-sa:
  orchestrator-api invoke のみ

orchestrator-sa:
  control-plane-api invoke のみ

control-plane-sa:
  Firestore registry read/write
  Cloud Tasks enqueue
  Cloud Build trigger request
  Cloud Run preview update request

tool-gateway-sa:
  Cloud Build実行
  Cloud Run deploy
  Artifact Registry read/write
  Cloud Storage read/write

worker-runner-sa:
  project workspace read/write
  tool-gateway-api invoke
  Firestore task state update
```

---

### 9. 全体整合性の最終判断

Control Plane / Service Registry を追加することで、AgentForge Hackathon Edition は、単独機能の集合ではなく、AIエージェントが全体を制御できる統合システムとして成立する。

```text
Reception Agent:
  ユーザーへの即時応答、進捗説明、中止・承認受付

Orchestrator:
  要求理解、作業計画、API/UI/Worker要否判断、結果統合

Control Plane / Service Registry:
  生成UI、生成API、Cloud Run service、Cloud Tasks、Cloud Build、Deployment、Approvalの状態管理

Tool / API Gateway:
  Google Cloud操作の安全な実行窓口

Google Cloud Services:
  Cloud Run、Cloud Tasks、Cloud Build、Artifact Registry、Firestore、Cloud Storage、Cloud Logging
```

この構成により、以下が実現できる。

```text
- 必要時だけWorker/APIを起動する
- 作業中もユーザー応答を止めない
- 生成API/UIを登録・反映できる
- previewとactiveを分けられる
- 中止・停止・disableを管理できる
- Rollback対象を追跡できる
- Google Cloud操作をAIから直接分離できる
```

したがって、ハッカソン版の構成は、Google Cloudサービスの利用モデルと整合しており、DevOpsの民主化を示す実装計画として妥当である。

---

## 改定追記：実行時アーキテクチャ確定事項（2026-06-08）

本節は設計レビューを経て確定した実行時アーキテクチャの追記であり、本文の関連記述を補強・優先する。正準（最新）の定義は `IMPLEMENTATION_GUIDE.md` §2.5 に集約する。

### 1. 通信
- ブラウザ（Web Shell）↔ Reception は **REST/HTTPS**（Firebase Auth の ID token）。**MCPは採用しない**（MCPはエージェント↔ツール用。常駐接続はscale-to-zeroと衝突）。MCP化はコンテスト後ロードマップ。
- 進捗・状態のライブ更新は、ブラウザが **Firestoreをリアルタイム購読**（backendを常時起動しない）。

### 2. コスト（アイドル時 ≈ ¥0）
- 全エージェントは非常駐、**Cloud Run scale-to-zero（min=0）**。Workerは Cloud Tasks で必要時のみ起動。
- 理解・整理は**小型安価モデル（Gemini Flash / Flash-Lite）**、重い判断のみ上位モデル＝**モデルルーティング**。

### 3. 生成機能の実行モデル（“生きた機能”）
**「境界LLM（小型）＋決定的API＋動的UI」**の三点セット。
- 骨格＝**決定的API**（CRUD、LLM不使用）。
- 境界＝**小型LLM**：自然言語入力→構造化、出力は任意形式（`function calling`で決定的ツール実行）。
- UI＝**動的manifest**（自然言語で再生成）。
- **節約**：UIを変えない時はAPI直叩き。

### 4. ワーカー非常駐＋コンテキスト永続化
- ワーカーは使用時のみ起動。文脈は **Firestore（Context DB）に永続化**（`context_chunks`/`worker_registry`/`worker_definitions`/`worker_runs`/`conversations`、大物はCloud Storage）し、起動毎に `context_refs` で **rehydrate**。

### 5. API化 vs ワーカー化の判断
- **Orchestratorが判断**（審査基準1の必然性の見せ場）。安定・決定的→API化／自然言語I/O→境界LLM／継続的判断→専用ワーカー（非常駐）。ビルド時ワーカーは汎用・再利用。

