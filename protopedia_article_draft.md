# 育てるアプリ ProtoPedia 投稿原稿

作成日: 2026-06-24 ／ 最終更新: 2026-07-06

## 公式項目メモ

ProtoPedia の作品投稿では、作品ステータス、作品タイトル、作品 URL、概要、ライセンス、画像、動画、システム構成、開発素材、タグ、ストーリー、メンバー、関連リンクを入力します。必須は作品ステータス、作品タイトル、概要です。DevOps × AI Agent Hackathon 2026 では、通常項目に加えて動画、システム構成、開発素材、タグ `findy_hackathon`、ストーリーの記載が提出上重要です。

以下は、各欄にそのまま貼れる形の原稿です。`【要差し替え】` の部分だけ提出前に実URL・チーム名へ置き換えてください。

---

## 作品タイトル

育てるアプリ - 会話だけで自分専用アプリを作って育てる

## 作品ステータス

開発中

## 作品URL

https://agentforge-devops.web.app

## 概要

育てるアプリは、非エンジニアがメインチャットで話すだけで、自分専用のミニアプリを作成・改変・公開・巻き戻しできる自己拡張型の AI アプリです。技術基盤として AgentForge を使っています。電卓、タスク管理、スケジュール、メモ、家計簿、翻訳、ペイント、レタッチ（オブジェクト選択・背景透過対応）、Bluesky クライアントの 9 種のデフォルトアプリを用意し、初心者はいきなり白紙から作るのではなく、既に使える道具の UI や機能を自分好みに直すところから始められます。外部サービス連携も、生成アプリから直接通信させるのではなく、バックエンドが秘密情報を管理する Connector Bridge 経由で安全に行います。ユーザー体験は「選ぶ / 話す」「AI が直す / 作る」「確認して反映」の3ステップですが、裏側では Receptor / Orchestrator / Tester / Reviewer / Specialist Worker が役割分担し、要求整理、設計、コード生成、実行検証、規約レビュー、プレビュー、承認公開までを1本の DevOps パイプラインとして管理します。生成物は見た目の HTML だけではなく、state、commands、Worker prompt、評価ケースを含む「公開後にワーカーが操作できる contract」として作ります。Safety Harness は公開前の最終安全判定を行い、Agent Harness は判断・成果物・検証結果・承認履歴を記録して、ユーザーには短い進捗と承認前サマリーとして見せます。

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

投稿用画像はすべて PNG 形式で `protopedia_assets/` に保存しています。

