# AgentForge 本番デプロイ手順

AgentForge 本体を本番へ反映するための正準手順。

- Frontend: Firebase Hosting `agentforge-devops.web.app`
- Backend: Cloud Run `agentforge-core-api`
- Project: `agentforge-498808`
- Region: `asia-northeast1`

本番反映は **Cloud Run backend と Firebase Hosting frontend の両方**を更新して初めて完了する。

---

## 1. 本番デプロイの制約

### 環境分離

- 本番 Cloud Run は `APP_ENV=prod`。
- `APP_ENV=prod` では `FIRESTORE_EMULATOR_HOST` を設定しない。設定されている場合は起動時に拒否する。
- ローカル / デモ / テストは emulator を使う。本番 Firestore と混ぜない。
- 本番の LLM provider は Gemini。開発用 Claude bridge は Cloud Run では使わない。

### 認証・アクセス

- 通常ログインは Firebase Auth + backend の `ALLOWED_EMAILS` で制限する。
- `ALLOWED_EMAILS` は **セミコロン区切り**。例: `a@example.com;b@example.com`
- gcloud の `--set-env-vars` ではカンマが区切りとして扱われるため、許可メールの区切りにカンマを使わない。
- 審査 / デモ用の名前付きゲスト入口は `GUEST_ACCESS_ENABLED=true` の時だけ有効。
- Firebase Auth の OAuth redirect URI には `https://agentforge-devops.web.app/__/auth/handler` が必要。

### Cloud Run

- service: `agentforge-core-api`
- `--allow-unauthenticated` で公開し、アプリ側で Firebase token / guest header を検証する。
- `--min-instances=0` を維持する。アイドルコストを抑えるため。
- `GEMINI_API_KEY` は Secret Manager `gemini-api-key:latest` から注入する。
- ヘルスチェックは `/health`。`/healthz` は Cloud Run / Google Front End 側で横取りされることがあるため使わない。

### Firebase Hosting

- site: `agentforge-devops`
- `frontend/dist` を配信する。
- `/api/**` は Cloud Run `agentforge-core-api` へ rewrite する。
- `npm run build` 後に Hosting を更新しないと、frontend の修正は本番に出ない。
- Firebase CLI がローカルのログイン状態を拾えない場合がある。その場合は gcloud access token + Firebase Hosting REST API で deploy する。
- REST API を使う場合は `X-Goog-User-Project: agentforge-498808` を付ける。これが無いと project 取得や quota で失敗することがある。

### デプロイ前確認

最低限、以下を通す。

```powershell
pytest backend\tests\test_templates.py backend\tests\test_feature_worker_task_manager.py backend\tests\test_feature_worker_schedule.py backend\tests\test_web_search_tool.py
cd frontend
npm run build
```

変更範囲が広い場合は backend 全体の pytest と frontend build を実行する。

---

## 2. 事前設定

PowerShell 例:

```powershell
$env:PROJECT = "agentforge-498808"
$env:REGION = "asia-northeast1"
gcloud config set project $env:PROJECT
gcloud auth list
```

Cloud Run 実行サービスアカウントに必要な権限:

```powershell
$SA = "217469091476-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding gemini-api-key `
  --member="serviceAccount:$SA" `
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $env:PROJECT `
  --member="serviceAccount:$SA" `
  --role="roles/datastore.user"
```

通常は初回設定済みなので毎回は不要。

---

## 3. Backend を Cloud Run へデプロイ

`backend/` ディレクトリから実行する。

```powershell
cd D:\github\airpocket-soundman\AgentForge\backend

gcloud run deploy agentforge-core-api `
  --source . `
  --region=asia-northeast1 `
  --allow-unauthenticated `
  --min-instances=0 `
  --set-env-vars="APP_ENV=prod,GOOGLE_CLOUD_PROJECT=agentforge-498808,GOOGLE_CLOUD_REGION=asia-northeast1,ALLOWED_EMAILS=yamashita.3154@gmail.com;airpocket.soundman@gmail.com,GUEST_ACCESS_ENABLED=true" `
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" `
  --quiet
