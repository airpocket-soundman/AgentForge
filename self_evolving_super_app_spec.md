# 自己拡張型スーパーアプリ基盤 仕様整理・既存例調査

作成日: 2026-06-08  
対象: チャットUIを入口に、LLMがUI・API・ワーカー・SNS表示・業務機能を動的に生成し、ユーザーごとに成長するWebアプリ基盤

---

## 1. 構想の要約

本構想は、単なる「AIチャット付きWebアプリ」ではない。ユーザーごとに隔離されたワークスペースを持ち、LLMオーケストレーターが必要に応じてUI、内部API、ワーカー、データ構造、SNSビュー、業務機能を生成・更新する、自己拡張型のアプリ基盤である。

既存のスーパーアプリは、決済、チャット、SNS、EC、予約、ミニアプリなどを最初から多数搭載する「全部入りアプリ」である。一方、本構想は、ユーザーの要求・作業履歴・利用パターンに応じて、アプリ自身が必要な機能を追加していく「スーパーアプリ生成基盤」に近い。

中核は以下である。

- ユーザーごとのチャットセッション
- ユーザーごとの隔離ワークスペース
- オーケストレーターLLM
- 動的に生成される一時ワーカーLLM
- 小型・中型・大型LLMのモデルルーティング
- Context DBによる文脈継承
- APIカタログ
- 必要に応じた内部API生成
- 自己設計UI
- SNS/タイムライン/フィードの動的生成
- 巻き戻し機能
- Policy Engineによる権限管理
- Tool Gatewayによる副作用操作の制御
- 監査ログ

最初はWebアプリとして実装し、将来的にはPWA、デスクトップ補助アプリ、ローカルエージェント、OS連携へ拡張する。

---

## 2. 基本思想

### 2.1 完成済みアプリではなく、成長するアプリ

このアプリの価値は、最初から多機能であることではなく、ユーザーごとの要求に合わせて自分自身を拡張できる点にある。

たとえば初期状態は以下だけでよい。

- ログイン
- チャット
- ファイルアップロード
- ユーザー別ワークスペース
- Context DB
- API Gateway
- Rollback Service
- Policy Engine

そこからユーザーが自然言語で要求する。

```text
タスク管理ページを作って
論文PDFを要約できるようにして
画像編集機能を追加して
マイコンのファームウェアをビルドできるようにして
SNSタイムラインを研究者向けに変えて
```

オーケストレーターは、既存APIで足りるか、ワーカーを生成すべきか、新APIを作るべきか、UIを追加すべきかを判断する。

### 2.2 LLMは毎回すべてを考えない

高コストなLLMに毎回すべての文脈を読ませる構成は破綻しやすい。

避けるべき設計:

```text
ユーザー指示
↓
巨大LLMに会話履歴・ファイル・DB内容を丸ごと投入
↓
毎回すべて推論
```

目指す設計:

```text
ユーザー指示
↓
オーケストレーターが既存API/Context DB/API Catalogを検索
↓
必要な最小文脈だけ取得
↓
必要なら一時ワーカーを起動
↓
安定処理はAPI化
↓
結果をContext DBへ保存
```

LLMは「毎回作業する存在」ではなく、「道具を作り、次回から道具を使う存在」として扱う。

### 2.3 ワーカーは常駐させない

各機能に対応するワーカーLLMは、24時間待機させない。呼び出された瞬間だけ起動し、必要な文脈だけをContext DBから取得し、結果を書き戻して終了する。

これにより以下を抑える。

- トークン使用量
- LLM推論コスト
- サーバ負荷
- セッション肥大化
- 不要な常駐プロセス
- 権限暴走範囲

### 2.4 壊さないより、壊しても戻せる

LLMに開発・編集・生成権限を与える以上、誤変更は避けられない。したがって「絶対に壊さない」ではなく、「復旧不能な変更を許さない」設計にする。

巻き戻し機能はLLMから厳密に隔離する。

```text
LLMが触れる領域:
  - ユーザー用ワークスペース
  - アプリコードの作業ブランチ
  - 生成ファイル
  - 一時DB
  - ユーザーデータの操作API

LLMが触れない領域:
  - Snapshot Store
  - Rollback Service
  - 監査ログの原本
  - 権限設定の根本ポリシー
  - シークレット
```

---

## 3. 全体アーキテクチャ

### 3.1 概念図

```text
User
 ↓
Web App / Chat UI / SNS UI
 ↓
Orchestrator Session
 ├─ 意図理解
 ├─ タスク分解
 ├─ 既存API検索
 ├─ API要不要判断
 ├─ Worker定義生成
 ├─ Model Router呼び出し
 ├─ Context DB検索
 ├─ 権限要求案生成
 └─ 結果統合
 ↓
Policy Engine
 ├─ ツール権限判定
 ├─ 副作用レベル判定
 ├─ 危険操作承認要求
 └─ シークレット保護
 ↓
Tool Gateway / API Gateway
 ├─ 既存内部API
 ├─ 外部APIラッパー
 ├─ ファイル操作API
 ├─ DB操作API
 ├─ Git操作API
 ├─ ビルドAPI
 ├─ 画像処理API
 └─ SNS Feed API
 ↓
Ephemeral Workers
 ├─ UI生成ワーカー
 ├─ API生成ワーカー
 ├─ 論文解析ワーカー
 ├─ 画像処理ワーカー
 ├─ コード修正ワーカー
 ├─ SNSキュレーションワーカー
 ├─ タスク整理ワーカー
 └─ 検証ワーカー
 ↓
Context DB / Object Store / Event Log
 ↓
Checkpoint / Rollback / Audit Log
```

### 3.2 常時稼働するもの

常時稼働するのは、LLMそのものではなく、通常のWebアプリ基盤と状態管理基盤である。

- Webサーバ
- 認証基盤
- DB
- Context DB
- API Gateway
- Tool Gateway
- Policy Engine
- Rollback Service
- Queue
- Scheduler
- Audit Log

### 3.3 必要時だけ起動するもの

- 一時ワーカーLLM
- API生成ワーカー
- UI生成ワーカー
- SNSキュレーションワーカー
- 論文解析ワーカー
- コード修正ワーカー
- ファームウェア開発ワーカー
- 検証ワーカー

---

## 4. オーケストレーター

### 4.1 役割

オーケストレーターは単なる会話相手ではない。システム全体の司令塔である。

主な役割:

- ユーザー意図の理解
- タスク分解
- 既存APIの検索
- API化の要否判断
- 既存ワーカー定義の検索
- 新規ワーカー定義の生成
- モデル選択
- Context DBからの文脈選択
- 権限要求の作成
- Policy Engineへの申請
- Tool Gateway経由の処理実行
- 結果統合
- UI追加の判断
- APIカタログ更新
- ワーカー定義の保存・昇格・廃棄

### 4.2 オーケストレーターは永続LLMである必要はない

「セッション」という表現を使っているが、実装上はLLMが常時起動している必要はない。

現実的には以下でよい。

```text
Orchestrator State = Context DBに保存
LLM呼び出し = ユーザー操作・イベント発生時だけ
```

つまり常駐させるのは「状態」であって、LLMプロセスそのものではない。

### 4.3 オーケストレーターの判断フロー

```text
ユーザー要求
↓
要求分類
↓
既存APIカタログ検索
↓
既存APIで処理可能か？
 ├─ Yes → API実行
 └─ No
      ↓
既存ワーカー定義検索
↓
既存ワーカーで処理可能か？
 ├─ Yes → ワーカー起動
 └─ No
      ↓
一時ワーカー定義生成
↓
Policy Engineで権限検査
↓
Worker Runtimeで実行
↓
結果を評価
↓
再利用価値あり？
 ├─ No → 一時ワーカー破棄
 └─ Yes → ワーカー定義保存 / API化候補化
```

---

## 5. 動的ワーカー定義

### 5.1 ワーカーは事前固定しない

ワーカーはあらかじめ `paper_worker` や `image_worker` のように固定で用意するのではなく、オーケストレーターがタスクに応じて定義する。

例:

```text
この論文群から、実験条件だけを抽出し、装置構成・データセット・評価指標で比較するワーカー
```

というように、その場で専用ワーカーを生成できる。

### 5.2 ワーカー定義に含める項目

ワーカー定義はプロンプトだけでは不十分である。以下を含める。