- フロントエンド: React + Vite。トップページ、Pipeline 詳細、Architecture 詳細、メインチャット（複数セッションの作成・命名・切替に対応）、ミニアプリ表示領域、アプリチャット、ステータスモニター、変更履歴を提供。左メニューではアプリの並べ替え、フォルダ化・取り出し、名称変更ができる。アプリ改修を依頼すると新しいメインチャットセッションへ遷移し、対象アプリだけを完了まで操作不可にして重複依頼を防ぐ。
- バックエンド: FastAPI。Receptor、Orchestrator、Control Plane、生成ミニアプリ実行API、Connector Bridge、承認・巻き戻し・完全削除APIを提供。会話履歴は閾値を超えると決定的に要約へ畳み込み（コンパクト化）し、長期利用でも肥大化しない。アプリ削除時は、表示定義だけでなく状態、Blob、接続設定・secret、アプリチャット、Workerコンテキスト、版履歴など、そのアプリに属するデータをまとめて削除する。
- AI ワーカー: Receptor / Orchestrator / Tester / Reviewer / Specialist Worker。役割ごとに文脈と権限を分け、MCP 的な request/report（plan / build / edit / verify / review / operate / investigate）で非同期に連携する。メッセージ追記は Firestore トランザクションで並行実行に耐える。ユーザーへの会話は Receptor / Specialist Worker が受け持ち、制作チームの raw trace をそのまま転記せず、依頼に対する進捗と結果へ要約して返す。
- 依頼理解と構造化: Receptor と Specialist Worker は、LLMで会話文脈と機能一覧を読み、依頼の目的、対象アプリ、必要な情報、実行内容を構造化してから処理する。固定キーワードだけに頼らず「新規作成 / 改修 / 調査 / 会話 / アプリ内操作」を判定し、機能名の表記ゆれやタイプミスも一覧に照らして解決する。タスク追加ではタスク名と詳細を分離し、補足の余地があればAIが提案を加えるなど、依頼の種類に応じて自然に具体化する。
- Specialist Worker の実行判断: 担当アプリ内の追加・更新・検索・削除などは、構造化した引数で `commands[]`、`state_schema`、アプリAPIを操作してその場で結果を返す。新機能や画面構造の変更など担当権限を超える依頼は、自分でコードを書き換えず「アプリ制作・改修パイプラインへエスカレーション」する。エスカレーション時は依頼専用の新しいメインチャットセッションを作り、依頼原文と構造化結果をReceptorからOrchestratorへ引き継ぐ。
- パイプライン: ユーザー発話を `task_id` 付きの作業単位に変換し、依頼確認、設計承認、生成、Tester検証、Reviewer審査、Safety Harness判定、プレビュー、公開承認までを一連の流れとして扱う。修正指示、検証NG、レビューNG、停滞時はそれぞれ明示的な戻り先を持つ。同一アプリの改修はロックし、他のアプリは利用可能なままにする。コード改修を伴わない依頼は investigate（調査）として扱い、保存状態や接続設定を事実ベースで確認して報告する。
- 生成 contract: 自己完結 HTML、`state_schema`、`commands[]`、`window.applyAgentCommand(name,args)`、Worker prompt、`worker_eval_cases`、危険操作方針、版メタデータを同時に設計する。
- Safety Harness: Tester / Reviewer の結果、禁止 API、外部リソース、Worker 契約、stub 生成物の有無を統合し、通過した候補だけを preview に進める公開前安全ゲート。NGの指摘は次の生成へ必ず引き継ぎ、3回までは自動再試行する。なお通らない場合は、ユーザーが「さらに3回試す」か「停止する」かを選び、継続するたびに同じ単位で改善を重ねる。
- Agent Harness: `pipeline_runs` にワーカーの判断、進捗、生成物メタ、Tester / Reviewer / Safety Harnessの結果、指摘の引き継ぎ、リトライ、承認を記録する。一般ユーザーには raw trace を見せず、進捗・失敗理由・次の判断・承認前サマリーに変換して表示する。
- LLM: 本番は Gemini API（FLASH=Gemini Flash / PRO=Gemini Pro）。開発・デモでは Codex CLI セッションをホストブリッジ経由で使い、同じワーカー構造と能力帯で検証する。
- 実行基盤: Cloud Run 上でアプリ本体を実行。Firebase Hosting / Auth、Firestore を組み合わせ、会話、ワーカー状態、生成ミニアプリ、承認、監査ログ、アプリ状態を保存。
- 安全境界: 生成ミニアプリは sandbox iframe 内で実行し、直接の外部通信・cookie・localStorage を禁止。保存は AF.load / AF.save 経由でサーバ側に限定。外部リンクはユーザーのクリック操作に応じたシェル経由（AF.openExternal）でのみ開く。
- Connector Bridge: 外部サービス連携（例: Bluesky/AT Protocol）は、ミニアプリが `AF.defineConnector` で feature 単位の接続を登録し、登録済み action だけを `AF.api` で呼ぶ。URL・トークン・パスワードはバックエンドが管理し、保存済み secret は query/body テンプレートでサーバ側だけで差し込む（生成 HTML の state には残さない）。宛先は登録した base_url の同一オリジンに限定し、任意ホストへのプロキシ化（SSRF）を防ぐ。
- DevOps 制御: 生成物はすぐ公開せず、Tester、Reviewer、Safety Harness のゲートを通したうえでプレビュー登録する。ユーザーが「反映して」と承認したときだけ active 化し、公開ごとのスナップショットから即時巻き戻しできる。改修完了・失敗・停止時には対象アプリのロックを確実に解除する。
- Specialist Worker Eval: 生成時に `worker_eval_cases`、`clarification_policy`、`dangerous_action_policy` を作る。各ミニアプリの専門ワーカーが、依頼を理解・構造化したうえで「削除」「一括操作」「異常値」「曖昧な対象」「担当外の構造変更」を判断できるかを検証し、担当外の改修は制作パイプラインへ正しくエスカレーションさせる。

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
- Claude Code CLI（開発・デモ用 LLM ブリッジ）

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