```

確認:

```powershell
gcloud run services describe agentforge-core-api `
  --region=asia-northeast1 `
  --format="json(status.latestReadyRevisionName,status.url,status.traffic)"

Invoke-WebRequest -UseBasicParsing `
  -Uri "https://agentforge-core-api-cwmxwrvkaa-an.a.run.app/health" |
  Select-Object -ExpandProperty Content
```

`/health` が `{"status":"ok","service":"agentforge-core-api"}` を返せば backend は起動している。

---

## 4. Frontend を Firebase Hosting へデプロイ

### 4.1 標準手順: Firebase CLI

```powershell
cd D:\github\airpocket-soundman\AgentForge\frontend
npm run build

cd D:\github\airpocket-soundman\AgentForge
firebase deploy --only hosting:agentforge-devops --project agentforge-498808
```

認証エラーが出る場合:

```powershell
firebase login
firebase projects:list
```

それでも CLI が認証状態を拾えない場合は 4.2 の REST API 手順を使う。

### 4.2 代替手順: Firebase Hosting REST API

Firebase CLI が `Failed to authenticate, have you run firebase login?` などで失敗する場合の手順。

このスクリプトは `frontend/dist` の全ファイルを gzip 圧縮し、圧縮後 SHA256 hex を Firebase Hosting API に登録して live release を作成する。

```powershell
$ErrorActionPreference = "Stop"
$project = "agentforge-498808"
$site = "agentforge-devops"
$dist = (Resolve-Path ".\frontend\dist").Path
$token = (gcloud auth print-access-token).Trim()
$jsonHeaders = @{
  Authorization = "Bearer $token"
  "X-Goog-User-Project" = $project
  "Content-Type" = "application/json"
}

function ConvertTo-Hex([byte[]]$bytes) {
  -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Compress-Gzip([byte[]]$bytes) {
  $ms = New-Object System.IO.MemoryStream
  $gzip = New-Object System.IO.Compression.GZipStream(
    $ms,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
  )
  $gzip.Write($bytes, 0, $bytes.Length)
  $gzip.Dispose()
  $out = $ms.ToArray()
  $ms.Dispose()
  $out
}

$createBody = @{
  config = @{
    rewrites = @(
      @{ glob = "/api/**"; run = @{ serviceId = "agentforge-core-api"; region = "asia-northeast1" } },
      @{ glob = "**"; path = "/index.html" }
    )
  }
  labels = @{ "deployment-tool" = "codex-rest" }
} | ConvertTo-Json -Depth 10

$version = Invoke-RestMethod `
  -Method Post `
  -Headers $jsonHeaders `
  -Uri "https://firebasehosting.googleapis.com/v1beta1/sites/$site/versions" `
  -Body $createBody
$versionId = ($version.name -split "/")[-1]

$files = @{}
$gzipByHash = @{}
$sha256 = [Security.Cryptography.SHA256]::Create()
Get-ChildItem -Path $dist -Recurse -File | ForEach-Object {
  $relative = $_.FullName.Substring($dist.Length + 1).Replace([IO.Path]::DirectorySeparatorChar, "/")
  $path = "/$relative"
  $raw = [IO.File]::ReadAllBytes($_.FullName)
  $gz = Compress-Gzip $raw
  $hash = ConvertTo-Hex ($sha256.ComputeHash($gz))
  $files[$path] = $hash
  $gzipByHash[$hash] = $gz
}

$populateBody = @{ files = $files } | ConvertTo-Json -Depth 10
$populate = Invoke-RestMethod `
  -Method Post `
  -Headers $jsonHeaders `
  -Uri "https://firebasehosting.googleapis.com/v1beta1/sites/$site/versions/$versionId`:populateFiles" `
  -Body $populateBody

$client = [System.Net.Http.HttpClient]::new()
$client.DefaultRequestHeaders.Authorization =
  [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $token)
foreach ($hash in @($populate.uploadRequiredHashes)) {
  $content = [System.Net.Http.ByteArrayContent]::new([byte[]]$gzipByHash[$hash])
  $content.Headers.ContentType =
    [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/octet-stream")
  $response = $client.PostAsync("$($populate.uploadUrl)/$hash", $content).GetAwaiter().GetResult()
  if (-not $response.IsSuccessStatusCode) {
    $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    throw "Upload failed $($response.StatusCode): $body"
  }
}
$client.Dispose()

$finalizeBody = @{ status = "FINALIZED" } | ConvertTo-Json
Invoke-RestMethod `
  -Method Patch `
  -Headers $jsonHeaders `
  -Uri "https://firebasehosting.googleapis.com/v1beta1/sites/$site/versions/$versionId`?updateMask=status" `
  -Body $finalizeBody | Out-Null

$versionName = [System.Uri]::EscapeDataString("sites/$site/versions/$versionId")
$releaseBody = @{ message = "Production deploy" } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Headers $jsonHeaders `
  -Uri "https://firebasehosting.googleapis.com/v1beta1/sites/$site/channels/live/releases?versionName=$versionName" `
  -Body $releaseBody
```

