# AgentForge 実装手順書（コンテスト提出版 / ソロ・初級・最速）

作成日: 2026-06-08 ／ 提出締切: **2026-07-10 23:59**
関連: [要綱まとめ](agentforge_hackathon_contest_brief.md) ／ [公式原文](hackathon_official_source_record.md) ／ [設計仕様(audited)](agentforge_contest_submission_spec_audited.md)

---

## 0. この手順書の前提

- **対象ユーザー（1ペルソナ）**: 社内の非エンジニア業務担当者
- **課題**: 簡単な社内ツールを自分で作れず、毎回エンジニアへの開発依頼で待たされる
- **提供価値**: 自然言語で言うだけでアプリが機能を増やし、AIが裏でDevOps（設計→実装→デプロイ→承認→巻き戻し）を回す
- **最初の生成機能**: ①タスク管理（縦切り1本目）→ ②PDFメモ（2本目）。機能は後から増やせる設計にする
- **体制**: ソロ開発。**コード実装はClaudeが担当**。ユーザーは「人間にしかできない操作」のみ担当
- **AIエージェントの必然性（ピッチの核）**: 決め打ちCI/CDと違い、「曖昧な自然言語要求から、何を作りどう分解しどのワーカーに振るか」を**非決定的に判断**する必要があるからエージェントである

---

## 1. 役割分担（重要）

### 🧑 あなた（ユーザー）がやること = 人間にしかできない操作
- Google Cloud / Firebase コンソールでのプロジェクト作成・課金有効化・$300クーポン適用
- 各種 API の有効化（コンソールのボタン操作。コマンドは私が用意）
- 認証情報の取得とローカル設定（`gcloud auth`、Firebaseログイン等。手順は私が提示）
- GitHubリポジトリの作成（公開）とローカル接続
- 生成されたプロジェクトID・リージョン・キー等を私に共有
- 最終的なデモ動画の撮影、ProtoPedia登録、提出フォーム送信

### 🤖 私（Claude）がやること = それ以外すべて
- リポジトリ構成・全コード（フロント / バックエンド / エージェント / インフラ設定ファイル）の実装
- gcloud / firebase コマンドの作成（あなたはコピペ実行するだけ）
- Cloud Build / デプロイ設定、CI/CD 設定ファイルの作成
- デモ用シナリオ、アーキ図のテキスト、ProtoPediaストーリー草案の作成

> 原則: 私がコマンドとコードを用意し、あなたは「コンソールのクリック」と「コマンドのコピペ実行」と「結果の共有」をする。

---

## 2. 技術スタック（確定）

| レイヤ | 採用技術 | 備考 |
|---|---|---|
| フロント | React + Vite + TypeScript | Firebase Hosting配信。Chat/Progress/生成View/Approval |
| 認証 | Firebase Authentication | Googleログイン |
| バックエンド | Python 3.12 + FastAPI | Cloud Run |
| エージェント | Google ADK (Python) + Gemini API | Reception/Orchestrator/Workers |
| LLM | Gemini API（キーはSecret Manager） | 必須要件②を充足。Vertex経由は後で選択可 |
| DB | Firestore (native) | registry / task状態 / audit |
| 非同期 | Cloud Tasks → worker-runner | 「必要時起動」「進捗即応」を実演 |
| ストレージ | Cloud Storage | manifest / アップロード / snapshot |
| CI/CD | GitHub → Cloud Build → Cloud Run | 「まわす」を充足 |
| リージョン | asia-northeast1（東京） | |

### デプロイ単位（ソロ向けに最小化：Hosting + Cloud Run 2本）
1. **agentforge-web**（Firebase Hosting）
2. **agentforge-core-api**（Cloud Run）= reception / orchestrator / control-plane / tool-gateway / generated-app を**モジュール分離**して1サービスに同居
3. **agentforge-worker**（Cloud Run）= worker-runner（UI/API/Programmer等）。Cloud Tasksから起動

> 論理的には仕様書通りエージェント/層を分離（審査の「実運用への配慮」を満たす）が、デプロイは2サービスに集約して運用負荷を下げる。フル分離は提出後ロードマップ。

---

## 2.5 実行時アーキテクチャ（確定事項）

会話で固めた実行時の設計原則。実装は必ずこれに従う。

### 通信
- ブラウザ（Web Shell）↔ Reception は **REST/HTTPS**（Firebase Auth の ID token）。**MCPは使わない**（MCPはエージェント↔ツール用。常駐接続はscale-to-zeroと衝突）。
- 進捗・状態のライブ更新は、**ブラウザが Firestore をリアルタイム購読**（`task_runs` 等）。backendを起こし続けない。
- 操作（送信・承認・中止）だけ core-api を叩く＝その瞬間だけ起動。

