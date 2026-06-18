# AgentForge ProtoPedia 投稿原稿

作成日: 2026-06-18

## 公式項目メモ

ProtoPedia の作品投稿では、作品ステータス、作品タイトル、作品 URL、概要、ライセンス、画像、動画、システム構成、開発素材、タグ、ストーリー、メンバー、関連リンクを入力します。必須は作品ステータス、作品タイトル、概要です。DevOps × AI Agent Hackathon 2026 では、通常項目に加えて動画、システム構成、開発素材、タグ `findy_hackathon`、ストーリーの記載が提出上重要です。

以下は、各欄にそのまま貼れる形の原稿です。`【要差し替え】` の部分だけ提出前に実URL・チーム名へ置き換えてください。

---

## 作品タイトル

AgentForge - 会話だけで自分専用アプリを育てる DevOps AI Agent Workbench

## 作品ステータス

開発中

## 作品URL

【要差し替え】デプロイ済みURL

## 概要

AgentForge は、非エンジニアがチャットで話すだけで、自分専用のミニアプリを作成・改変・公開・巻き戻しできる自己拡張型アプリです。裏側では Receptor / Orchestrator / Tester / Reviewer / Specialist Worker が協業し、要求整理、設計、コード生成、検証、レビュー、プレビュー、承認公開までの DevOps サイクルを安全に代行します。

## ライセンス

【要差し替え】例: MIT License

## 動画

【要差し替え】YouTube または Vimeo のデモ動画URL

## システム構成

AgentForge は、ユーザーが触るフロントエンド、ミニアプリ生成・承認・状態管理を行うバックエンド、そして Google Cloud / Firebase 上の実行基盤で構成しています。

図解としては、以下を添付してください。

- `protopedia_assets/agentforge_handdrawn_infographic.png`: 手書き風の機能・ユースケース・制作パイプライン紹介
- `protopedia_assets/agentforge_concept_infographic.png`: アプリとAIエージェントのコンセプト
- `protopedia_assets/agentforge_system_architecture.png`: システム全体構成
- `protopedia_assets/agentforge_devops_flow.png`: 会話から公開までの DevOps フロー
- `protopedia_assets/agentforge_app_screen.png`: アプリ画面構造

同じ内容の編集用 SVG も `protopedia_assets/` に保存しています。

- フロントエンド: React + Vite。メインチャット、ミニアプリ表示領域、アプリチャット、ステータスモニター、変更履歴を提供。
- バックエンド: FastAPI。Receptor、Orchestrator、Control Plane、生成ミニアプリ実行API、承認・巻き戻しAPIを提供。
- AI ワーカー: Receptor / Orchestrator / Tester / Reviewer / Specialist Worker。役割ごとに文脈を分け、MCP 的な request/report で非同期に連携。
- LLM: 本番は Gemini API を想定。開発・デモでは Codex CLI ブリッジを使い、同じワーカー構造でコストを抑えて検証。
- 実行基盤: Cloud Run 上でアプリ本体を実行。Firebase Hosting / Auth、Firestore を組み合わせ、会話、ワーカー状態、生成ミニアプリ、承認、監査ログ、アプリ状態を保存。
- 安全境界: 生成ミニアプリは sandbox iframe 内で実行し、外部通信や localStorage を禁止。保存は AF.load / AF.save 経由でサーバ側に限定。
- DevOps 制御: 生成物はすぐ公開せず、Tester と Reviewer のゲートを通したうえでプレビュー登録。ユーザーが「反映して」と承認したときだけ active 化し、公開ごとのスナップショットから即時巻き戻しできる。

## 開発素材

- Google Cloud
- Cloud Run
- Gemini API
- Firebase Hosting
- Firebase Authentication
- Firestore
- FastAPI
- React
- TypeScript
- Docker
- Codex CLI

## タグ

findy_hackathon
AIエージェント
DevOps
GoogleCloud
Gemini
CloudRun
Firebase
Firestore
React
FastAPI
マルチエージェント
生成AI

## ストーリー

### 解決したい課題と背景

世の中には小さな便利アプリが大量にありますが、一般ユーザーにとっては「探す」「選ぶ」「広告や不要機能を避ける」「自分好みに直す」こと自体が負担になっています。単純な計算機、メモ、PDF ビューワ、タスク管理のような道具でも、ストアで探すと広告が多かったり、ほしい機能だけが微妙に足りなかったりします。

一方で、自分で作れば解決できると分かっていても、非エンジニアが設計、実装、テスト、デプロイ、修正、巻き戻しまで行うのは現実的ではありません。生成AIでコードだけを作れても、それを安全に動かし、確認し、公開し、壊れたら戻す DevOps の流れが抜けると、日常的に使える道具にはなりません。