注意:

- `populateFiles` に渡す hash は **gzip 後の SHA256 hex**。
- upload body も gzip 後の bytes。
- `Invoke-WebRequest -Body byte[]` はバイト列が崩れることがあるため、upload は `.NET HttpClient` の `ByteArrayContent` を使う。
- release 作成時の `versionName` は body ではなく query parameter。

---

## 5. 本番反映後の確認

### Backend

```powershell
gcloud run services describe agentforge-core-api `
  --region=asia-northeast1 `
  --format="value(status.latestReadyRevisionName,status.url)"

Invoke-WebRequest -UseBasicParsing `
  -Uri "https://agentforge-core-api-cwmxwrvkaa-an.a.run.app/health" |
  Select-Object -ExpandProperty Content
```

### Hosting

`npm run build` で生成された `frontend/dist/assets/index-*.js` が本番 HTML に含まれることを確認する。

```powershell
$asset = Get-ChildItem .\frontend\dist\assets -Filter "index-*.js" |
  Select-Object -First 1 -ExpandProperty Name
$url = "https://agentforge-devops.web.app/?v=deploy-check-$(Get-Date -Format yyyyMMddHHmmss)"
$html = (Invoke-WebRequest -UseBasicParsing -Uri $url).Content
if ($html -match [regex]::Escape("assets/$asset")) {
  "hosting: new frontend asset found"
} else {
  "hosting: expected asset not found"
}
```

最新 release:

```powershell
$token = (gcloud auth print-access-token).Trim()
$headers = @{
  Authorization = "Bearer $token"
  "X-Goog-User-Project" = "agentforge-498808"
}
Invoke-RestMethod `
  -Headers $headers `
  -Uri "https://firebasehosting.googleapis.com/v1beta1/sites/agentforge-devops/channels/live/releases?pageSize=1" |
  ConvertTo-Json -Depth 8
```

### UI スモーク

- `https://agentforge-devops.web.app` を cache bust 付きで開く。
- 通常ログインまたはゲストログインで入れる。
- メインチャット、デフォルトアプリ生成、アプリチャットの最低限操作を確認する。
- 直近で触った機能は本番 UI で直接確認する。

---

## 6. ロールバック

### Cloud Run

直前 revision へ戻す:

```powershell
gcloud run revisions list `
  --service=agentforge-core-api `
  --region=asia-northeast1

gcloud run services update-traffic agentforge-core-api `
  --region=asia-northeast1 `
  --to-revisions="<REVISION_NAME>=100"
```

### Firebase Hosting

Firebase Console の Hosting release history から rollback するか、REST API / Firebase CLI で過去 release を再指定する。

---

## 7. 現在の本番状態

最終確認: 2026-07-09

- Cloud Run: `agentforge-core-api-00020-rtd` が 100% traffic
- Cloud Run health: `/health` OK
- Firebase Hosting live release: `sites/agentforge-devops/channels/live/releases/1783582058547000`
- Hosting version: `sites/agentforge-devops/versions/fd910da04214771f`
- Firebase Auth: OAuth redirect URI `https://agentforge-devops.web.app/__/auth/handler` 登録済み
- `authDomain`: `agentforge-498808.firebaseapp.com`

将来は GitHub push → Cloud Build → Cloud Run / Hosting の CI/CD に置換予定。当面はこの手順を正準とする。
