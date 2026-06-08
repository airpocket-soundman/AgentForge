# AgentForge Contest Submission Spec  
## 自然言語でスーパーアプリを育てる DevOps AI Agent Workbench

作成日: 2026-06-08  
対象: DevOps × AI Agent Hackathon 2026 提出版  
版: v1.0 audited

---

## 0. 提出版の結論

AgentForge のコンテスト提出版は、**「スーパーアプリそのもの」ではなく、「スーパーアプリをAIエージェントが安全に育てるための DevOps AI Agent Workbench」** として実装する。

提出版では、ユーザーが自然言語で「タスク管理を追加して」「フィードを作って」「PDFメモを追加して」と依頼すると、以下の流れを実証する。

```text
ユーザー指示
↓
Reception Agent が即時応答
↓
Orchestrator が作業計画を作成
↓
Control Plane / Service Registry に作業・生成物を登録
↓
Cloud Tasks 経由で Worker Runner を起動
↓
UI Designer / API Designer / Programmer / DevOps Agent が分担
↓
Cloud Build で検証
↓
Artifact Registry にイメージ保存
↓
Cloud Run preview にデプロイ
↓
ユーザー承認後に active へ昇格
↓
失敗時は Rollback / disable
```

重要な設計原則は以下である。

- AIエージェントにGoogle Cloudの強権限を直接渡さない。
- AIは判断・計画・申請・進捗説明を担当する。
- 実際のデプロイ操作は Control Plane / Tool Gateway / 限定Service Account が行う。
- 受付係は常に即応可能にし、長時間作業中でも進捗確認・中止・承認ができる。
- 作業ワーカーは常駐させず、Cloud Tasks + Cloud Run で必要時だけ起動する。
- 生成API/UIは必ず registry に登録し、preview と active を分ける。
- Cloud Run service delete、IAM変更、Secret直接読み取り、課金設定変更はAIから禁止する。

---

## 1. コンテスト向けテーマ

### 1.1 タイトル案

**AgentForge: DevOpsの民主化を実現する自己拡張型スーパーアプリ開発エージェント**

### 1.2 1文説明

一般ユーザーが自然言語でスーパーアプリを育てると、裏側ではAIエージェントがUI設計、API設計、実装、テスト、デプロイ、進捗説明、監査ログ、巻き戻しまでを行う DevOps AI Agent Workbench。

### 1.3 コンテストで前面に出す価値

```text
ユーザー体験:
  自然言語でアプリを育てる

技術的価値:
  AIエージェントがDevOpsサイクルを代行する

審査向け主張:
  AIエージェントが価値の中心であり、
  判断・タスク分解・ワーカー委任・デプロイ・運用までを一貫して扱う
```

### 1.4 スーパーアプリの位置づけ

提出版で作る本体はスーパーアプリではない。  
スーパーアプリは、AgentForgeの自己拡張能力を示すための題材である。

```text
作品本体:
  AgentForge Core

デモ対象:
  AgentForgeによって段階的に生成されるPersonal Super App

見せること:
  機能の完成度ではなく、機能追加プロセスそのもの
```

---

## 2. 提出版のスコープ

### 2.1 提出版で実装するもの

```text
Core Agent Layer:
  - Web Shell / Chat UI
  - Reception Agent
  - Orchestrator
  - Control Plane / Service Registry
  - Tool / API Gateway
  - Task State / Worker State
  - Audit Log
  - Approval Flow
  - Simple Rollback / disable

Generated App Layer:
  - タスク管理機能
  - プロジェクトフィード機能
  - PDFメモまたはファイルメモ機能
  - UI manifestによる生成画面表示

External Capability Layer:
  - 最小Social Data Layer
  - File / Object Storage
  - Search / Indexの簡易版

DevOps Layer:
  - Cloud Tasks
  - Cloud Build
  - Artifact Registry
  - Cloud Run preview
  - Cloud Logging
```

### 2.2 提出版で後回しにするもの

```text
- BYOK / BYOM / BYOLLM
- 他社AI API
- ローカルLLM接続
- 本格Marketplace
- 本格課金
- 本格SNS
- OS深部連携
- マイコン書き込み
- 外部公開APIの一般開放
```