世の中には小さな便利アプリが大量にありますが、一般ユーザーにとっては「探す」「選ぶ」「広告や不要機能を避ける」「自分好みに直す」こと自体が負担になっています。単純な計算機、メモ、PDF ビューワ、タスク管理のような道具でも、ストアで探すと広告が多かったり、ほしい機能だけが微妙に足りなかったりします。かといって、最初から完全なアプリを考えて作るのも、多くの初心者には難しい体験です。

一方で、自分で作れば解決できると分かっていても、非エンジニアが設計、実装、テスト、デプロイ、修正、巻き戻しまで行うのは現実的ではありません。生成AIでコードだけを作れても、それを安全に動かし、確認し、公開し、壊れたら戻す DevOps の流れが抜けると、日常的に使える道具にはなりません。

AgentForge は、このギャップを埋めるためのアプリです。ユーザーは「計算機を作って」「テトリスを作って」のように新しく作ることも、「メモの入力欄を広くして」「スケジュールにメモ欄を足して」「タスク管理に優先度を追加して」のように既存のデフォルトアプリを育てることもできます。裏側では複数の AI ワーカーが、要求の具体化、設計、コード生成、検証、レビュー、プレビュー、承認公開、巻き戻しまでを担当します。

単なる「コードを生成するチャット」ではなく、AI エージェントが DevOps の工程を分担し、途中経過を説明し、失敗時には検証結果をもとに再試行し、公開前には人間の承認を求める仕組みにした点が特徴です。

### 想定ユーザー

主な想定ユーザーは、プログラミング経験はないが、自分用の小さなアプリを持ちたい一般ユーザーです。

例えば、既製アプリの広告や複雑な設定に疲れていて、「必要な機能だけの自分専用ツールがほしい」と感じている人です。仕事や生活の中で、簡単なメモ、計算、チェックリスト、ゲーム、学習ツール、閲覧ツールなどを思いつくたびに作りたい。しかし、アプリ開発やデプロイの知識はなく、GitHub やクラウドを触る前提のツールは使えない。AgentForge は、そうした人が最初はデフォルトアプリをそのまま使い、慣れてきたら UI の見た目、項目、操作、保存データ、ワーカーの扱える機能を少しずつ自分用に変えられることを目指しています。

### プロダクトの特徴

AgentForge の最大の特徴は、アプリの中でアプリ自身を拡張できる再帰的な構造です。ユーザーがメインチャットで依頼すると、AgentForge 自身の中に新しいミニアプリが追加されます。生成されたミニアプリには専属の Specialist Worker が付き、そのアプリの中から内容の編集や操作を依頼できます。トップページでは、初めて触る人にも分かるように「1. 選ぶ / 話す」「2. AI が直す / 作る」「3. 確認して反映」という3ステップの体験として説明しています。完全に新しいアプリを作るだけでなく、用意されたアプリを自分好みにカスタマイズしていく自由度を、日常的なユーザー体験の中心に置いています。

デフォルトアプリ自体も「会話で育てた」実例になっています。たとえばレタッチスタジオは、レイヤ編集、ズーム、ブラシに加えて、クリックやおおよそのトレースで写真内のオブジェクトの境界を検出して選択し（クリック追加で選択拡大・つながった部分は自動結合）、「選択以外を透過」でワンタップの背景削除ができます。Bluesky クライアントは Connector Bridge を通じて実際の外部 SNS に安全に接続します。メインチャットは複数セッションを持て、依頼内容ごとに会話を分けて進められます。

#### 1. 自然言語を検証済みミニアプリへ変換する Pipeline