```json
{
  "worker_id": "worker_20260608_001",
  "purpose": "PDF論文から実験条件と主張を抽出する",
  "lifetime": "single_task",
  "model_policy": {
    "preferred_class": "small_or_medium",
    "escalate_to_large_if": [
      "confidence_low",
      "schema_validation_failed",
      "conflicting_claims_detected"
    ]
  },
  "allowed_tools": [
    "read_paper_text",
    "read_paper_figures",
    "write_structured_claims"
  ],
  "denied_tools": [
    "write_code",
    "delete_files",
    "deploy",
    "read_secrets"
  ],
  "context_refs": [
    "paper:123",
    "project:paper_review_policy"
  ],
  "input_schema": {
    "paper_id": "string",
    "target_sections": "array"
  },
  "output_schema": {
    "claims": "array",
    "experimental_conditions": "array",
    "limitations": "array"
  },
  "side_effect_level": "low"
}
```

### 5.3 ワーカーの種類

#### 一時ワーカー

- 1タスク専用
- 実行後に破棄
- 例: 特定PDFだけを解析するワーカー

#### 再利用ワーカー

- 類似タスクで再利用
- Context DBに保存
- 例: 論文の主張抽出ワーカー

#### 標準ワーカー

- 高頻度・高成功率
- API Catalogと連携
- 例: タグ付け、要約、分類、差分説明

### 5.4 ワーカー生成の制約

オーケストレーターがワーカーを定義するが、権限付与はPolicy Engineが行う。

固定ルール:

- ワーカーは自分の権限を増やせない
- ワーカーは別ワーカーを勝手に作れない
- ワーカーはContext DB全体を読めない
- ワーカーはSnapshot/Rollback領域に触れない
- ワーカーはシークレットを読めない
- 副作用操作はTool Gateway経由のみ
- 出力はスキーマ検証する

---

## 6. モデルルーティング

### 6.1 モデルを使い分ける理由

すべてを大型LLMで処理するとコストが膨らむ。小型LLM・中型LLM・大型LLMを使い分ける。

```text
大型LLM:
  - 要件整理
  - 複雑な設計判断
  - セキュリティ判断
  - 複雑なコード生成
  - 本番反映前レビュー

中型LLM:
  - 通常のコード修正
  - UI生成
  - API仕様生成
  - 論文要約
  - タスク整理

小型LLM:
  - 分類
  - タグ付け
  - 短い要約
  - 既存API選択
  - ルーティング
  - メタデータ抽出
```

### 6.2 LLM不要な処理

以下は原則としてLLMにやらせない。

- 画像リサイズ
- PDFテキスト抽出
- 正規表現抽出
- DB検索
- embedding検索
- ソート
- 重複排除
- 通知送信
- 定型変換
- バッチ処理

LLMは高価な推論リソースであり、機械的処理に使うべきではない。

### 6.3 ルーティング基準

Model Routerは以下で判断する。

- タスク種別
- 必要精度
- 入力サイズ
- 危険度
- レイテンシ要求
- 予算
- 過去の成功率
- 出力スキーマ検証結果

低コスト化のため、まず小型LLMで試し、信頼度が低い場合に大型LLMへエスカレーションする方式が有効である。

---

## 7. API生成・APIカタログ

### 7.1 API化の目的

API化は機能追加だけでなく、トークン削減のためにも重要である。

LLMに毎回以下を行わせるのは無駄である。

- 全文を読む
- 同じ判断を繰り返す
- 同じ処理手順を書く
- 同じファイル操作を行う
- 同じDB検索を自然言語で解釈する

安定した処理はAPI化する。

### 7.2 API化すべき条件

- 繰り返し使う
- 入力と出力をスキーマ化できる
- 手順が安定している
- LLM判断が少ない
- 処理コストが高い
- UIから直接呼びたい
- 他ワーカーからも使いたい
- 結果の再現性が重要

### 7.3 API化しない方がよい条件

- 一回限りの判断
- 仕様が揺れている
- 出力形式が安定していない
- 高度な設計判断が必要
- 人間との対話が必要
- 危険操作を含む
- 失敗時の影響が大きい

### 7.4 APIの段階

```text
Stage 1: 一時スクリプト
Stage 2: 内部ツール
Stage 3: 内部API
Stage 4: UI接続
Stage 5: 標準機能化
```

### 7.5 APIカタログ

APIが増えると、LLM自身も何があるか分からなくなる。そのためAPIカタログが必須である。

```json
{
  "endpoint": "/api/papers/:id/claims",
  "description": "論文から抽出済みの主要主張を返す",
  "input_schema": { "paper_id": "string" },
  "output_schema": { "claims": "array" },
  "permissions": ["read_paper"],
  "side_effects": "none",
  "cost_estimate": "low",
  "examples": [
    "GET /api/papers/p_123/claims"
  ],
  "owner_project": "paper_review"
}
```

---

## 8. Context DB

### 8.1 目的

マルチワーカー構成では、各ワーカーが短命であるため、文脈をワーカー内部に持たせてはいけない。文脈はContext DBに保存する。

Context DBは単なる会話履歴保存ではない。構造化された文脈管理基盤である。

### 8.2 保存対象

- user_context
- project_context
- session_summary
- task_state
- decision_log
- api_catalog
- worker_definitions
- worker_outputs
- file_index
- memory_chunks
- embeddings
- change_history
- permission_context
- ui_context
- sns_context

### 8.3 構成案

最初はPostgreSQL中心でよい。

```text
PostgreSQL
 ├─ 通常テーブル
 ├─ JSONB
 ├─ pgvector
 ├─ event_log
 ├─ worker_definitions
 ├─ api_catalog
 └─ object storage参照
```

必要に応じて以下を分離する。

- Vector DB
- Object Storage
- Graph DB
- Event Store
- Search Index

### 8.4 コンテキスト引き継ぎ単位

会話丸ごとではなく、以下の単位で取り出す。

- User Context
- Project Context
- Task Context
- Artifact Context
- Decision Context
- Permission Context
- API Context
- UI Context
- SNS Context

ワーカーには必要最小限の `context_refs` を渡す。

```json
{
  "task": "指定PDFから主張を抽出する",
  "context_refs": [
    "paper:123:extracted_text",
    "project:paper_review:summary_policy"
  ],
  "allowed_tools": [
    "read_paper_text",
    "write_claims"
  ],
  "output_schema": "claims_v1"
}
```

---

## 9. UI自己設計

### 9.1 UIは固定しない

アプリのUIは固定ページの集合ではなく、ユーザーや目的に応じて生成されるビューとする。

同じ情報オブジェクトでも、表示形式を変えられる。

```text
研究者向け: 論文カード + 引用グラフ
開発者向け: Issue + Pull Request + 技術メモ
趣味向け: 画像ギャラリー + コメント
教育向け: 問答 + 添削 + 学習履歴
企業向け: タスク + 稟議 + 日報
地域向け: 地図 + イベント + 掲示板
```

### 9.2 View Generator

```text
Information Object Store
↓
Relation Graph
↓
Ranking / Filtering Engine
↓
View Generator
↓
User-specific UI
```

生成可能なビュー例:

- timeline_view
- thread_view
- kanban_view
- calendar_view
- map_view
- gallery_view
- paper_review_view
- issue_tracker_view
- chat_room_view
- knowledge_graph_view
- firmware_build_view

---

## 10. SNS機能

### 10.1 SNSを固定形式にしない

本構想では、SNSはX型、Instagram型、Reddit型、Discord型のどれかに固定しない。UIとフィードロジックを生成可能にすることで、任意のSNS形態を取れるようにする。

### 10.2 情報オブジェクト

投稿だけを基本単位にしない。以下をInformation Objectとして扱う。

- 投稿
- コメント
- 記事
- 画像
- 動画
- 音声
- PDF
- 論文
- コード
- タスク
- Issue
- 実験ログ
- センサー値
- マイコンファーム
- ノート
- チャット履歴
- LLM生成物
- 外部リンク

### 10.3 AIキュレーション

SNSフィードは、ユーザーの選択により以下のようなモードを取れる。

#### フィルターバブル強化

- 関心に近い投稿を優先
- 価値観が近い人を優先
- 不快な話題を隠す
- 専門領域を深掘り
- 似た意見をクラスタ化

#### 視野拡張

- 反対意見を一定割合で混ぜる
- 専門外の視点を提示する
- 海外圏の議論を翻訳して混ぜる
- 異分野の類似構造を提示する
- 自分の前提を揺さぶる投稿を出す

#### 明示すべき表示方針

- 深掘りモード
- 反対意見混入モード
- 未読重要度優先
- 自分と遠い視点優先
- 癒やし優先
- 研究優先
- 実務優先