これらはコンテスト後ロードマップに置く。  
コンテスト版では Google Cloud / Gemini / ADK 中心に寄せる。

---

## 3. Google Cloud 構成概要

### 3.1 採用サービス一覧

| システム内コンポーネント | Googleサービス | 用途 |
|---|---|---|
| Web Shell / Chat UI | Firebase Hosting | SPA配信、生成UI表示 |
| 認証 | Firebase Authentication | Googleログイン / メールログイン |
| Reception API | Cloud Run | ユーザー即応、進捗説明、中止/承認受付 |
| Orchestrator API | Cloud Run | 要求理解、作業計画、ワーカー選定 |
| Control Plane API | Cloud Run | registry管理、lifecycle制御 |
| Tool Gateway API | Cloud Run | Google Cloud操作の安全な実行窓口 |
| Worker Runner | Cloud Run | UI/API/Programmer/DevOps worker実行 |
| 非同期キュー | Cloud Tasks | 長時間処理の委任、ワーカー起動 |
| 状態DB | Firestore | task_state, registries, audit, context |
| 類似検索 | Firestore Vector Search | API/Worker/Context検索 |
| ファイル保存 | Cloud Storage | 生成物、source bundle、snapshot、upload |
| ビルド | Cloud Build | test / build / containerize |
| コンテナ保存 | Artifact Registry | preview/active image保存 |
| デプロイ先 | Cloud Run | generated API / preview API / core API |
| AI推論 | Gemini API / Vertex AI経由 Gemini | Orchestrator / Workers |
| エージェント構成 | ADK | Orchestrator / worker実装 |
| シークレット | Secret Manager | Gemini key等の安全管理 |
| ログ | Cloud Logging | 実行ログ、エラー、監査補助 |
| 監視 | Cloud Monitoring | リクエスト数、エラー率、レイテンシ |

### 3.2 Google Cloud上のサービス構成図

```text
Firebase Hosting
  └─ Web Shell / Chat UI / Generated View Renderer
        ↓ HTTPS
Cloud Run: reception-api
        ↓ service-to-service auth
Cloud Run: orchestrator-api
        ↓
Cloud Run: control-plane-api
        ↓
Firestore:
  - task_runs
  - worker_runs
  - service_registry
  - api_registry
  - ui_view_registry
  - deployment_registry
  - approval_registry
  - audit_logs
        ↓
Cloud Tasks
        ↓ HTTP target
Cloud Run: worker-runner-api
        ↓
Gemini API / ADK
        ↓
Cloud Storage / Firestore / Tool Gateway
        ↓
Cloud Build
        ↓
Artifact Registry
        ↓
Cloud Run preview / generated API
```

---

## 4. 主要コンポーネント仕様

### 4.1 Web Shell

Web Shell は、生成されるアプリ画面を表示する固定のフロントエンドである。  
提出版ではWebアプリ全体を生成UIごとに再デプロイしない。

役割:

```text
- Chat UI
- Progress UI
- Approval UI
- Generated View Renderer
- Route Loader
```

Googleサービス:

```text
Firebase Hosting
Firebase Authentication
```

生成UIの流れ:

```text
UI Designer Agent
↓
view_manifest.json生成
↓
Cloud Storageへ保存
↓
Control Planeがui_view_registryへ登録
↓
Web Shellがui_view_registryを読む
↓
Generated View Rendererが表示
```

view_manifest例:

```json
{
  "view_id": "task_list_view",
  "route": "/app/tasks",
  "title": "Tasks",
  "components": [
    {
      "type": "form",
      "api": "task_create_api",
      "fields": ["title", "due_date"]
    },
    {
      "type": "list",
      "api": "task_list_api",
      "item_actions": ["complete", "delete"]
    }
  ]
}
```

### 4.2 Reception Agent

Reception Agent はユーザー窓口である。  
重い作業が走っていてもユーザー対応を止めてはいけない。

役割:

```text
- チャット受付
- 現在作業の進捗説明
- 中止要求の受付
- 方針変更の受付
- ユーザー承認の受付
- Orchestratorへの取り次ぎ
```

Googleサービス:

```text
Cloud Run: reception-api
Firestore: task_runs / worker_runs / approval_registry
Gemini API: 軽量応答が必要な場合のみ
```