AgentForge は、ユーザーの発話を単発のコード生成に投げるだけではありません。意図の判定はキーワードの固定ルールではなく LLM が担い、セッションの会話文脈とアクティブな機能一覧を読んで「新規作成 / 既存改修 / 調査 / 会話」を判定します。機能名の表記ゆれやタイプミスも解決し、曖昧な目的語や危険操作は聞き返します。コード改修を伴わない「保存されてる？」「接続を調べて」のような依頼は調査（investigate）として扱い、保存状態・connector 設定を事実ベースで確認して報告します。その後、制作依頼は `task_id` 付きの作業単位として Agent Harness に記録され、Orchestrator が画面構造、保存 state、操作 API、Specialist Worker プロンプト、受け入れ条件を設計します。

コード生成後は Tester と Reviewer の両方を通ります。Tester は実際に動くか、主要操作が動作するかを確認します。Reviewer は sandbox、保存API、操作ツール、レスポンシブ対応、チャットUIの分離などの規約に合っているかを確認します。どちらかが NG ならコード生成に戻り、公開済み版には触りません。長時間の無音停滞は Receptor が検知し、停止、もう少し待つ、直前の成功段階から再トライをユーザーに選ばせます。

#### 2. 役割を分けた Architecture

AgentForge は、1つの AI に全権を渡す構造ではありません。ユーザーと話す Receptor、設計と生成を担う Orchestrator、実行検証の Tester、規約判定の Reviewer、公開後のミニアプリを操作する Specialist Worker を分離します。その外側で Control Plane、Safety Harness、Agent Harness、Sandbox、Version 管理が副作用を制御します。

Control Plane は、公開、巻き戻し、承認、バージョン管理、ワーカー状態を扱う決定的な制御層です。AI が直接本公開や権限変更を行わないように、強い副作用はここに閉じ込めます。ワーカーは必要時に起動し、状態、待機理由、最終更新、使用モデルを記録します。固着した場合は Receptor が回収します。

#### 3. 生成物を「操作可能な contract」として作る

このとき Orchestrator は、単にコードを書く係ではありません。ユーザーの依頼が新規作成なのか既存改修なのか、データ中心アプリなのか操作中心アプリなのか、専門ワーカーが `commands` を使うべきか、保存 state を直接編集するべきか、あるいは hybrid にするべきかを判断します。

AgentForge は、自然言語から見た目だけを作るのではなく、公開後に Specialist Worker が継続操作できる contract まで生成します。HTML、state、commands、Worker prompt、評価ケースを同時に設計し、受け入れ条件、Tester の検証観点、Reviewer の確認観点、Specialist Worker の操作例までを 1 つの生成単位として扱います。

生成される成果物は次のようなものです。

- View artifact: `<!DOCTYPE html>` から始まる自己完結 HTML。外部 CDN、fetch、cookie、localStorage なしで sandbox 実行する。
- State contract: タスク、予定、家計簿、メモなどのデータ中心アプリでは `worker_state_mode=state/hybrid` と `state_schema` を生成する。
- Command surface: `window.applyAgentCommand(name,args)` と `commands[]` を一致させ、Worker が UI やデータを安全に操作できるようにする。
- Worker prompt pack: 役割、API 仕様、聞き返し方針、危険操作方針、自然言語例をアプリごとに Specialist Worker へ渡す。
- Eval cases: 一括削除、曖昧な対象、異常値、担当外の構造変更など、失敗しやすい指示をテストケース化する。
- Version metadata: feature、title、theme、manifest 参照、承認 ID、公開版スナップショットを Control Plane が管理する。
- Runtime context: 複数画面や詳細画面では `AF.setChatContext()` でアプリチャットの文脈を分ける。

ただし、AI が勝手に公開することはありません。AgentForge には 3 つの人間承認ゲートがあります。まず Receptor が依頼内容を整理し、ユーザーが「お願い」と承認してから制作に入ります。次に設計案を見て、ユーザーが「これで作って」と承認してからコード生成します。最後にプレビューを確認し、ユーザーが「反映して」と言ったときだけ公開します。

#### 4. Safety Harness と Quality Gates

公開前には Safety Harness が最終判定します。Tester / Reviewer の合否、禁止 API、外部リソース、Worker 契約の有無、stub 生成物の有無を統合し、通過した候補だけを preview / publish に進めます。片方でも NG、または Safety Harness 未通過なら公開せず、修正ループに戻します。

Quality Gates では、主に以下を確認します。