既存SNSの問題は、推薦ロジックがブラックボックスであること。本構想では「なぜこの投稿が出ているか」をユーザー側に戻す。

---

## 11. セキュリティ・権限設計

### 11.1 ユーザー分離

ユーザーごとに以下を分離する。

- LLMセッション状態
- workspace
- DB tenant / schema
- files
- tools
- API権限
- Context DB範囲

```text
User A
 ├─ workspace A
 ├─ Context A
 ├─ API scope A
 └─ Worker scope A

User B
 ├─ workspace B
 ├─ Context B
 ├─ API scope B
 └─ Worker scope B
```

### 11.2 プロジェクト分離

同一ユーザー内でもプロジェクトごとに分離する。

```text
User A
 ├─ project_kigo
 ├─ project_mcu
 ├─ project_paper_analysis
 └─ project_sns
```

論文解析ワーカーがマイコンファーム開発プロジェクトを触らないようにする。

### 11.3 Tool Gateway

LLMやワーカーに直接shellやDB権限を渡さない。すべてTool Gateway経由にする。

```text
LLM / Worker
↓
Tool Gateway
↓
Policy Check
↓
実行
↓
Audit Log
```

### 11.4 危険操作

以下は承認制または禁止にする。

- shell実行
- ファイル削除
- DBスキーマ変更
- 本番DB更新
- 外部API送信
- メール送信
- SNS投稿
- 決済
- 本番デプロイ
- マイコン書き込み
- `.env` 読み取り
- 秘密鍵読み取り
- unrestricted network access

### 11.5 シークレット隔離

LLMにAPIキーや `.env` を見せない。必要な処理はサーバ側の専用ツールが代行する。

悪い例:

```text
LLMが.envを読み、APIキーを使って外部APIを呼ぶ
```

良い例:

```text
LLMが「メール送信API」を呼ぶ
↓
サーバ側ツールが内部で認証情報を使う
↓
LLMにはキーを見せない
```

---

## 12. 巻き戻し機能

### 12.1 原則

巻き戻し機能はLLMから隔離する。LLMは巻き戻しを提案できても、Snapshot Storeを削除・変更できない。

### 12.2 対象

巻き戻し対象はコードだけではない。

- コード
- DBスキーマ
- DBデータ
- アップロードファイル
- 生成ファイル
- 設定
- ジョブ履歴
- APIカタログ
- UI定義
- ワーカー定義

### 12.3 チェックポイント

```text
checkpoint_2026-06-08_001
 ├─ git_commit
 ├─ db_schema_version
 ├─ db_snapshot
 ├─ file_snapshot
 ├─ config_snapshot
 ├─ api_catalog_snapshot
 ├─ ui_definition_snapshot
 ├─ worker_definition_snapshot
 └─ metadata.json
```

### 12.4 自動チェックポイント対象

破壊的操作の前に自動チェックポイントを作る。

- ファイル削除
- 大量ファイル変更
- DBスキーマ変更
- DBレコード一括更新
- 本番デプロイ
- 外部APIへの書き込み
- 設定ファイル変更
- 依存パッケージ更新
- マイコン書き込み

### 12.5 巻き戻し粒度

- 直前の操作だけ戻す
- セッション開始前へ戻す
- 任意チェックポイントへ戻す
- 特定API追加だけ戻す
- 特定UI変更だけ戻す
- 特定ワーカー定義だけ無効化する

---

## 13. MVP設計

### 13.1 最小構成

最初に作るべきMVPは以下。

- ユーザー認証
- チャットUI
- ユーザー別workspace
- Context DB
- API Catalog
- Tool Gateway
- Policy Engine
- Rollback Service
- Audit Log
- 情報オブジェクト管理
- 簡易SNSタイムライン
- 一時ワーカー起動基盤
- 既存API検索
- API化候補ログ

### 13.2 MVPで扱う初期タスク

初期タスクは重すぎないものに絞る。

- タスク管理ページ生成
- 投稿/コメント/タグ付け
- ファイルアップロードと要約
- 画像リサイズAPI
- PDFテキスト抽出API
- ユーザー指定フィード生成
- 簡易UIビュー生成

### 13.3 MVPで避けるべきもの

初期段階では以下を避ける。

- 本番サーバ直接改修
- 自由なshell実行
- 無制限外部通信
- 決済
- メール自動送信
- マイコン自動書き込み
- OS深部連携
- 自動デプロイ

---

## 14. 将来拡張

### Phase 1: Webアプリ

- ブラウザ上で動作
- ユーザー別ワークスペース
- チャット入口
- Context DB
- 動的UI/API/ワーカー

### Phase 2: PWA

- Web Push通知
- File System Access API
- オフラインキャッシュ
- ホーム画面追加

### Phase 3: デスクトップ補助アプリ

- ローカルファイル連携
- Git操作
- IDE連携
- ローカルビルド

### Phase 4: ローカルエージェント

- ローカルLLM
- ローカル検索インデックス
- スクリーンショット解析
- クリップボード連携
- ローカルアプリ起動

### Phase 5: OS統合

- 通知
- ファイルシステム
- カメラ/マイク
- デバイス制御
- バックグラウンドジョブ
- NPU/ローカル推論

OS連携は強力だが危険度も高い。Webアプリで安全設計を固めてから進むべきである。

---

# 15. 既存例調査

## 15.1 既存例の分類

本構想に近い既存例は、単独カテゴリではなく以下の複合である。

1. AIアプリビルダー
2. コーディングエージェント
3. クラウド型開発エージェント
4. マルチエージェント基盤
5. カスタムSNSフィード
6. エージェント用スキル/ツール拡張
7. ロールバック/サンドボックス付き開発基盤

完全一致する既存例は見当たらない。特に「ユーザーごとにSNS形態、UI、API、ワーカーを動的に自己設計するスーパーアプリ基盤」は、複数領域を横断した構想である。

---

## 15.2 OpenAI Codex / Codex Cloud

OpenAI Codexは、コードを読み、編集し、実行できるコーディングエージェントである。Codex Cloudでは、クラウド環境でバックグラウンドタスクを並列実行できる。公式ドキュメントでは、Codex Cloudタスクはコンテナを作成し、指定されたリポジトリのブランチまたはコミットをチェックアウトして実行されると説明されている。また、セットアップ時のインターネットアクセスと、エージェント実行時のインターネットアクセス制御が分離されている。

関連点:

- クラウド上でエージェントがコードを変更する
- コンテナ環境で実行する
- 並列タスクを委任できる
- CLIやIDEからクラウドタスクを起動できる
- Agent Skillsによりタスク固有能力を追加できる

本構想との違い:

- Codexは主にコード開発支援が中心
- ユーザー別スーパーアプリ生成基盤ではない
- SNS/UI/API/Context DB/ワーカー生成を統合する設計ではない
- API要否判断やSNSフィード設計までは主目的ではない

参考:

- OpenAI Codex Cloud: https://developers.openai.com/codex/cloud
- Codex Cloud environments: https://developers.openai.com/codex/cloud/environments
- Codex CLI: https://developers.openai.com/codex/cli
- Agent Skills: https://developers.openai.com/codex/skills

---

## 15.3 Claude Code / Claude Agent SDK

Claude Codeは、ターミナル上で動作するエージェント型コーディングツールである。公式ドキュメントでは、サブエージェント、hooks、permissions、MCP、sessions、skillsなどを扱える。カスタムサブエージェントは、カスタムプロンプト、ツール制限、権限モード、hooks、skillsを持てる。

関連点:

- サブエージェント
- ツール制限
- 権限管理
- hooksによる決定論的制御
- MCP連携
- セッション管理
- Agent SDKによる組み込み

本構想との違い:

- Claude Codeは開発者向けCLI/SDK寄り
- ワーカー定義はオーケストレーターが完全動的に作るというより、設定されたサブエージェントを活用する設計に近い
- SNS/スーパーアプリ/自己設計UIの中核基盤ではない

参考:

- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code hooks guide: https://docs.anthropic.com/en/docs/claude-code/hooks-guide
- Claude Code hooks reference: https://docs.anthropic.com/en/docs/claude-code/hooks
- Claude Agent SDK: https://docs.anthropic.com/en/docs/claude-code/sdk
- Claude Code settings: https://docs.anthropic.com/en/docs/claude-code/settings

---

## 15.4 GitHub Copilot Coding Agent

GitHub Copilot coding agentは、リポジトリを調査し、実装計画を作成し、ブランチ上でコード変更を行い、差分レビューやPull Request作成へつなげられる。