Reception Agent は原則、Firestoreの状態を読んで即応する。毎回大型LLMを呼ばない。

### 4.3 Orchestrator

Orchestrator は作業判断・計画の中枢である。  
ただし、コードやAPIを直接実装しない。

役割:

```text
- ユーザー要求の解釈
- タスク分解
- API要否判断
- UI設計要否判断
- 外部機能利用可否判断
- 必要ワーカーの選定
- 作業計画の作成
- Control Planeへの登録申請
- 結果統合
```

やらないこと:

```text
- 自分でAPIコードを書く
- 自分でCloud Runへデプロイする
- IAMを変更する
- Secretを読む
- Cloud Run serviceをdeleteする
```

Googleサービス:

```text
Cloud Run: orchestrator-api
Gemini API / ADK
Firestore
```

### 4.4 Control Plane / Service Registry

Control Plane は、AgentForge全体の状態管理とライフサイクル制御を担う。  
AIにGoogle Cloud操作の強権限を直接渡さないための中間制御層である。

役割:

```text
- service_registry管理
- api_registry管理
- ui_view_registry管理
- deployment_registry管理
- route_registry管理
- task_registry管理
- approval_registry管理
- lifecycle_controller
- policy_binding_registry
```

Googleサービス:

```text
Cloud Run: control-plane-api
Firestore
Cloud Tasks client
Cloud Build trigger client
Cloud Run Admin API client
```

Control Plane は必要なGoogle Cloud操作を Tool Gateway に依頼する。  
Orchestrator が直接 Cloud Run Admin API や Cloud Build API を叩くことは禁止する。

### 4.5 Tool / API Gateway

Tool Gateway は、Google Cloud操作や副作用操作の実行窓口である。

役割:

```text
- Cloud Tasks task作成
- Cloud Build trigger実行
- Cloud Run preview deploy
- Artifact Registry操作
- Cloud Storage操作
- Secret Manager経由の秘密情報利用
- Firestore registry更新の一部
- 外部機能Gatewayの入口
```

制約:

```text
- Tool Gatewayのみがデプロイ系Service Accountを持つ
- WorkerやOrchestratorは直接デプロイ権限を持たない
- SecretはTool Gateway内部でのみ参照
- 操作結果はAudit Logへ記録
```

### 4.6 Worker Runner

Worker Runner は非同期作業を行うCloud Runサービスである。  
Cloud Tasksから起動され、必要時だけ動く。

ワーカー種別:

```text
- UI Designer Agent
- API Designer Agent
- Programmer Agent
- Test Agent
- DevOps Agent
- Review Agent
- Recommendation Designer
```

Googleサービス:

```text
Cloud Run: worker-runner-api
Cloud Tasks
Gemini API / ADK
Firestore
Cloud Storage
Tool Gateway
```

ワーカーの基本入力:

```json
{
  "task_id": "task_123",
  "worker_type": "programmer_agent",
  "context_refs": ["project:001", "api_spec:task_v1"],
  "allowed_tools": ["read_workspace", "write_source_bundle"],
  "output_schema": "programmer_result_v1"
}
```

---

## 5. デプロイ制御設計

### 5.1 AIに直接クラウド権限を渡さない

提出版の重要な設計原則は以下である。

```text
AI Agent
  ↓ 申請・計画
Control Plane
  ↓ 権限確認・状態登録
Tool Gateway
  ↓ 限定Service Accountで実行
Google Cloud
```

AIエージェントにGoogle Cloud Admin権限やService Account keyを渡してはいけない。

### 5.2 生成APIデプロイの全体フロー

```text
1. ユーザー:
   「タスク管理APIを追加して」

2. Reception Agent:
   要求を受け付け、Orchestratorへ渡す

3. Orchestrator:
   - API追加が必要と判断
   - API Designer / Programmer / Test / DevOps Workerを計画
   - task_runsを作成
   - Control Planeへ申請

4. Control Plane:
   - api_registryへpending登録
   - deployment_registryへpending登録
   - Cloud Tasksへprogrammer taskを投入

5. Programmer Agent:
   - APIコードを生成
   - テストコードを生成
   - source bundleをCloud Storageへ保存
   - worker_runsへ結果保存

6. Test Agent:
   - ローカル/軽量検証
   - 問題があればProgrammerへ戻す

7. DevOps Agent:
   - Cloud Build用manifestを作成
   - Control Planeへbuild開始申請

8. Tool Gateway:
   - Cloud Build triggerを起動

9. Cloud Build:
   - test
   - build
   - containerize
   - Artifact Registryへpush

10. Tool Gateway:
   - Cloud Run preview serviceへdeploy

11. Review Agent:
   - preview URLを検証
   - API smoke test

12. Reception Agent:
   - ユーザーへ承認要求

13. ユーザー:
   「反映して」と承認

14. Control Plane:
   - route_registry更新
   - api_registry status=active
   - active revisionへ昇格

15. Audit Log:
   - 全操作を記録
```

