# DevOps × AI Agent Hackathon 2026 — 要綱まとめ & AgentForge提出戦略

作成日: 2026-06-08
出典: https://findy.notion.site/devops-ai-agent-hackathon-2026 （公式ページ各セクション）
主催: ファインディ株式会社 ／ メインスポンサー: グーグル・クラウド・ジャパン ／ スポンサー: Elasticsearch

> このファイルは公式情報の一次まとめ。AgentForgeの設計仕様は
> [agentforge_contest_submission_spec_audited.md](agentforge_contest_submission_spec_audited.md) /
> [agentforge_hackathon_google_cloud_spec_with_control_plane.md](agentforge_hackathon_google_cloud_spec_with_control_plane.md) を参照。

---

## 0. 一目で分かる重要事実

| 項目 | 内容 |
|---|---|
| **提出締切** | **2026/7/10（金）23:59**（ProtoPedia提出）← 最重要制約 |
| 参加登録 | 2026/4/27 10:00 〜 2026/7/10 23:59（Findy Conference申込ページ） |
| 一次審査 | 2026/7/13〜17（運営事務局） |
| 二次審査 | 2026/7/21〜24（外部審査員） |
| 決勝10チーム発表 | 2026/7/30（サイト＆Google Cloud Japanブログ） |
| 最終ピッチ | 2026/8/19（水）Googleオフィス渋谷ストリーム（一般観覧は抽選あり） |
| アフターイベント | 2026/9月予定（オンライン、審査員の"推し作品"を取り上げ） |
| 賞金支払い | 2026年8月末予定 |
| 賞金総額 | **200万円**（入賞枠 計10作品） |
| 参加資格 | **日本居住・18歳以上の個人**（チーム可）。**業務/団体代表としての参加は不可**。公務員等は賞金受領制限で不可 |
| 参加特典 | Google Cloudクーポン **$300分**（先着・要有料アカウント化、有効化期限 2026/10/20） |
| SNSタグ | **#findy_hackathon**（ProtoPediaタグにも `findy_hackathon` 必須） |

---

## 1. 3つのコンセプト

- **つくる**: Google CloudのAIを中核に、実務で役立つ独創的なAIエージェントを設計・実装
- **まわす**: GitHub連携やCI/CDなどDevOpsフローを構築し、AIを継続的に改善するサイクルを体験
- **とどける**: Cloud Runへのデプロイで、スケーラブルな環境に本番品質のプロダクトを届ける

---

## 2. 開発要件（必須）

### ① Googleアプリケーション実行プロダクト（1つ以上）
App Engine / GCE / **GKE** / **Cloud Run** / Cloud Functions / Cloud TPU・GPU
→ **AgentForgeは Cloud Run で充足。**

### ② Google Cloud AI技術（1つ以上）
- **Gemini Enterprise Agent Platform（旧 Vertex AI）** — AutoML / Vector Search / Explainable AI 等
- **Gemini API** — Vertex経由推奨だが直接利用も可
- Gemma / Imagen / Agent Builder
- **ADK (Agents Development Kit)**
- Speech-to-Text / Text-to-Speech / Vision AI / Natural Language AI / Translation AI
→ **AgentForgeは Gemini + ADK で充足（厚め）。**

### ③ 任意技術
Flutter / **Firebase** / Veo / **Elasticsearch（スポンサー）** ほか自由
→ AgentForgeは Firebase 採用済み。Elastic Agent Builder を Context検索/RAG に使うと**スポンサー露出枠**（活用チームインタビュー記事・推し作品）あり。

---

## 3. 審査基準（5項目）

1. **AIエージェントが価値の中心になっているか** — 自律的な判断・タスク実行、"AIエージェントである必然性"
2. **設定した課題へのアプローチ力** — 課題・背景・対象ユーザー・提供価値のストーリーの一貫性／妥当性／新規性
3. **ユーザビリティ** — 直感的に使える機能・デザイン
4. **実用性・体験価値の魅力** — 課題解決の実用性、突き抜けた体験価値は加点
5. **実装力** — 技術構成の納得度、拡張性、実運用への配慮、必須ツールの活用度

---

## 4. 審査員（二次審査）と評価の重心

| 審査員 | 立場 | 重視軸（推定） |
|---|---|---|
| **ばんくし王** (@vaaaaanquish) | エムスリー VPoE / ML engineer / GDE AI/ML | 実装力・技術構成の納得度（基準5） |
| **佐藤一憲 / Kaz Sato** (@kazunori_279) | グーグル合同会社 Developer Advocate (AI/ML) | Google Cloud AI活用の見せ方（ADK/Gemini/Vertex） |
| **宮田大督** (@miyatti) | エクスプラザ CPO / PdM15年・生成AIエバンジェリスト | 課題設定・プロダクトストーリー（基準2） |

→ **技術深度（ばんくし）× Google Cloud活用（Kaz Sato）× プロダクトストーリー（宮田）の三輪**が必要。

---

## 5. 賞金構造（入賞枠 計10）