関連点:

- リポジトリ調査
- 実装計画
- ブランチ上の変更
- PRレビュー
- 人間によるマージ判断

本構想との違い:

- 開発ワークフロー中心
- ユーザーごとのアプリ自己拡張基盤ではない
- SNS/UI/API/ワーカー/Context DBの統合設計ではない

参考:

- GitHub Copilot coding agent: https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent
- GitHub Copilot docs: https://docs.github.com/copilot

---

## 15.5 Lovable

Lovableは、自然言語でWebアプリを構築・反復・デプロイするフルスタックAI開発プラットフォームである。公式ドキュメントでは、自然言語でフルスタックアプリを作り、AI機能も組み込めると説明されている。また、Lovable APIではプロンプトや画像からアプリ生成を開始できる。

関連点:

- 自然言語によるフルスタックアプリ生成
- AI機能の組み込み
- アプリ生成API
- デプロイまで含む

本構想との違い:

- Lovableはアプリを「作る」プラットフォーム
- 本構想はアプリの中に、自己拡張・API生成・ワーカー生成・SNSキュレーションを継続的に持たせる
- Context DBや巻き戻し隔離、ワーカー常時非稼働などのアーキテクチャが中核になる

参考:

- Lovable welcome: https://docs.lovable.dev/introduction/welcome
- Lovable AI features: https://docs.lovable.dev/integrations/ai
- Lovable API: https://docs.lovable.dev/integrations/lovable-api
- Lovable Build with URL: https://docs.lovable.dev/integrations/build-with-url

---

## 15.6 Replit Agent

Replitは、自然言語でWeb/モバイルアプリやサイトを作れるAI開発環境を提供している。公式サイトでは、Parallel Agentsにより複数タスクを同時に進められること、認証、DB、デザインを扱えることが示されている。

関連点:

- 自然言語でアプリ構築
- ホスティングまで統合
- Parallel Agents
- 認証、DB、デザインへの対応

本構想との違い:

- 開発環境/アプリビルダーとしての性格が強い
- ユーザー自身のWebアプリが内部で自己拡張し続ける設計とは異なる
- SNSフィードの自己設計やContext DBによる個人OS化は主目的ではない

参考:

- Replit official: https://replit.com/

---

## 15.7 Bolt.new

Bolt.newは、ブラウザ上でプロンプトからフルスタックアプリを生成・実行・編集・デプロイできるAI開発エージェントである。GitHub上の説明では、ローカル環境なしでブラウザ上からフルスタックアプリを構築できるとされている。

関連点:

- ブラウザ内フルスタック開発
- プロンプトからアプリ生成
- 実行・編集・デプロイ
- WebContainers系技術との親和性

本構想との違い:

- Boltは主にアプリ開発環境
- 本構想は完成後のアプリ自体が、ユーザーの要求で機能・UI・API・ワーカー・SNSを生成し続ける

参考:

- Bolt official: https://bolt.new/
- Bolt.new GitHub: https://github.com/stackblitz/bolt.new

---

## 15.8 Vercel v0

v0は、AIでフルスタックWebアプリを生成するVercelのAIビルダーである。公式サイトでは、DB、API、デプロイ、LLMを含めたエージェント的な構築が示されている。Vercelのブログでは、単一プロンプトからUI、コンテンツ、バックエンド、ロジックを含むアプリへ進めると説明されている。

関連点:

- UI生成
- フルスタック化
- DB/API/Deployとの統合
- エージェント的な計画・構築

本構想との違い:

- v0はアプリ生成・開発支援が中心
- 本構想はアプリ内部のオーケストレーターが、利用中にAPIやUIやワーカーを判断・生成する
- SNSフィード設計やユーザー固有Context DBは中核ではない

参考:

- v0 official: https://v0.app/
- v0.app announcement: https://vercel.com/blog/v0-app

---

## 15.9 LangGraph

LangGraphは、エージェントのdurable execution、streaming、human-in-the-loop、persistenceを扱うオーケストレーションランタイムである。公式ドキュメントでは、LangGraphは永続実行や状態保持に重点を置くランタイムとして説明されている。

関連点:

- エージェントオーケストレーション
- 状態永続化
- Human-in-the-loop
- 長時間実行
- 再開可能なワークフロー

本構想との関係:

- オーケストレーター/ワーカー/Context DB/人間承認/巻き戻しに近い実装基盤候補
- ただし、本構想のアプリ生成・SNS生成・API生成ポリシーそのものを提供するわけではない

参考:

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph GitHub: https://github.com/langchain-ai/langgraph

---

## 15.10 Microsoft Agent Framework / AutoGen

Microsoft Agent Frameworkは、AutoGenとSemantic Kernelの後継的な位置づけとして、単一・マルチエージェントパターン、セッションベース状態管理、型安全性、フィルター、テレメトリ、モデル/embedding対応を統合するものと説明されている。AutoGenはイベント駆動のマルチエージェントAIシステム構築フレームワークとして使われてきた。

関連点:

- マルチエージェント
- セッション状態管理
- イベント駆動
- ツール利用
- 人間参加型ワークフロー
- テレメトリ

本構想との関係:

- 動的ワーカーやオーケストレーション基盤の参考になる
- ただし、スーパーアプリ自己拡張、SNS UI自己設計、API要否判断までを内包する製品ではない

参考:

- Microsoft Agent Framework overview: https://learn.microsoft.com/en-us/agent-framework/overview/
- AutoGen docs: https://microsoft.github.io/autogen/stable//index.html

---

## 15.11 CrewAI

CrewAIは、複数のAIエージェントを編成し、タスクを処理するフレームワークである。公式サイトでは、エージェント導入を支援するオープンプラットフォームとして説明されている。

関連点:

- 複数エージェント
- Crew/Flow型のワークフロー
- エージェント運用
- 企業向け管理

本構想との関係:

- ワーカー管理・タスク分解の実装候補
- ただし、動的API生成や自己設計SNSを中核にしたスーパーアプリ基盤そのものではない

参考:

- CrewAI official: https://crewai.com/
- CrewAI docs: https://docs.crewai.com/

---

## 15.12 OpenHands

OpenHandsは、ソフトウェア開発向けのオープンソースAIエージェントプラットフォームである。コードベースに対する実作業を行い、計画、コード作成、変更適用などを支援する。

関連点:

- オープンソース
- ソフトウェア開発エージェント
- ローカル/クラウド実行
- コード変更
- PR/Issue連携

本構想との違い:

- コーディングエージェント用途が中心
- SNS/UI/API/Context DBを統合した個人化スーパーアプリ基盤ではない

参考:

- OpenHands official: https://openhands.dev/
- OpenHands GitHub: https://github.com/OpenHands/openhands

---

## 15.13 Bluesky / AT Protocol / Custom Feeds / Attie

SNS機能に関しては、BlueskyとAT Protocolが非常に参考になる。Blueskyはカスタムフィードにより、ユーザーや開発者が独自のアルゴリズムフィードを作れる。さらに2026年には、自然言語でカスタムフィードを作るAIアプリ「Attie」が報じられている。

関連点:

- ユーザー選択型アルゴリズム
- カスタムフィード
- アルゴリズムマーケットプレイス的発想
- 自然言語によるフィード作成
- atproto上のアプリ生成可能性

本構想との関係:

- 「SNSのUI/フィードをユーザーが自己設計する」という点で非常に近い
- 本構想はさらに、UI生成、API生成、ワーカー生成、スーパーアプリ化まで広げる

参考:

- Bluesky official: https://bsky.app/
- The Verge: Bluesky Attie AI custom feeds, 2026-03-29
- Wired: Bluesky custom algorithms, 2023
- Paper Skygest: Personalized Academic Recommendations on Bluesky, 2026
- Designing Usable Controls for Customizable Social Media Feeds, 2025

---

## 15.14 研究動向: AI Coding Agents

2026年時点で、AIコーディングエージェントのGitHub Pull Requestに関する研究が増えている。AIDevデータセットは、OpenAI Codex、GitHub Copilot、Devin、Cursor、Claude Codeによる大量のAgentic PRを集め、AIエージェントが実際のOSS開発に与える影響を分析している。

関連研究の示唆:

- AIエージェントは実際にPRを作成し始めている
- 人間によるマージ承認は依然として重要
- タスク種別により成功率が異なる
- ドキュメント修正や定型修正は成功しやすい
- 新機能・構造変更は難易度が高い
- エージェントごとの行動特性がある