### 5.3 Cloud Build / Artifact Registry / Cloud Run の扱い

Cloud Buildは生成コードをテスト・ビルドし、Artifact Registryへ保存し、Cloud Run previewへ反映する。

```text
Cloud Storage source bundle
↓
Cloud Build
↓
Artifact Registry
↓
Cloud Run preview
↓
User approval
↓
active route
```

cloudbuild.yaml例:

```yaml
steps:
  - name: 'gcr.io/cloud-builders/npm'
    args: ['ci']
  - name: 'gcr.io/cloud-builders/npm'
    args: ['test']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', '$LOCATION-docker.pkg.dev/$PROJECT_ID/agentforge/generated-api:$SHORT_SHA', '.']
images:
  - '$LOCATION-docker.pkg.dev/$PROJECT_ID/agentforge/generated-api:$SHORT_SHA'
```

実際のCloud Run deployは、Tool GatewayまたはCloud Build stepで行う。  
MVPでは操作面を単純化するため、Tool GatewayからCloud Run deployを行う方式を優先する。

### 5.4 preview / active / disabled

生成サービスには状態を持たせる。

```text
pending:
  仕様生成中

building:
  Cloud Build中

preview:
  検証用URLで確認可能

active:
  Web ShellやAPI Gatewayから利用可能

disabled:
  ルートから外され利用不可

archived:
  履歴保持のみ

deleted:
  原則使用しない。管理者のみ
```

Cloud Run service deleteはAIから禁止する。  
不要な生成機能は `disabled` にし、トラフィックを0にする。

---

## 6. 必要時起動・停止制御

### 6.1 Cloud Runの起動

Cloud Runサービスは明示的な「起動」ではなく、HTTPリクエストでインスタンスが作られる。  
そのため、必要時起動は以下で実現する。

```text
- worker-runner-api:
    Cloud TasksからHTTP requestを受けて起動

- generated-app-api:
    Web ShellまたはTool Gatewayから呼ばれた時に起動

- preview-api:
    Test Agentまたはユーザー確認時に起動
```

### 6.2 停止・無効化

停止には段階を持たせる。

```text
soft disable:
  route_registryから外す

traffic disable:
  Cloud Run trafficを0にする

scale-to-zero:
  min instances=0にして待機

delete:
  原則禁止。管理者のみ
```

AIに許可するのは原則 `soft disable` まで。  
Cloud Run設定変更はControl Plane / Tool Gateway経由で行う。

### 6.3 長時間作業の中止

中止はCloud TasksとFirestore task stateで制御する。

```text
1. ユーザー「中止して」
2. Reception Agentがcancel_requested=true
3. 未実行Cloud TaskはControl Planeが削除
4. 実行中Workerはtask stateを確認し協調停止
5. 完了済み変更はrollback候補へ
```

禁止:

```text
- queue purge
- queue pause
- 全worker強制停止
```

---

## 7. Firestore設計

Firestoreは提出版のControl Plane DBである。

### コレクション構成

```text
/users
/projects
/conversations
/task_runs
/worker_runs
/service_registry
/api_registry
/ui_view_registry
/deployment_registry
/route_registry
/approval_registry
/audit_logs
/context_chunks
/social_objects
/subsystem_registry
```

### task_runs例

```json
{
  "task_id": "task_123",
  "project_id": "project_001",
  "user_id": "user_001",
  "goal": "タスク管理機能を追加する",
  "status": "running",
  "current_step": "programmer_agent",
  "cancel_requested": false,
  "approval_required": false,
  "progress_message": "Task APIを実装中です",
  "created_at": "...",
  "updated_at": "..."
}
```

