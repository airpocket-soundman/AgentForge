# scripts/

## claude_bridge.py — ローカルテスト用 Claude ブリッジ

ローカル開発時、LLM呼び出しを**本番Geminiの代わりにホストの Claude Code セッション**で行い、Gemini API課金を節約するためのブリッジ（IMPLEMENTATION_GUIDE.md §2.6）。

### 使い方
1. **ホスト**（`claude` CLIがインストール・ログイン済みのPC）で起動：
   ```bash
   python scripts/claude_bridge.py
   # -> http://0.0.0.0:8765 で待受
   ```
2. 別ターミナルでローカルスタックを起動：
   ```bash
   docker compose -f docker-compose.dev.yml up --build
   ```
   - backend は `APP_ENV=local` なので Gateway が自動で **claude-cli** プロバイダを選択。
   - backend → `http://host.docker.internal:8765/generate` でブリッジを呼ぶ。

### 動作確認
```bash
curl http://localhost:8765/health
# {"status":"ok","claude":true}

curl -s http://localhost:8765/generate -H "Content-Type: application/json" \
  -d '{"prompt":"次の文をJSONで返して: {\"ok\": true}","tier":"flash"}'
```

### プロバイダの切替（Gateway / §2.6）
- ローカル既定：`claude-cli`（このブリッジ）
- ブリッジ無しで完全オフライン：`docker-compose.dev.yml` の backend に `LLM_PROVIDER: stub` を設定
- ローカルで実Gemini検証：`backend/.env` に `GEMINI_API_KEY=...` ＋ `LLM_PROVIDER=gemini`
- 本番（Cloud Run）：既定 `gemini`（claude-cli はホスト前提のため本番では使えない）

### 環境変数
| 変数 | 既定 | 説明 |
|---|---|---|
| `CLAUDE_BRIDGE_PORT` | 8765 | 待受ポート |
| `CLAUDE_BRIDGE_HOST` | 0.0.0.0 | 待受ホスト（コンテナから到達するため。dev専用） |
| `CLAUDE_CMD` | claude | claude 実行コマンド |
| `CLAUDE_TIMEOUT` | 300 | 1呼び出しのタイムアウト秒 |