本構想への示唆:

- 本番反映は人間承認を残すべき
- タスク種別ごとにモデル/ワーカー/API化戦略を変えるべき
- 監査ログと変更差分は必須
- ワーカーごとの成功率・失敗率・コストを記録すべき

参考:

- AIDev: Studying AI Coding Agents on GitHub, 2026
- Comparing AI Coding Agents, 2026
- How AI Coding Agents Modify Code, 2026
- Collaborator or Assistant?, 2026

---

# 16. 既存例との比較表

| 項目 | 本構想 | Codex | Claude Code | Copilot Agent | Lovable | Replit | Bolt | v0 | LangGraph/Agent FW | Bluesky/Attie |
|---|---|---|---|---|---|---|---|---|---|---|
| 自然言語で機能追加 | ◎ | ○ | ○ | ○ | ◎ | ◎ | ◎ | ◎ | △ | △ |
| Webアプリ自体が自己拡張 | ◎ | △ | △ | △ | ○ | ○ | ○ | ○ | △ | △ |
| UI自己設計 | ◎ | △ | △ | △ | ○ | ○ | ○ | ◎ | × | ○ |
| API自動生成 | ◎ | △ | △ | △ | ○ | ○ | ○ | ○ | △ | △ |
| API要否判断 | ◎ | △ | △ | △ | △ | △ | △ | △ | △ | × |
| 動的ワーカー生成 | ◎ | △ | ○ | △ | △ | △ | △ | △ | ○ | △ |
| ワーカー非常駐 | ◎ | ○ | ○ | ○ | 不明 | 不明 | 不明 | 不明 | ○ | 不明 |
| Context DB中心設計 | ◎ | △ | ○ | △ | △ | △ | △ | △ | ○ | △ |
| SNSフィード自己設計 | ◎ | × | × | × | × | × | × | × | × | ◎ |
| 巻き戻し隔離 | ◎ | ○ | ○ | ○ | △ | △ | △ | △ | △ | × |
| ユーザー別スーパーアプリ化 | ◎ | × | × | × | △ | △ | △ | △ | × | △ |

凡例: ◎ 中核機能 / ○ 近い機能あり / △ 部分的 / × 主目的ではない

---

# 17. 本構想の独自性

本構想の独自性は、単一の新技術ではなく、以下を一つのアプリ基盤として統合する点にある。

1. チャットを入口にした自己拡張Webアプリ
2. ユーザーごとの隔離ワークスペース
3. オーケストレーターによるAPI要否判断
4. オーケストレーターによる動的ワーカー定義
5. ワーカーの非常駐・呼び出し時実行
6. 小型/中型/大型LLMの使い分け
7. Context DBによる文脈継承
8. APIカタログによる再利用
9. SNSフィード/表示思想の自己設計
10. 巻き戻し機能の隔離
11. Tool GatewayとPolicy Engineによる安全制御
12. 安定処理のAPI化によるトークン削減

既存例はそれぞれ一部を持っているが、これらを「ユーザーごとに育つスーパーアプリ基盤」として統合する例は、現時点では明確には見当たらない。

---

# 18. 技術スタック案

## 18.1 MVP向け

- Frontend: Next.js / React
- Backend: FastAPI or NestJS
- DB: PostgreSQL + JSONB + pgvector
- Queue: Redis Queue / BullMQ / Celery
- Object Storage: S3互換 / MinIO
- Auth: Auth.js / Keycloak / Supabase Auth
- Container: Docker
- Sandbox: Docker container per workspace
- Git管理: branch / changeset / patch
- LLM Gateway: OpenAI / Anthropic / local model wrapper
- Tool Gateway: 独自API
- Policy Engine: OPA / Cedar / 独自RBAC+ABAC
- Audit Log: append-only table
- Rollback: snapshot + event log + Git

## 18.2 将来拡張

- LangGraph: durable agent workflow
- Microsoft Agent Framework: enterprise multi-agent orchestration
- MCP: 外部ツール接続
- WebContainer系: ブラウザ内実行環境
- Local LLM: llama.cpp / Ollama等
- Desktop bridge: Tauri / Electron
- OS連携: ネイティブ補助エージェント

---

# 19. 実装上の最重要ポイント

1. LLMにroot権限を渡さない
2. 本番環境を直接触らせない
3. ワーカーは短命にする
4. 文脈はContext DBに保存する
5. API化判断をログで支える
6. APIカタログを必ず持つ
7. 巻き戻し機能はLLMから隔離する
8. シークレットをLLMに見せない
9. 破壊的変更の前に自動チェックポイントを作る
10. 変更単位をChangeSetとして扱う
11. SNS推薦ロジックをユーザーに明示する
12. 人間承認ポイントを残す

---

# 20. グランドデザイン追記：DevOpsの民主化としてのAgentForge

## 20.1 コンテスト向けの主題

本構想を DevOps × AI Agent Hackathon に応募する場合、前面に出すべき主題は「スーパーアプリそのもの」ではなく、以下である。

```text
AgentForge:
DevOpsの民主化を実現する、自己拡張型AIエージェント基盤
```

この場合、スーパーアプリは応募作品そのものではなく、AgentForgeの能力を示す実例である。すなわち、以下の二層構造として説明する。

```text
応募作品の本体:
  AgentForge = 自然言語でアプリを成長させるDevOps AI Agent Workbench

デモ題材:
  Personal Super App = AgentForge上で生成・拡張されるスーパーアプリ例
```

ピッチ上の主語は常に AgentForge とし、スーパーアプリは「AgentForgeによって育てられる題材」として扱う。これにより、単なる多機能アプリではなく、AIエージェントが開発・運用・改善・巻き戻しを担うDevOps基盤として評価されやすくなる。

## 20.2 DevOpsの民主化という体験価値

通常のDevOpsは、開発者や運用者が担う専門工程である。

```text
要件整理
↓
設計
↓
実装
↓
テスト
↓
デプロイ
↓
監視
↓
改善
↓
障害対応・巻き戻し
```

AgentForgeでは、この流れを一般ユーザーの自然言語操作へ変換する。

```text
ユーザー:
  「タスク管理を追加して」
  「投稿フィードを作って」
  「PDFメモを足して」
  「今の変更を戻して」

AgentForge:
  要件整理、設計、実装、テスト、デプロイ、監視、巻き戻しを裏側で実行
```

つまり本構想の体験価値は、以下の一文に集約できる。

```text
自然言語でアプリを育てる。
その裏側ではAIがDevOpsを回す。
```

この意味で、AgentForgeは「DevOpsの民主化」を実現する基盤である。ユーザーはDevOpsという言葉を知らなくても、アプリを継続的に改善し、動かし、戻し、育てる体験に参加できる。

---

# 21. レイヤ構造：コア機能・生成機能・外部機能・管理機能

## 21.1 4層構造

本システムは、責務と安全性を明確にするために、以下の4層に分ける。

```text
1. Core Agent Layer
   自己拡張能力そのものを提供する中核

2. Generated App Layer
   ユーザーごとに後から生成される個別機能

3. External Capability Layer
   外部サーバ・共有データ・他ユーザーとの通信が必要な機能

4. Management / Billing Layer
   サービス提供者側の認証・契約・課金・利用制限・管理機能
```

この分類により、AIエージェントが自由に改変できる範囲と、改変させてはいけない範囲を分ける。

## 21.2 Core Agent Layer

Core Agent Layer は、AgentForgeの最小MVPであり、ユーザーの自然言語指示を受けて、アプリを自己拡張するための基盤である。

```text
Core Agent Layer
├─ Chat UI
├─ Reception Agent
├─ Orchestrator
├─ Task State DB
├─ Context DB
├─ Worker Registry
├─ API Catalog
├─ Tool / API Gateway
├─ Policy Engine
├─ Rollback Service
└─ Audit Log
```

この層は安定性が最優先である。生成機能が壊れても復旧できるが、Core Agent Layerが壊れると自己拡張・巻き戻し・進捗説明ができなくなる。

## 21.3 Generated App Layer

Generated App Layer は、Core Agent Layerによって後から作られる機能群である。

```text
Generated App Layer
├─ タスク管理
├─ メモ
├─ プロジェクトフィード
├─ PDF / 論文メモ
├─ 画像アップロード
├─ ダッシュボード
├─ 検索画面
├─ SNSビュー
├─ リコメンドUI
└─ ユーザー固有の業務機能
```