### api_registry例

```json
{
  "api_id": "task_list_api",
  "path": "/api/tasks",
  "method": "GET",
  "service_id": "generated-app-api",
  "status": "active",
  "side_effect_level": "read_project_data",
  "required_permission": "project.task.read"
}
```

### ui_view_registry例

```json
{
  "view_id": "task_view",
  "route": "/app/tasks",
  "manifest_uri": "gs://agentforge-artifacts/views/task_view_v1.json",
  "status": "active"
}
```

---

## 8. 権限設計

### 8.1 Service Account分離

| Service Account | 主な権限 |
|---|---|
| `reception-sa` | `orchestrator-api` / `control-plane-api` invoke |
| `orchestrator-sa` | `control-plane-api` invoke、限定Firestore read |
| `control-plane-sa` | Firestore registry read/write、Cloud Tasks enqueue、Tool Gateway invoke |
| `tool-gateway-sa` | Cloud Build起動、Artifact Registry書込、Cloud Run preview更新、Cloud Storage操作 |
| `worker-runner-sa` | task state更新、workspace read/write、Tool Gateway invoke |
| `generated-api-runtime-sa` | 生成API実行に必要なFirestore/Storage最小権限 |
| `build-sa` | Cloud Build実行、Artifact Registry push、必要に応じてCloud Run deploy |
| `review-sa` | preview API invoke、Firestore read、Logging read |

### 8.2 AIができること

```text
- 作業計画作成
- UI設計
- API設計
- Worker task 作成申請
- Cloud Build開始申請
- preview deploy申請
- 生成UI/API登録申請
- disable申請
- rollback申請
- ユーザー承認要求
- 進捗説明
```

### 8.3 AIが直接できないこと

```text
- IAM変更
- Service Account作成
- Secret直接読み取り
- Cloud Run core service停止
- Cloud Run service delete
- Cloud Tasks queue purge
- Billing設定変更
- Management / Billing Layer変更
- Rollback Store削除
- Artifact Registry全削除
- Cloud Storage bucket削除
```

---

## 9. MVP開発手順

### Phase 0: Google Cloud初期設定

作成するもの:

```text
- Google Cloud project
- Firebase project
- Firestore native mode
- Cloud Storage bucket
- Artifact Registry repository
- Cloud Tasks queue
- Cloud Run services
- Secret Manager secrets
```

有効化するAPI:

```text
- run.googleapis.com
- cloudbuild.googleapis.com
- artifactregistry.googleapis.com
- firestore.googleapis.com
- cloudtasks.googleapis.com
- secretmanager.googleapis.com
- logging.googleapis.com
- storage.googleapis.com
- firebase.googleapis.com
- aiplatform.googleapis.com または Gemini Developer API
```

### Phase 1: Web Shell + Reception

```text
- Firebase HostingにSPAを配置
- Firebase Authでログイン
- Cloud Runにreception-apiを配置
- Firestoreにconversation / task_state保存
- Reception Agentが進捗確認に即答できる
```

ゴール:

```text
ログインしてチャットできる。
まだ機能追加はできないが、task_stateを読んで説明できる。
```

### Phase 2: Orchestrator + Gemini

```text
- orchestrator-apiをCloud Runに配置
- Gemini API呼び出し
- ユーザー要求を作業計画JSONへ変換
- Firestore task_runsに保存
```

ゴール:

```text
「タスク管理を追加して」と言うと作業計画が生成される。
```

### Phase 3: Control Plane / Registry

```text
- control-plane-apiをCloud Runに配置
- service_registry / api_registry / ui_view_registry / deployment_registry作成
- Orchestratorがregistry登録申請できる
```

ゴール:

```text
作業計画と生成予定UI/APIがregistryにpending登録される。
```

### Phase 4: Worker Runner + Cloud Tasks

```text
- worker-runner-apiをCloud Runに配置
- Cloud Tasks queue作成
- Control Planeがworker taskをenqueue
- Worker RunnerがUI Designer / API Designer / Programmer役を実行
- 進捗をworker_runsに保存
```

ゴール:

```text
長時間作業中でもReception Agentが進捗説明できる。
```

### Phase 5: 生成UI manifest