### コスト（アイドル時 ≈ ¥0）
- 全エージェントは**常駐させずCloud Run scale-to-zero**（min=0）。Workerは Cloud Tasks で必要時のみ起動。
- Gemini は呼んだ時だけ。理解・整理は**小型安価モデル（Flash / Flash-Lite）**、重い判断（計画・コード生成）のみ上位モデル＝**モデルルーティング**。
- **方針：原則すべての Cloud Run サービスを min=0（コールドスタート許容）**でコスト最優先。min=1（常駐）は採用しない（最終手段のみ）。
  - コールドスタート対策：軽量コンテナ（slimイメージ・最小依存）、重いクライアントは遅延初期化、デモ撮影前にウォームアップ要求を1回投げる。

### 生成機能の実行モデル（例：タスク管理）
生成機能は静的フォームにしない。**「境界LLM（小型）＋決定的API＋動的UI」**の三点セット。
- **骨格＝決定的API**：追加/一覧/完了/並び替え等の CRUD（Firestore、LLM不使用）。
  - **永続化APIは機能ごとに増える**：動的UIの編集可能要素（チェックボックス・メモ欄・フォーム等）は、書き換えた状態をサーバに残すため対応する永続化API（作成/取得/更新/部分更新/削除）が必要。機能の追加・拡張ごとに設計・生成・登録する。`api_registry`登録、`generated-app-api`がFirestoreを読み書き。
  - **増殖管理戦略**：①汎用CRUDエンジン（entity/スキーマをパラメータ化）を基盤にし単純な読み書きは賄う、②特別なバリデーション/集計/副作用が要る所だけ機能特化APIを生成。汎用で足りるか専用かはOrchestratorが判断。UIコンポーネントは`view_manifest`でAPI×フィールドにバインド。
- **入出力の境界＝小型LLM**：自然言語入力→タスク情報へ構造化、出力は任意形式。`function calling` で決定的ツールを呼ぶ。
- **UI＝動的manifest**：「締切順で見やすく」等の自然言語で UI Designer が `view_manifest` を再生成。
- **節約**：UIを変えない時は manifest 再生成せず **API直叩き**。LLM不要な操作はLLMに通さない。

### ワーカー非常駐＋コンテキスト永続化
- ワーカーは機能使用時のみ起動、他は休止。
- 短命のため文脈はワーカー内に持たせず、**Firestore（Context DB）に永続化**：`context_chunks`（+Vector Search）/ `worker_registry` / `worker_definitions` / `worker_runs` / `conversations`、大物は Cloud Storage。
- 起動毎に `context_refs`（最小ポインタ）で取得して **rehydrate**。

### API化 vs ワーカー化の判断
- **Orchestrator が判断**（審査基準1「AIエージェントの必然性」の見せ場）。
- 安定・決定的→API化／自然言語I/O→境界LLM／継続的判断→専用ワーカー（非常駐）。
- ビルド時ワーカー（UI Designer/Programmer等）は汎用・再利用、機能ごとに新規作成しない。

## 3. MVPスコープ（7/10までに「動く」もの）

### 必ず動かす（縦切り1本完走）
```
ログイン → チャットで「タスク管理を追加して」
→ Reception即応 → Orchestratorが作業計画(JSON)生成
→ Control Planeがregistryにpending登録 → Cloud Tasksでworker起動
→ UI Designer Workerがview_manifest生成 → Cloud Storage保存 → registry登録(preview)
→ Web Shellがpreviewタブで生成画面を表示
→ ユーザー「反映して」承認 → registryをactive化 → 本タブに常設
→ Task API(生成機能)がFirestoreにタスクCRUD
→ ユーザー「進捗どう?」にReceptionが即答
→ ユーザー「戻して」でrollback（active→disable、checkpoint復帰）
→ 全操作がAudit Logに残る
```

### 加点（時間が余れば）
- ②PDFメモ機能の自己拡張（Gemini要約）
- Programmer Agentが**実コード**生成 → Cloud Build → Cloud Run preview（Tier B）
- GitHub連携CI/CDをデモに組み込み
- Elastic Agent Builder連携（スポンサー露出枠）

### 提出版では作らない
BYOK / BYOLLM / Marketplace / 本格SNS / IoT / 課金（すべてロードマップ）

---

## 4. フェーズ別 実装計画

各フェーズは「ゴール＝何が動けば次へ進めるか」で区切る。**Phase 0〜2で必須要件（Cloud Run＋Gemini＋デプロイURL）を満たす**。