この層は、ユーザーごと・プロジェクトごとに異なってよい。壊れる可能性を前提に、ChangeSet、Audit Log、Rollbackで管理する。

## 21.4 External Capability Layer

External Capability Layer は、アプリ単体では成立しない外部機能である。代表例はSNS、通知、Webhook、外部API接続である。

```text
External Capability Layer
├─ Social Data Layer
├─ Notification Service
├─ Webhook Service
├─ 外部API Connector
├─ 共有ストレージ
├─ 共同編集基盤
└─ 公開API
```

この層の操作は、他ユーザーや外部世界に影響するため、Core Agent Layerから直接操作させない。必ず External Service Gateway を通す。

```text
Orchestrator / Workers
↓
External Service Gateway
↓
SNS / Notification / Webhook / External APIs
```

外部公開、通知、メール、SNS投稿、Webhook呼び出しなどは完全な巻き戻しができない場合がある。そのため、内部変更よりも強い承認ゲートを置く。

## 21.5 Management / Billing Layer

Management / Billing Layer は、このシステムをサービスとして利用させるための運営基盤である。

```text
Management / Billing Layer
├─ 認証
├─ ユーザー管理
├─ 契約プラン管理
├─ 課金管理
├─ 使用量計測
├─ AI利用量管理
├─ 自作API / CPU利用量管理
├─ ストレージ使用量管理
├─ SNS利用枠管理
├─ Marketplace売上管理
├─ 管理者画面
├─ 利用停止・制限
└─ 管理監査ログ
```

この層は、ユーザーのAIエージェントに改変させてはいけない。課金ロジック、管理者権限、認証、契約、使用量ログ、請求履歴は固定システムとして扱う。

```text
AIが自由に生成してよい:
  - ユーザーごとの画面
  - ユーザーごとのAPI
  - プロジェクト固有ワーカー
  - フィード表示
  - 業務機能

AIが勝手に変えてはいけない:
  - 課金ロジック
  - 契約プラン
  - 認証処理
  - 決済API
  - 管理者権限
  - 使用量制限
  - 請求履歴
```

---

# 22. エージェント構成の詳細設計

## 22.1 オーケストレーターの責務

オーケストレーターは、APIやUIを直接作る存在ではない。判断・調停・計画・統合を行う現場監督である。

```text
Orchestrator
├─ ユーザー要求の理解
├─ 要件分解
├─ API作成可否の判断
├─ UI設計要否の判断
├─ 外部機能利用可否の判断
├─ 課金・利用枠の確認
├─ 必要ワーカーの選定
├─ 作業命令書の作成
├─ Policy Engineへの権限申請
├─ ワーカー結果の統合
├─ 次工程判断
└─ ユーザーへの最終説明
```

オーケストレーターが作るのはコードではなく、以下のような作業命令書である。

```json
{
  "task_id": "task_123",
  "goal": "タスク管理機能を追加する",
  "plan": [
    {
      "step": 1,
      "worker": "ui_designer",
      "instruction": "タスク管理画面の情報設計を行う"
    },
    {
      "step": 2,
      "worker": "api_designer",
      "instruction": "Task APIとデータ構造を設計する"
    },
    {
      "step": 3,
      "worker": "programmer",
      "instruction": "APIとUIを実装する"
    },
    {
      "step": 4,
      "worker": "test_agent",
      "instruction": "テストを生成・実行する"
    },
    {
      "step": 5,
      "worker": "devops_agent",
      "instruction": "Cloud Runへのデプロイ計画を作成する"
    }
  ],
  "rollback_required": true,
  "approval_required_before_external_publish": true
}
```

## 22.2 受付係エージェント

長時間作業中にユーザー対応が止まることは許されない。そのため、Reception Agentを設ける。

```text
Reception Agent
├─ ユーザーからの即時問い合わせ対応
├─ 現在の作業状況説明
├─ 進捗確認
├─ 作業中断受付
├─ 優先度変更受付
├─ 追加指示受付
├─ 承認要求の提示
├─ エラー状況説明
└─ 必要時にオーケストレーターへ取り次ぎ
```

ユーザーが「進捗どうですか」と聞いた場合、受付係はTask State DBやAudit Logを読み、即答する。

```text
例:
現在は「Task APIの実装」が完了し、UIプログラマーが画面コンポーネントを生成中です。
次の工程はテスト実行です。直近のエラーはありません。
```

受付係は大型LLMである必要はない。軽量LLM、テンプレート生成、ルールベースでもよい。重要なのは、作業ワーカーの実行中でもユーザーとの対話経路が塞がらないことである。

## 22.3 専門ワーカー群

実装作業は専用ワーカーが担当する。

```text
Worker Agents
├─ Product Planner
├─ UI Designer
├─ UX Reviewer
├─ API Designer
├─ Programmer
├─ UI Programmer
├─ Backend Programmer
├─ Test Agent
├─ DevOps Agent
├─ Security / Policy Reviewer
├─ Recommendation Designer
└─ Documentation Agent
```

### UI Designer

UI Designerは「どう見せるか」を設計する。

```text
UI Designer
├─ 情報設計
├─ 画面構成
├─ ユーザー導線
├─ コンポーネント構成
├─ 表示優先順位
├─ レスポンシブ方針
└─ UI仕様書の出力
```

UI Designerはコードを書かない。出力はUI仕様である。

### Programmer

Programmerは実装担当である。

```text
Programmer
├─ API実装
├─ UI実装
├─ DB接続
├─ 状態管理
├─ エラーハンドリング
├─ テストコード作成
└─ ビルドエラー修正
```

### DevOps Agent

DevOps Agentは、作って終わりにしないための運用担当である。

```text
DevOps Agent
├─ テスト実行
├─ ビルド
├─ Cloud Build連携
├─ Cloud Runデプロイ
├─ Cloud Logging確認
├─ 障害原因調査
├─ Rollback候補作成
└─ デプロイ後確認
```

## 22.4 非同期実行と進捗管理

重い作業は同期レスポンスで実行しない。Task Queueへ投入し、ワーカーが非同期に処理する。

```text
ユーザー指示
↓
Reception Agentが受理
↓
Orchestratorが作業計画を作成
↓
Task Queueへ投入
↓
各Workerが実行
↓
Task State DBへ進捗を書き込む
↓
Reception Agentがいつでも説明可能
```

進捗管理には以下のテーブル/コレクションを用意する。

```text
task_runs
├─ task_id
├─ user_id
├─ project_id
├─ status
├─ current_step
├─ assigned_worker
├─ started_at
├─ updated_at
├─ progress_message
├─ last_error
├─ next_action
├─ cancel_requested
└─ approval_required

worker_runs
├─ worker_run_id
├─ task_id
├─ worker_type
├─ model
├─ status
├─ input_context_refs
├─ output_refs
├─ tool_calls
├─ token_usage
├─ started_at
├─ completed_at
└─ summary
```

---

# 23. SNS外部機能の設計：Social Data LayerとExperience Layerの分離

## 23.1 SNSは外部機能として扱う

SNSは外部サーバなしでは本質的に成立しない。

```text
SNSに必要なもの
├─ 投稿保存
├─ コメント保存
├─ リアクション保存
├─ フォロー関係
├─ 公開範囲管理
├─ 検索
├─ インデックス
├─ 通知
└─ 複数ユーザー間の共有
```

したがって、SNSはGenerated App Layerではなく、External Capability Layerの一部として設計する。

## 23.2 Social Data Layer

SNS基盤は固定UIを持つ完成SNSではなく、情報を蓄え、検索し、関係を管理するSocial Data Layerである。

```text
Social Data Layer
├─ SocialObject保存
├─ User Relation保存
├─ Comment保存
├─ Reaction保存
├─ Tag保存
├─ Visibility管理
├─ Search Index
├─ Vector Index
├─ Feed Source API
└─ Audit Log
```

SocialObjectは、単なる投稿ではなく、スーパーアプリ上のあらゆる情報を流通可能にする汎用オブジェクトである。

```text
SocialObject
├─ object_id
├─ owner_user_id
├─ type
│  ├─ post
│  ├─ memo
│  ├─ task
│  ├─ image
│  ├─ pdf_note
│  ├─ code_snippet
│  ├─ project_update
│  └─ external_link
├─ body
├─ attachments
├─ tags
├─ embedding
├─ visibility
├─ created_at
├─ updated_at
├─ relations
└─ metadata
```

## 23.3 Experience Layer

SNSのUIや推薦ロジックはSocial Data Layerではなく、ユーザー側のGenerated App Layerで作る。