```text
- UI Designerがview_manifest生成
- Cloud Storageに保存
- ui_view_registryにactive登録
- Web Shellが生成画面を表示
```

ゴール:

```text
チャットから「タスク管理画面」が追加される。
```

### Phase 6: 生成APIのpreview deploy

```text
- ProgrammerがAPIコード生成
- source bundleをCloud Storageに保存
- Tool GatewayがCloud Build起動
- Artifact Registryへpush
- Cloud Run previewへdeploy
- Smoke test
```

ゴール:

```text
生成APIがpreview URLで動く。
```

### Phase 7: 承認・active化・Rollback

```text
- preview結果をReception Agentが説明
- ユーザーが承認
- route_registryをactiveに変更
- 直前checkpointを保存
- 失敗時はrouteを戻す
```

ゴール:

```text
生成機能を本体アプリから使える。
```

---

## 10. デモシナリオ

### シナリオ1: 初期状態

```text
画面:
  Chatのみ

ユーザー:
  「このアプリにタスク管理機能を追加して」
```

### シナリオ2: 作業計画

Reception Agent:

```text
タスク管理機能を追加するには、
1. Task API
2. Task UI
3. Firestore tasks collection
4. テスト
5. preview deploy
が必要です。開始しますか？
```

### シナリオ3: 非同期作業と進捗確認

ユーザー:

```text
進捗どう？
```

Reception Agent:

```text
現在はProgrammer AgentがTask APIを生成中です。
UI Designerは画面manifestを作成済みです。
次にCloud Buildでpreviewを作成します。
```

### シナリオ4: preview確認

```text
Task API preview URL
Task UI preview route
Smoke test result
```

### シナリオ5: active化

ユーザー:

```text
反映して
```

Control Plane:

```text
route_registryを更新し、/app/tasks をactive化。
api_registryのtask APIをactive化。
```

### シナリオ6: rollback

ユーザー:

```text
直前の変更を戻して
```

Control Plane:

```text
route_registryを前checkpointに戻す。
generated APIをdisabledにする。
task_stateにrollback完了を記録。
```

---

## 11. Googleサービス適合性監査

### 11.1 Cloud Run

適合性:

```text
- Core API群のHTTP実行に適する
- Worker RunnerをCloud Tasksから起動できる
- generated API / preview APIをCloud Runに載せられる
- 未使用時scale-to-zero設計に合う
```

注意:

```text
- Reception APIの即応性を重視するならmin instances=1を検討
- ただし無料枠重視ならmin=0から開始
- deleteは禁止し、disable/traffic controlで扱う
```

### 11.2 Cloud Tasks

適合性:

```text
- Worker Runnerの非同期起動に適する
- 長時間処理をユーザー応答から切り離せる
- HTTP targetでCloud Runを呼べる
```

注意:

```text
- payloadには本文を入れずcontext_refだけ渡す
- queue purgeはAIから禁止
- 中止はtask単位削除 + cancel_requestedで行う
```

### 11.3 Firestore / Vector Search

適合性:

```text
- registry / task state / context / auditに適する
- JSON的な柔軟データ構造に向く
- Vector Searchで類似API/類似作業検索が可能
```

注意:

```text
- 大量ログはFirestoreに置きすぎない
- 詳細artifactはCloud Storageへ逃がす
- ベクトル埋め込みはFirestoreが生成するのではなくGemini/Vertex等で生成して保存する
```

### 11.4 Cloud Build / Artifact Registry

適合性:

```text
- 生成コードのtest/build/container化に適する
- Artifact Registryへimage保存できる
- Cloud Run preview deployへ接続できる
```

注意:

```text
- AIの修正ループでbuildが暴走しないよう上限を設ける
- preview imageを残しすぎると容量が増える
```

### 11.5 Cloud Storage

適合性:

```text
- view_manifest
- source bundle
- uploaded files
- generated artifacts
- rollback snapshot
```

注意:

```text
- snapshot bucketはAIから削除不可
- lifecycle ruleで古いpreview artifactsを整理
```

### 11.6 Gemini API / ADK

適合性:

```text
- Orchestrator / Reception / Worker のLLM処理に適する
- ADKでマルチエージェント構成を表現可能
- ハッカソン要件のGoogle AI利用に合う
```

注意:

```text
- 無料枠にはレート制限がある
- Programmer Agentには高品質モデルを絞って使う
- 受付係や分類は軽量モデルに寄せる
```

### 11.7 Secret Manager / IAM

適合性:

```text
- Gemini API key等の保管
- Service Account分離
- Tool Gateway限定の秘密情報利用
```

注意:

```text
- WorkerにSecretを直接見せない
- IAM変更はAI禁止
```

---

## 12. 実装優先度

### P0: 必須

```text
- Firebase Hosting Web Shell
- Firebase Auth
- reception-api
- orchestrator-api
- Firestore task_runs / conversations
- Gemini API呼び出し
```

### P1: Core Agent化

```text
- control-plane-api
- service/api/ui registry
- Cloud Tasks
- worker-runner-api
- 進捗確認
```

### P2: 自己拡張の見える化

```text
- UI manifest生成
- Web Shellによる生成画面表示
- タスク管理機能の追加
```

### P3: DevOps体験

```text
- Programmer Agent
- Cloud Build
- Artifact Registry
- Cloud Run preview
- Smoke test
- 承認後active化
```

### P4: 安全性

```text
- Rollback / disable
- Audit Log
- Review Agent
- Policy Engine簡易版
```

---

## 13. ハッカソン提出時に見せるべき画面

```text
1. Chat UI
2. Task State / Progress panel
3. Orchestrator plan view
4. Worker run timeline
5. Generated UI preview
6. API registry
7. Deployment registry
8. Approval panel
9. Rollback panel
10. Audit log
```

提出デモで一番重要なのは、生成されたタスク管理画面の完成度ではない。  
重要なのは、**チャットから要求し、AIが計画し、ワーカーに委任し、Google Cloud上にpreview deployし、承認後に反映する一連のDevOps体験**である。

---

## 14. コンテスト後ロードマップ

```text
Phase A:
  Model Gateway抽象化

Phase B:
  BYOK / 他社AI API対応

Phase C:
  BYOLLM / ローカルLLM / 社内LLM対応

Phase D:
  Marketplace / Subsystem販売

Phase E:
  本格課金 / 使用量管理

Phase F:
  本格SNS / Social Data Layer拡張

Phase G:
  IoT / Device Gateway
```

コンテスト版ではGoogle Cloud中心性を崩さない。  
モデル自由度やVPS/ローカルLLM対応はコンテスト後の拡張計画とする。

---

## 15. 公式情報・参照先

- Cloud Run source deploy roles: https://docs.cloud.google.com/run/docs/deploying-source-code
- Cloud Run build service account: https://docs.cloud.google.com/run/docs/configuring/services/build-service-account
- Cloud Run service-to-service authentication: https://docs.cloud.google.com/run/docs/authenticating/service-to-service
- Cloud Tasks HTTP target tasks: https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks
- Cloud Run async tasks with Cloud Tasks: https://docs.cloud.google.com/run/docs/triggering/using-tasks
- Firestore Vector Search: https://firebase.google.com/docs/firestore/vector-search
- Firestore product overview: https://cloud.google.com/products/firestore
- ADK documentation: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk
- Gemini API pricing / free tier: https://ai.google.dev/gemini-api/docs/pricing
- Gemini API rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Firebase Hosting docs: https://firebase.google.com/docs/hosting
- Firebase pricing: https://firebase.google.com/pricing
- Cloud Build overview: https://cloud.google.com/build/docs/overview
- Cloud Build triggers: https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers
- Artifact Registry pricing: https://cloud.google.com/artifact-registry/pricing
- Cloud Run pricing: https://cloud.google.com/run/pricing
- Cloud Tasks pricing: https://cloud.google.com/tasks/pricing
- Secret Manager free tier: https://docs.cloud.google.com/free/docs/free-cloud-features
- Google Cloud free credit: https://cloud.google.com/?hl=ja

---

## 16. 最終監査結果

### 16.1 全体整合性

整合している。

```text
Reception:
  常時応答

Orchestrator:
  判断・計画

Control Plane:
  registry / lifecycle制御

Tool Gateway:
  Google Cloud操作

Worker Runner:
  必要時起動

Cloud Run:
  core API / worker / generated API

Cloud Tasks:
  非同期処理

Cloud Build:
  生成物の検証・ビルド

Firestore:
  状態管理

Cloud Storage:
  生成物・snapshot

Gemini / ADK:
  AIエージェント
```

