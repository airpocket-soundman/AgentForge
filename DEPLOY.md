# AgentForge — Cloud Run / Hosting デプロイ手順

backend（core-api）を Cloud Run にデプロイし、Secret Manager の `gemini-api-key`
を環境変数として注入する手順。Cloud Shell でも、gcloud 認証済みのローカル PowerShell でも実行できる。

> これが通ると必須要件（Cloud Run 実行 ＋ Gemini API 利用）を満たし、
> 公開デプロイURL（提出要件）が立つ＝**最低限の提出可能状態**に到達する。
>
> デプロイ前のテスト実行手順は [ENVIRONMENT.md](ENVIRONMENT.md) §2 (C) を参照。

---

## 0. 変数とプロジェクト設定
```bash
export PROJECT=agentforge-498808
export REGION=asia-northeast1
export SA=217469091476-compute@developer.gserviceaccount.com   # 既定のCloud Run実行SA
gcloud config set project $PROJECT
```

## 1. 最新コードを取得（Cloud Shell 内）
```bash
git clone https://github.com/airpocket-soundman/AgentForge.git
cd AgentForge/backend
# 既にclone済みなら:  cd ~/AgentForge && git pull && cd backend
```

## 2. 実行SAに最小権限を付与（Secret読取 ＋ Firestore読み書き）
```bash
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/datastore.user"
```

## 3. デプロイ（`AgentForge/backend/` ディレクトリ内で実行）
```bash
gcloud run deploy agentforge-core-api \
  --source . \
  --region=$REGION \
  --allow-unauthenticated \
  --min-instances=0 \
  --set-env-vars="APP_ENV=prod,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_REGION=$REGION,ALLOWED_EMAILS=yamashita.3154@gmail.com;airpocket.soundman@gmail.com,GUEST_ACCESS_ENABLED=true" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest"
```
- `ALLOWED_EMAILS`：このメール**以外はログインしてもアプリを使えない**（API 403／UIはアクセス拒否画面）。
  複数許可する場合は **`;`（セミコロン）区切り**：`ALLOWED_EMAILS=a@x.com;b@y.com`（カンマは gcloud と衝突するので不可）。
  空または未設定なら通常ユーザーの許可リストは空になり、`ADMIN_EMAILS` の管理者だけが利用できる。
- `GUEST_ACCESS_ENABLED=true`：デモ/審査用。Google アカウント不要の名前付きゲスト入口を有効にする。
  frontend は `X-AgentForge-Guest-Id` / `X-AgentForge-Guest-Name` を付け、backend は `guest_<id>` の project に分離する。
- `APP_ENV=prod` では `FIRESTORE_EMULATOR_HOST` を設定しない。設定されている場合は起動時にエラーにする。
- 認証込みローカルデモは `APP_ENV=demo` と Firestore emulator を使い、本番 Firestore には接続しない。
- 初回ビルドで「`cloud-run-source-deploy` リポジトリを作成しますか？」と聞かれたら **y**
- `--min-instances=0` ＝ scale-to-zero（アイドル≈¥0）
- Firestore は本番（`(default)` / asia-northeast1）を使用（エミュレータではない）

## 4. 動作確認
```bash
URL=$(gcloud run services describe agentforge-core-api --region=$REGION --format='value(status.url)')
echo $URL
curl -s $URL/health ; echo
curl -s $URL/api/orchestrator/health ; echo

# 本物の Gemini で作業計画生成 → Control Plane に pending 登録される
curl -s -X POST $URL/api/reception/messages \
  -H "Content-Type: application/json" \
  --data '{"project_id":"prod","text":"タスク管理を追加して"}' ; echo
```
- 応答 JSON の `detected_intent` が `build_feature:task`、`task_id`/`approval_id` が返ればOK
- `work_plans` の `generated_by` が `"gemini"` なら実Geminiで生成成功。`"stub"` の場合はモデル名を調整（下記）

## 5.（必要なら）Gemini モデル名の調整
`generated_by` が `stub` のまま（＝Gemini呼び出しが失敗してフォールバック）の場合、
モデルIDが環境に合っていない可能性。コード変更不要、環境変数の更新だけで切替できる:
```bash
gcloud run services update agentforge-core-api --region=$REGION \
  --update-env-vars="GEMINI_FLASH_MODEL=gemini-2.0-flash,GEMINI_PRO_MODEL=gemini-2.0-flash"
```
（利用可能なモデルは `gcloud ai` ではなく [AI Studio / Gemini API のモデル一覧] に従って調整）

---

## 提出に使う公開URL
ユーザー向け提出URLは Firebase Hosting の `https://agentforge-devops.web.app`。
Cloud Run 直URL（例: `https://agentforge-core-api-217469091476.asia-northeast1.run.app`）は API 確認用。
審査期間（〜7/24）は落とさない。

## 現在の本番状態（2026-07-07）
- Cloud Run: `agentforge-core-api-00018-jc9` が 100% traffic
- Hosting: `sites/agentforge-devops/releases/1783390141966000`
- Firebase Auth: OAuth redirect URI `https://agentforge-devops.web.app/__/auth/handler` 登録済み
- `authDomain`: `agentforge-498808.firebaseapp.com`

> 将来: GitHub push → Cloud Build → Cloud Run の自動CI/CD（Phase 6）に置換予定。
> 当面はこの `--source` 手動デプロイで提出ラインを確保する。