```text
Social Data Layer:
  情報を保存し、検索し、APIで返す

Experience Layer:
  どう見せるか、どう並べるか、何を推薦するかを決める
```

同じSocial Data Layerを使って、以下のような体験を生成できる。

```text
X風:
  短文タイムライン

Reddit風:
  スレッド・サブコミュニティ

Discord風:
  チャンネル・会話部屋

研究者向け:
  論文カード・引用関係・要約

開発者向け:
  Issue・PR・変更ログ

創作者向け:
  画像ギャラリー・制作記録
```

## 23.4 リコメンドロジックも生成対象

リコメンドロジックは固定しない。ユーザーの目的に応じて、オーケストレーターとRecommendation Designerが設計する。

```text
深掘りモード:
  類似投稿を優先
  同一タグを優先
  近いユーザーを優先
  ノイズを減らす

視野拡張モード:
  反対意見を混ぜる
  異分野の類似構造を出す
  海外圏の情報を翻訳して混ぜる
  普段見ないクラスタを一定割合入れる
```

この分離により、SNSは固定されたタイムラインではなく、ユーザーごとに設計可能な情報体験になる。

---

# 24. 課金・管理・マーケットプレイス設計

## 24.1 課金の基本単位

課金要素は以下の4系統に分ける。

```text
1. AI利用料
2. 自作API / ワーカー実行料
3. 外部機能利用料
4. サブシステム販売・流通手数料
```

AI利用料と自作API/CPU利用料がベースになる。

```text
AI利用料:
  Gemini等のAI推論に使ったトークン・画像入力・長時間推論

Compute利用料:
  自作API実行、ワーカー実行、Cloud Run実行、DB読み書き、インデックス作成

Storage利用料:
  Context DB、アップロードファイル、生成物、Rollbackスナップショット

External利用料:
  SNS、通知、Webhook、外部公開API
```

## 24.2 無料枠の位置づけ

無料枠は、リテラシーのない人でも「自然言語でアプリが育つ」体験を試せるようにするためのオンボーディング手段である。

```text
無料枠の目的
├─ APIキーなしで始められる
├─ サービス側AIを少量使える
├─ 基本チャットを体験できる
├─ 基本SNS UIを使える
├─ 小さな機能追加を試せる
├─ 小規模Context DBを使える
└─ 有料化・開発者利用・マーケット参加へ進ませる
```

無料枠は節約手段ではなく、導入体験である。

## 24.3 サービス側AIと無料枠

無料ユーザーは、サービス側が提供するAIを少量利用できる。

```text
Free Plan
├─ 基本チャット
├─ 受付係の軽量応答
├─ 少量AIトークン
├─ 基本SNS UI閲覧
├─ 少量SNS投稿
├─ 小規模プロジェクト
├─ 自作API少量実行
├─ 小容量ストレージ
└─ 短期Rollback
```

本格利用では、AIトークン、ワーカー実行、CPU、ストレージ、外部機能利用に応じて課金する。

## 24.4 BYOK / BYOM / BYOLLMの位置づけ

将来的には、ユーザー自身のAI API契約やローカルLLMを接続できるようにする。

```text
BYOK:
  Bring Your Own Key
  ユーザー自身のクラウドAI APIキーを使う

BYOM:
  Bring Your Own Model
  ユーザー自身のAI Providerやモデルを使う

BYOLLM:
  Bring Your Own Local LLM
  Ollama、llama.cpp、LM Studio、vLLM、社内LLM等を接続する
```

この場合、AI推論費はユーザー側が負担するため、サービス側AIの無料枠は付与しない。

```text
BYOK / BYOM / BYOLLMユーザー:
  - 無料AI枠なし
  - AI推論費はユーザー負担
  - Context DB、自作API、ワーカー実行基盤、ストレージ、SNS基盤、Rollback保持は課金対象
```

ただし、コンテスト版ではGoogleサービス活用を明確にするため、これらはコンテスト後の拡張計画とする。

## 24.5 Model Gateway構想

コンテスト後には Model Gateway を導入する。

```text
Worker / Orchestrator
↓
Model Gateway
├─ Service AI
├─ Gemini API
├─ ユーザー持ち込みAI API
├─ Ollama
├─ llama.cpp server
├─ vLLM
├─ LM Studio
├─ LocalAI
└─ 社内LLM endpoint
```

各モデルには能力プロファイルを持たせる。

```text
model_capabilities
├─ max_context
├─ supports_json_schema
├─ supports_tool_calling
├─ coding_score
├─ reasoning_score
├─ vision_support
├─ latency
├─ cost
└─ privacy_level
```

オーケストレーターは、この能力プロファイルを見て、タスクごとにモデルを選択する。

## 24.6 サブシステム販売モデル

ユーザーが作った機能群を、他ユーザーへ販売できるようにする。これにより、AgentForgeはAIエージェント基盤であると同時に、サブシステム流通プラットフォームになる。

```text
販売できるもの
├─ タスク管理サブシステム
├─ 論文管理サブシステム
├─ 画像整理サブシステム
├─ マイコン開発支援サブシステム
├─ SNSフィードテンプレート
├─ リコメンドロジック
├─ UIテーマ
├─ APIセット
├─ ワーカー定義
├─ 業務テンプレート
└─ DevOpsパイプライン設定
```

販売モデルは複数考えられる。

```text
販売モデル
├─ 買い切り
├─ 月額サブスク
├─ 利用回数課金
├─ API実行量課金
├─ ワーカー実行量課金
├─ チーム単位ライセンス
└─ 収益分配
```

プラットフォームは以下で収益を得る。

```text
プラットフォーム収益
├─ 売上手数料
├─ 実行時基盤利用料
├─ 決済手数料上乗せ
├─ 有料掲載
├─ 認証・審査料
└─ Team / Organization向け管理機能
```

## 24.7 サブシステム配布時の安全表示

他人が作ったサブシステムを使うため、権限表示と審査が必要である。

```text
配布時に表示すべき情報
├─ 必要権限
├─ 使用するAPI
├─ 外部通信の有無
├─ 想定AIトークン使用量
├─ Compute使用量
├─ データアクセス範囲
├─ 作成者
├─ バージョン
├─ 変更履歴
├─ セキュリティ審査状態
└─ 返金/停止ルール
```

これはスマートフォンアプリの権限表示に近いが、AIワーカー、Context DB、外部API、SNS投稿、課金要素まで含む点が異なる。

---

# 25. Google Cloud中心のハッカソン版とコンテスト後ロードマップ

## 25.1 ハッカソン版の方針

ハッカソン版では、Google Cloud / Gemini / ADK 中心に寄せる。ローカルLLMや他社APIキー持ち込みは自由度として魅力的だが、Googleサービス活用という評価軸をぼかすため、コンテスト後の計画に回す。

```text
AgentForge Hackathon Edition
├─ Gemini API
├─ ADK
├─ Cloud Run
├─ Cloud Run Jobs
├─ Firestore
├─ Firestore Vector Search / Vertex AI Vector Search
├─ Cloud Storage
├─ Cloud Build
├─ Artifact Registry
├─ Cloud Logging
├─ Secret Manager
└─ IAM
```

## 25.2 Googleサービスの役割

```text
Gemini API:
  オーケストレーター、UIデザイナー、プログラマー、要約、ログ解析

ADK:
  エージェント構成、ツール呼び出し、ワーカー管理

Cloud Run:
  Webアプリ、Orchestrator API、Tool Gateway、Reception Agent

Cloud Run Jobs:
  一時ワーカー実行

Firestore:
  Context DB、Task State DB、Worker Registry、API Catalog、Audit Log

Vector Search:
  既存API検索、過去タスク検索、文脈検索、SNS検索

Cloud Storage:
  アップロードファイル、生成物、Rollbackスナップショット

Cloud Build:
  テスト、ビルド、デプロイ検証

Cloud Logging:
  実行ログ、エラー解析、運用エージェント入力

Secret Manager / IAM:
  シークレット保護、権限制御
```

## 25.3 ハッカソン版MVP

ハッカソン版のMVPは「完成済みスーパーアプリ」ではない。MVPは、チャット窓口から自己拡張サイクルを開始できるコア基盤である。

```text
MVP = Core Agent Layer
  - Chat UI
  - Reception Agent
  - Orchestrator
  - Task State DB
  - Context DB
  - Worker呼び出し
  - Tool / API Gateway
  - Rollback / Audit Log
```

プレゼンでは、このMVP上で生成された実例として、以下を見せる。