### 16.2 重要な修正済み設計

```text
- AIにCloud管理者権限を直接渡さない
- Control Plane / Tool Gateway経由に限定
- previewとactiveを分離
- core service停止は禁止
- Cloud Run deleteは禁止
- Cloud Tasks queue purgeは禁止
- IAM変更は禁止
- Secret直接読み取りは禁止
```

### 16.3 リスク

```text
- Cloud Build連打によるコスト増
- Gemini API無料枠のレート制限
- Firestore read/write増加
- 生成APIのセキュリティ
- Web Shell manifest rendererの脆弱性
- previewからactiveへの承認漏れ
```

### 16.4 対策

```text
- taskごとのbuild上限
- worker retry上限
- manifest schema validation
- generated API permission check
- user approval必須
- audit log必須
- disable優先、delete禁止
```

### 16.5 最終判断

この仕様は、Google Cloudサービスの使い方と整合している。  
また、AIエージェントが単独のコード生成ではなく、デプロイ、非同期実行、進捗説明、承認、preview、active化、Rollbackまでを統合制御するDevOps体験として成立する。

ハッカソン提出版としては、まずP0〜P2を確実に実装し、余力でP3のCloud Build / Cloud Run previewまで到達するのが現実的である。

---

## 17. 改定追記：実行時アーキテクチャ確定事項（2026-06-08）

本章は設計レビューを経て確定した実行時アーキテクチャの追記であり、本文中の関連記述（生成機能の扱い・通信・コスト）を補強・優先する。正準（最新）の定義は `IMPLEMENTATION_GUIDE.md` §2.5 に集約する。

### 17.1 通信
- ブラウザ（Web Shell）↔ Reception は **REST/HTTPS**（Firebase Auth の ID token）。**MCPは採用しない**（MCPはエージェント↔ツール用であり、ブラウザ↔backendの転送路ではない。常駐接続はscale-to-zeroと衝突する）。MCP化はコンテスト後ロードマップ。
- 進捗・状態のライブ更新は、ブラウザが **Firestoreをリアルタイム購読**（backendを常時起動しない）。操作（送信・承認・中止）時だけ core-api を起動。

### 17.2 コスト（アイドル時 ≈ ¥0）
- 全エージェントは非常駐、**Cloud Run scale-to-zero（min=0）**。Workerは Cloud Tasks で必要時のみ起動。
- 理解・整理は**小型安価モデル（Gemini Flash / Flash-Lite）**、重い判断（計画・コード生成）のみ上位モデル＝**モデルルーティング**。
- 審査期間（〜7/24）だけ Reception を min=1 にする運用は可。

### 17.3 生成機能の実行モデル（“生きた機能”）
生成機能は静的フォームにしない。**「境界LLM（小型）＋決定的API＋動的UI」**の三点セットとする。
- 骨格＝**決定的API**：追加/一覧/完了等のCRUD（Firestore、LLM不使用）。
- 入出力の境界＝**小型LLM**：自然言語入力→タスク情報へ構造化、出力は任意形式。`function calling`で決定的ツールを呼ぶ。
- UI＝**動的manifest**：自然言語でUI Designerが `view_manifest` を再生成。
- **節約**：UIを変えない時はAPI直叩き。LLM不要な操作はLLMに通さない。

### 17.4 ワーカー非常駐＋コンテキスト永続化
- ワーカーは機能使用時のみ起動、他は休止。
- 短命のため文脈はワーカー内に持たせず、**Firestore（Context DB）に永続化**：`context_chunks`（+Vector Search）/ `worker_registry` / `worker_definitions` / `worker_runs` / `conversations`、大物は Cloud Storage。起動毎に `context_refs`（最小ポインタ）で取得し **rehydrate**。

### 17.5 API化 vs ワーカー化の判断
- **Orchestratorが判断**（審査基準1「AIエージェントである必然性」の見せ場）。
- 安定・決定的→API化／自然言語I/O→境界LLM／継続的判断→専用ワーカー（非常駐）。ビルド時ワーカー（UI Designer/Programmer等）は汎用・再利用、機能ごとに新規作成しない。