- 🏅 **最優秀賞 50万円 × 1**：技術的完成度・DevOps実践度・独創性・実務応用可能性の総合
- 🥈 **優秀賞 30万円 × 3**：設計力・実装力・デプロイまでのフルサイクル開発の完成度
- 🥉 **特別賞 10万円 × 6**：独自の切り口・技術的チャレンジ・社会課題アプローチ
  → AgentForgeの**「AIに強権限を渡さない安全なDevOps制御」**は特別賞の独自切り口として現実的に狙える。

---

## 6. 応募方法（3 STEP）と提出必須物

- **STEP① 参加申込**: Findy Conference申込フォーム（チームは全員申込必須）
- **STEP② 作品をProtoPediaに登録**
- **STEP③ Google Form（作品提出フォーム）で正式エントリー**

### Google Form提出 必須3点
1. **GitHub公開リポジトリURL**（※公開が必須。当初「公開禁止」と誤認したが、審査過程の公開として必須）
2. **デプロイ済みプロジェクトURL**（動作確認できる状態を維持＝Cloud Runで実稼働、審査期間 〜7/24 落とさない）
3. **ProtoPedia作品URL**

### ProtoPedia登録ルール（必須項目）
- 作品ステータス / タイトル / 概要：必須
- **動画（YouTube or Vimeo URL）：必須** ← 審査の主入力
- **システム構成（アーキテクチャ図のアップロード）：必須**
- 開発素材（使用ツール）：必須
- **タグ：必須（`findy_hackathon` を1つ必ず設定）**
- **ストーリー：必須 → ①解決したい課題と背景 ②想定ユーザー ③プロダクトの特徴**
- 画像（最大5枚）/ メンバー登録 / 関連URL：任意

> **重要**: ProtoPediaのストーリー3項目は審査基準2と完全一致。
> 「対象ユーザー1絞り込み・課題1つ」は提出フォームレベルで強制される。

### その他Q&A要点
- 1人で複数作品の提出可（作品ごとに提出）
- 再提出可（最新タイムスタンプの作品を正として審査）
- チームはProtoPedia代表者1名のアカウントで可。ただしFormで全員氏名を記載
- 著作権は参加者帰属（運営は広報・運営目的の掲載権を持つ）

---

## 7. AgentForge 提出戦略（確定版）

### 二層の建て付け
- **最大ターゲット（背景として語る）**: 自己拡張型スーパーアプリ／DevOpsの民主化
- **提出版フォーカス（7/10までに動かす）**: スーパーアプリを安全に育てる **DevOps AI Agent Workbench**。
  スーパーアプリは「AgentForgeの自己拡張能力を示す題材」であり、評価対象は**機能追加プロセスそのもの**。

### 残り約32日で勝つための3調整（審査基準・審査員・提出要件すべてから裏付け済み）
1. **スコープを1機能の1サイクル完走に絞る**（P0〜P2＋rollback）。
   「チャット→計画→生成→Cloud Run preview→承認→active→rollback」を1機能で確実に動かす。
   フル構成（5サービス＋Control Plane全部）は1ヶ月では不可。デプロイURL動作必須なのでモック不可。
2. **対象ユーザー1人 × 課題1つに絞る**（基準2・宮田氏・ProtoPediaストーリー対策）。
   「DevOpsの民主化」は背景に留め、具体ペルソナ1つの課題に寄せる。
3. **"AIエージェントの必然性"を1文で明示**（基準1）。
   決め打ちCI/CD自動化との差＝「曖昧な自然言語要求からの判断・分解・委任」が非決定的に必要だから。

### 技術の見せ方（審査員別）
- ばんくし向け: Control Plane / Service Account分離 / Tool Gateway / Audit Log / Rollback を**実装で**見せる
- Kaz Sato向け: **ADK ＋ Gemini Enterprise Agent Platform** を中核として明示（Google Cloud AI活用の必然）
- 宮田向け: 1ユーザー1課題のストーリー一貫性

### デモ動画前提
ProtoPedia動画が審査の主入力。仕様書「見せるべき10画面」を**動画ストーリーボード**として設計する。

---

## 8. 直近スケジュール逆算（目安）

| 期間 | やること |
|---|---|
| 〜6/中旬 | 対象ユーザー/課題の確定、アーキ最終化、Cloud Run雛形＋Gemini疎通、Boot Camp受講（ADK/Gemini/Cloud Run, 6/1〜6/12） |
| 6/中〜下旬 | Reception＋Orchestrator＋Control Plane＋Worker（1機能分）実装、生成UI manifest表示 |
| 6/下〜7/上旬 | Cloud Build→preview→承認→active→rollback の1サイクル完走、Audit/権限の作り込み |
| 7/上旬 | デモ動画撮影、アーキ図、ProtoPediaストーリー執筆、公開リポジトリ整備、デプロイURL固定 |
| **7/10 23:59** | **提出締切**（再提出可。早めに一度出す） |

※ Boot Camp: Agentic AI Bootcamp 2026（Google Cloud Japan, 6/1〜6/12 オンライン無料）／Elastic Agent Builder実践Bootcamp（6/23 19:00-20:30）