- Sandbox: 外部通信、cookie、localStorage、別ウィンドウに依存しないこと。
- Persistence: 状態を持つアプリが `AF.load()` / `AF.save()` に接続され、画面遷移後も復元すること。
- Worker operability: 主要操作が `commands` または `state_schema` で表現され、自然言語から到達できること。
- UX fidelity: ユーザー要求をフォームだけで代替せず、実際に使える UI とレスポンシブ性を満たすこと。
- Chat boundary: 生成 HTML 内にチャット UI を入れず、アプリ表示エリアと下部アプリチャットを分離すること。
- External access: 外部 API 連携は Connector Bridge 経由のみ。secret の state 保存、外部 URL の src/href 直接埋め込み、未エスケープの innerHTML を禁止すること。
- Deletion safety: アプリ削除は「保存データも失われる」ことをユーザーに確認したうえで完全削除し、操作証跡を監査ログに残すこと（巻き戻しは別操作としてデータを保持する）。

さらに、各ミニアプリの Specialist Worker には `worker_eval_cases` を持たせます。例えばスケジュールアプリなら「22日の予定を全部消して」は削除、「15:65にテスト」は即実行せず確認質問、というように、ユーザーが実際に言いそうな自然言語指示を事前に想定します。これにより、未知の新しいアプリでも「画面だけ作る」のではなく、「そのアプリを扱う専門ワーカーの運用能力」まで生成過程に含めます。

ミニアプリは sandbox iframe 内で動作し、直接の外部通信、localStorage、cookie を使わせません。状態保存は AF.load / AF.save 経由でサーバ側に限定します。これにより、画面遷移やリロード後もアプリ状態を復元でき、同時に生成コードの権限を限定できます。外部サービスと連携するアプリ（例: Bluesky クライアント）でも、生成 HTML は登録済みの connector action しか呼べず、トークンやパスワードはバックエンドだけが保持します。

また、公開ごとにスナップショットを保存するため、「戻して」と言うだけで直前の公開版へ巻き戻せます。これは LLM に再生成させるのではなく、保存済みの版を復元する決定的な操作です。生成AIに任せる部分と、決定的に制御する部分を分けることで、安全に自己拡張する体験を作っています。

Agent Harness はこの裏側を支える実行基盤です。各パイプライン実行について、依頼、設計案、生成物メタ、検証結果、レビュー結果、Safety Harness 結果、リトライ、承認を `pipeline_runs` として記録します。ただし、一般ユーザーに細かい trace をそのまま見せるとノイズになるため、通常画面では「設計案を作っています」「動作確認しています」「保存処理を修正して再確認しています」のような短い進捗に変換します。プレビュー承認前には、変更内容、ワーカーができること、検証済み項目、注意点をまとめたサマリーを表示します。

AgentForge は、アプリを作る、運用する、届ける流れを 1 つの体験として扱います。

- つくる: Gemini API を中心に、複数の AI ワーカーがユーザー要求を解釈し、ミニアプリを設計・生成する。
- まわす: 設計、生成、検証、レビュー、安全判定、承認、履歴、巻き戻しを一連の DevOps サイクルとして回す。Safety Harness により未通過成果物の公開を止め、Agent Harness により判断・成果物・検証結果を後から追える。
- とどける: Cloud Run / Firebase / Firestore を使い、実際にアクセスできるアプリとしてユーザーへ届ける。

AI エージェントである必然性は、単なるコード生成ではなく、曖昧な自然言語要求から「何を作るか」「どう分解するか」「どのワーカーが何を確認するか」「専門ワーカーにどんな操作能力を持たせるか」「どの段階で人間承認を求めるか」を判断し続ける点にあります。AgentForge は、AI が強い権限を直接持つのではなく、Control Plane、Safety Harness、Agent Harness、承認ゲートの中で安全に働く DevOps AI Agent Workbench です。

## 関連リンク

- GitHub: https://github.com/airpocket-soundman/AgentForge （提出時に公開設定になっていることを確認）
- デプロイURL: https://agentforge-devops.web.app
- 説明資料: リポジトリ内 `docs/index.html`（ワーカー定義・コード規約・アーキテクチャの正本ドキュメント）

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