```text
生成された実例
├─ タスク管理
├─ プロジェクトフィード
├─ PDF / メモ登録
└─ SNS風ビュー
```

重要なのは、追加機能そのものではなく、それらがCore Agent Layerによって生成・実装・反映されたことを示すことである。

## 25.4 デモシナリオ

```text
初期状態:
  チャット窓口だけの最小アプリ

ユーザー指示:
  「タスク管理機能を追加して」

AgentForge:
  1. Reception Agentが受理
  2. Orchestratorが作業計画を作成
  3. UI Designerが画面設計
  4. API DesignerがAPI仕様作成
  5. Programmerが実装
  6. Test Agentが検証
  7. DevOps AgentがCloud Run反映
  8. Audit Logに記録
  9. Rollbackポイントを保存

ユーザー:
  「進捗どうですか？」

Reception Agent:
  Task State DBを見て即時説明

ユーザー:
  「この変更を戻して」

Rollback Service:
  直前ChangeSetを復旧
```

## 25.5 コンテスト後ロードマップ

```text
Phase 1: Hackathon Edition
  Google Cloud / Gemini中心で自己拡張サイクルを実証

Phase 2: Model Gateway
  モデル抽象化層を導入

Phase 3: BYOK
  ユーザー持ち込みAI APIキー対応

Phase 4: BYOLLM / Local Bridge
  Ollama、llama.cpp、LM Studio、社内LLMへの接続

Phase 5: Social Data Layer拡張
  SNS基盤、検索、公開範囲、カスタム推薦を強化

Phase 6: Marketplace
  ユーザー作成サブシステム販売、手数料、権限審査

Phase 7: Desktop / Local Agent
  ローカルファイル、OS通知、ローカルLLM、デバイス連携

Phase 8: OS統合
  ファイルシステム、通知、クリップボード、ローカルアプリ起動、デバイス制御との深い連携
```

---

# 26. 更新後の一文要約

本構想は、最初から多機能なスーパーアプリを作るものではない。最初に作るのは、チャット窓口、受付係、オーケストレーター、Context DB、ワーカー呼び出し、Tool Gateway、Rollbackを備えたCore Agent Layerである。このコア基盤が、必要に応じてUIデザイナー、プログラマー、DevOpsワーカー等を呼び出し、ユーザーの自然言語指示からスーパーアプリを段階的に生成・運用・改善していく。

SNSは固定UIを持つ完成機能ではなく、情報を蓄積・検索・インデックス化するSocial Data Layerとして外部機能に分離する。UIやリコメンドロジックはユーザー側の生成機能として作る。さらに、認証・課金・使用量管理・MarketplaceはManagement / Billing Layerとして分離し、AI生成対象から外す。

ハッカソン版ではGoogle Cloud / Gemini / ADK中心で実装し、ローカルLLMや他社APIキー持ち込みはコンテスト後のModel Gateway構想に回す。これにより、応募時はGoogleサービス活用を明確にしつつ、将来的にはBYOK、BYOLLM、Marketplace、OS連携へ拡張できる。


---

# 27. 結論

この構想は、現行のAIアプリビルダー、コーディングエージェント、マルチエージェントフレームワーク、カスタムSNSフィードの延長線上にあるが、それらを単純に足しただけではない。

本質は以下である。

```text
ユーザーが自然言語で意図を伝える
↓
オーケストレーターが既存API・Context DB・ワーカー定義を調べる
↓
足りなければワーカーを生成する
↓
繰り返し処理ならAPI化する
↓
必要ならUIを生成する
↓
SNSの見え方もユーザーに合わせて変える
↓
すべての変更は権限管理・監査・巻き戻しの下で実行する
```

これは、固定機能を持つスーパーアプリではなく、ユーザーごとに機能・UI・API・情報流通を自己拡張する「個人化されたアプリOS」に近い。

最初はWebアプリとして始めるのが妥当である。OS深部との統合は魅力的だが、権限と安全性の難易度が跳ね上がる。まずはWeb上で、Context DB、APIカタログ、動的ワーカー、巻き戻し、SNSビュー生成を成立させるのが現実的な第一歩である。

---

# 28. 参考URL一覧

## 公式・一次情報

- OpenAI Codex Cloud: https://developers.openai.com/codex/cloud
- OpenAI Codex Cloud environments: https://developers.openai.com/codex/cloud/environments
- OpenAI Codex CLI: https://developers.openai.com/codex/cli
- OpenAI Agent Skills: https://developers.openai.com/codex/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code hooks guide: https://docs.anthropic.com/en/docs/claude-code/hooks-guide
- Claude Code hooks reference: https://docs.anthropic.com/en/docs/claude-code/hooks
- Claude Agent SDK: https://docs.anthropic.com/en/docs/claude-code/sdk
- GitHub Copilot coding agent: https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent
- Lovable docs: https://docs.lovable.dev/introduction/welcome
- Lovable AI features: https://docs.lovable.dev/integrations/ai
- Lovable API: https://docs.lovable.dev/integrations/lovable-api
- Lovable Build with URL: https://docs.lovable.dev/integrations/build-with-url
- Replit: https://replit.com/
- Bolt: https://bolt.new/
- Bolt GitHub: https://github.com/stackblitz/bolt.new
- v0: https://v0.app/
- v0 announcement: https://vercel.com/blog/v0-app
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework/overview/
- AutoGen docs: https://microsoft.github.io/autogen/stable//index.html
- CrewAI: https://crewai.com/
- CrewAI docs: https://docs.crewai.com/
- OpenHands: https://openhands.dev/
- OpenHands GitHub: https://github.com/OpenHands/openhands
- Bluesky: https://bsky.app/

## 記事・研究

- The Verge, Bluesky Attie AI custom feeds, 2026-03-29
- Wired, Bluesky custom algorithms, 2023
- Paper Skygest: Personalized Academic Recommendations on Bluesky, 2026
- Designing Usable Controls for Customizable Social Media Feeds, 2025
- AIDev: Studying AI Coding Agents on GitHub, 2026
- Comparing AI Coding Agents, 2026
- How AI Coding Agents Modify Code, 2026
- Collaborator or Assistant?, 2026
- Dive into Claude Code, 2026

---

## 改定追記：実行時アーキテクチャ確定事項（コンテスト提出版 / 2026-06-08）

本書は最大ターゲット（自己拡張型スーパーアプリ基盤）の原構想。以下は、その構想をコンテスト提出版へ落とし込む際に確定した**実行時アーキテクチャ**であり、原構想のうち「モデルルーティング・Context DB・非常駐ワーカー・API化」の運用方針を具体化したもの。正準（最新）の定義は `IMPLEMENTATION_GUIDE.md` §2.5 に集約する。

### 1. 通信
- ブラウザ ↔ Reception は **REST/HTTPS**（Firebase Auth）。**MCPは採用しない**（MCPはエージェント↔ツール用。常駐接続はscale-to-zeroと衝突）。MCP化は将来拡張。
- 進捗・状態のライブ更新は、ブラウザが **Firestoreをリアルタイム購読**。

### 2. コスト（アイドル時 ≈ ¥0）
- 全エージェント非常駐、**Cloud Run scale-to-zero**。Workerは Cloud Tasks で必要時のみ起動。
- 理解・整理は**小型安価モデル（Flash / Flash-Lite）**、重い判断のみ上位モデル＝**モデルルーティング**（原構想§6の具体化）。

### 3. 生成機能の実行モデル（“生きた機能”）
生成機能は静的フォームにしない。**「境界LLM（小型）＋決定的API＋動的UI」**の三点セット。
- 骨格＝**決定的API**（CRUD、LLM不使用）。原構想§7「API化」の適用。
- 境界＝**小型LLM**：自然言語入力→構造化、出力は任意形式（`function calling`）。
- UI＝**動的manifest**（自然言語で再生成）。原構想§9「UI自己設計」の適用。
- **節約**：UIを変えない時はAPI直叩き。LLM不要な操作はLLMに通さない。

### 4. ワーカー非常駐＋コンテキスト永続化
- ワーカーは使用時のみ起動（原構想§2.3, §5）。文脈はワーカー内に持たせず **Firestore（Context DB）に永続化**（原構想§8）し、起動毎に `context_refs` で **rehydrate**。

### 5. API化 vs ワーカー化の判断
- **Orchestratorが判断**（原構想§4, §7）。安定・決定的→API化／自然言語I/O→境界LLM／継続的判断→専用ワーカー（非常駐）。ビルド時ワーカーは汎用・再利用。