AgentForge は、このギャップを埋めるためのアプリです。ユーザーは「計算機を作って」「テトリスを作って」「ボタンを大きくして」のように話すだけです。裏側では複数の AI ワーカーが、要求の具体化、設計、コード生成、検証、レビュー、プレビュー、承認公開、巻き戻しまでを担当します。

### 想定ユーザー

主な想定ユーザーは、プログラミング経験はないが、自分用の小さなアプリを持ちたい一般ユーザーです。

例えば、既製アプリの広告や複雑な設定に疲れていて、「必要な機能だけの自分専用ツールがほしい」と感じている人です。仕事や生活の中で、簡単なメモ、計算、チェックリスト、ゲーム、学習ツール、閲覧ツールなどを思いつくたびに作りたい。しかし、アプリ開発やデプロイの知識はなく、GitHub やクラウドを触る前提のツールは使えない。AgentForge は、そうした人が「使う場所」と「作る場所」を分けず、会話だけで自分の環境を育てられることを目指しています。

### プロダクトの特徴

AgentForge の最大の特徴は、アプリの中でアプリ自身を拡張できる再帰的な構造です。ユーザーがメインチャットで依頼すると、AgentForge 自身の中に新しいミニアプリが追加されます。生成されたミニアプリには専属の Specialist Worker が付き、そのアプリの中から内容の編集や操作を依頼できます。

ただし、AI が勝手に公開することはありません。AgentForge には 3 つの人間承認ゲートがあります。まず Receptor が依頼内容を整理し、ユーザーが「お願い」と承認してから制作に入ります。次に設計案を見て、ユーザーが「これで作って」と承認してからコード生成します。最後にプレビューを確認し、ユーザーが「反映して」と言ったときだけ公開します。

公開前には Tester と Reviewer の両方が生成物を確認します。Tester は実際に動くか、受け入れ条件を満たすかを検証します。Reviewer は sandbox、保存API、操作ツール、レスポンシブ対応、チャットUIの分離などの規約に合っているかを確認します。片方でも NG なら公開せず、修正ループに戻します。

ミニアプリは sandbox iframe 内で動作し、外部通信、localStorage、cookie を使わせません。状態保存は AF.load / AF.save 経由でサーバ側に限定します。これにより、画面遷移やリロード後もアプリ状態を復元でき、同時に生成コードの権限を限定できます。

また、公開ごとにスナップショットを保存するため、「戻して」と言うだけで直前の公開版へ巻き戻せます。これは LLM に再生成させるのではなく、保存済みの版を復元する決定的な操作です。生成AIに任せる部分と、決定的に制御する部分を分けることで、安全に自己拡張する体験を作っています。

DevOps × AI Agent Hackathon の 3 つのコンセプトに対して、AgentForge は次のように対応します。

- つくる: Gemini API を中心に、複数の AI ワーカーがユーザー要求を解釈し、ミニアプリを設計・生成する。
- まわす: 設計、生成、検証、レビュー、承認、履歴、巻き戻しを一連の DevOps サイクルとして回す。
- とどける: Cloud Run / Firebase / Firestore を使い、実際にアクセスできるアプリとしてユーザーへ届ける。

AI エージェントである必然性は、単なるコード生成ではなく、曖昧な自然言語要求から「何を作るか」「どう分解するか」「どのワーカーが何を確認するか」「どの段階で人間承認を求めるか」を判断し続ける点にあります。AgentForge は、AI が強い権限を直接持つのではなく、Control Plane と承認ゲートの中で安全に働く DevOps AI Agent Workbench です。

## 関連リンク

- GitHub: 【要差し替え】公開リポジトリURL
- デプロイURL: 【要差し替え】アプリURL
- 説明資料: 【要差し替え】docs/index.html 相当の公開URL、またはリポジトリ内 docs

## メンバー

【要差し替え】チーム名・メンバー名

## 投稿前チェックリスト

- 作品ステータスを「開発中」または「完成」にする
- 作品タイトルを入力する
- 概要を入力する
- デプロイ済みURLを入力する
- YouTube または Vimeo のデモ動画URLを入力する
- システム構成図を画像としてアップロードする
- 開発素材を登録する
- タグに `findy_hackathon` を必ず入れる
- ストーリーに「課題と背景」「想定ユーザー」「プロダクトの特徴」が入っていることを確認する
- 関連リンクに GitHub 公開リポジトリURL、デプロイURLを入れる