### Phase 0: 基盤セットアップ（あなた主体 / 私がコマンド用意）
- GCPプロジェクト作成、課金＋$300クーポン適用
- API有効化: run / cloudbuild / artifactregistry / firestore / cloudtasks / secretmanager / storage / aiplatform(or Gemini API) / firebase
- Firestore(native)・Cloud Storageバケット・Artifact Registry・Cloud Tasks queue 作成
- Gemini APIキー取得 → Secret Manager登録
- GitHub公開リポジトリ作成、ローカル接続
- **ゴール**: `gcloud run deploy` が通る空サービスが1つ立つ

### Phase 1: Web Shell + Reception（ログインしてチャットできる）
- React+Vite SPA（Chat UI / Progress / Approval枠）
- Firebase Auth（Googleログイン）
- core-api に `reception` モジュール（FastAPI）。Firestoreの会話・task状態を読んで即応
- **ゴール**: ログイン→チャット→Firestoreにconversation保存→Receptionが定型＋軽量Geminiで応答

### Phase 2: Orchestrator + Gemini + Control Plane（作業計画が生成・登録される）
- ADK+Geminiで「要求→作業計画JSON」生成
- Control Planeモジュール: service/api/ui/deployment/approval registry（Firestore）
- 計画と生成予定UI/APIをregistryにpending登録
- **ゴール**: 「タスク管理を追加して」で作業計画が出てregistryにpending登録される。**この時点でCloud Run＋Geminiの必須要件クリア＝最低限の提出可能状態**

### Phase 3: Worker + Cloud Tasks + 生成UI manifest（画面が増える）
- Cloud Tasks queue → worker-runner(Cloud Run)起動
- UI Designer Workerがview_manifest(JSON)生成 → Cloud Storage → ui_view_registry(preview)
- Web ShellのGenerated View Rendererがmanifestから画面描画
- **ゴール**: チャットからタスク管理画面がpreview表示される。作業中もReceptionが進捗即答

### Phase 4: 承認 → active化 → Task API稼働（機能が本当に使える）
- 承認UI → Control Planeがregistryをactive化、ルート常設
- 生成機能のTask API（Firestore tasksのCRUD）をcore-api内の動的ルートで提供
- **ゴール**: 承認後、タスクの追加/一覧/完了切替が本タブで動く

### Phase 5: Rollback + Audit（戻せる・説明できる）
- checkpoint作成、rollback（active→disable、route復帰）
- 全操作をaudit_logsに記録、画面で閲覧
- Service Account分離・Tool Gateway経由実行（強権限を渡さない設計の実装）
- **ゴール**: 「戻して」で機能が消え、Audit Logに一連が残る

### Phase 6: CI/CD + 仕上げ（まわす・とどける）
- GitHub → Cloud Build → Cloud Run の自動デプロイ
- （加点）Programmer Agent実コード生成→Cloud Build→preview
- **ゴール**: pushで本番更新。DevOpsサイクルが回る

### Phase 7: 提出物（あなた主体）
- デモ動画（縦切り1本＋rollback）撮影
- アーキ図、ProtoPediaストーリー（課題/ユーザー/特徴）登録、公開リポジトリ整備、デプロイURL固定
- 早めに一度提出（再提出可）→ 改善して再提出
- **ゴール**: 7/10までに提出完了

---

## 5. デモ動画ストーリーボード（提出の主入力）

仕様書「見せるべき10画面」を動画の流れに変換：
1. ログイン直後＝チャットだけの最小アプリ（"これがどう育つか"）
2. 「タスク管理を追加して」→ Reception即応＋作業計画表示
3. 進捗パネル / Workerタイムライン（"AIが分担して働いている"）
4. 生成画面のpreview
5. 「反映して」承認 → active化
6. タスクを実際に追加・完了（"本当に動く"）
7. 「戻して」→ rollback（"安全に戻せる"）
8. Audit Log / registry（"実運用への配慮"）
9. （加点）PDFメモを追加 or GitHub→Cloud Buildのパイプライン

---

## 6. 進捗トラッキング

実装の現在地はこのリポジトリの `PROGRESS.md`（Phase 1着手時に作成）で管理する。
各Phaseのゴール達成チェックリストを置き、完了したらチェックする。

---

## 7. リスクと対策

| リスク | 対策 |
|---|---|
| スコープ過大で未完走 | Phase 2で一度「提出可能な最小形」に到達させ、以降は加点 |
| デプロイURLが審査期間に落ちる | min-instances/監視。〜7/24は止めない |
| Gemini無料枠レート制限 | Receptionは定型中心、重い判断のみGemini。$300クーポンでカバー |
| 初級ゆえの詰まり | 私がコマンド/コードを用意。あなたは実行と結果共有に専念 |
| 生成コードのCloud Build暴走コスト | Tier Bは加点扱い。MVPはmanifest方式で再ビルド不要 |
```
