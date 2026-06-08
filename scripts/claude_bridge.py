#!/usr/bin/env python3
"""Host-side Claude bridge for local AgentForge development.

Exposes `POST /generate` that runs the local `claude` CLI in print mode and
returns the text. This lets the containerized backend use the host's Claude Code
session as an LLM provider for local testing — so local runs don't spend Gemini
API quota (IMPLEMENTATION_GUIDE.md §2.6, memory: extra-mvp-decisions).

Run on the HOST (where `claude` is installed and logged in), NOT in Docker:

    python scripts/claude_bridge.py

The backend (in docker-compose.dev) reaches it at http://host.docker.internal:8765/generate.

Env:
    CLAUDE_BRIDGE_PORT  default 8765
    CLAUDE_BRIDGE_HOST  default 0.0.0.0  (must be reachable from the container; dev only)
    CLAUDE_CMD          default "claude"
    CLAUDE_TIMEOUT      default 300 (seconds per call)

Request JSON:  {"prompt": "...", "tier": "flash|pro", "model": "<optional>"}
Response JSON: {"text": "..."}  (or {"error": "..."} with HTTP 500)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("CLAUDE_BRIDGE_PORT", "8765"))
HOST = os.environ.get("CLAUDE_BRIDGE_HOST", "0.0.0.0")
CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")
TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "300"))


def run_claude(prompt: str, model: str | None) -> str:
    exe = shutil.which(CLAUDE_CMD) or CLAUDE_CMD
    cmd = [exe, "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"claude exited {proc.returncode}")
    out = (proc.stdout or "").strip()
    # `claude -p --output-format json` -> {"type":"result","result":"<text>", ...}
    try:
        data = json.loads(out)
        if isinstance(data, dict) and "result" in data:
            return str(data["result"])
    except json.JSONDecodeError:
        pass
    return out


def _send(handler: BaseHTTPRequestHandler, code: int, obj: dict) -> None:
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("", "/health"):
            _send(self, 200, {"status": "ok", "claude": bool(shutil.which(CLAUDE_CMD))})
        else:
            _send(self, 404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/generate":
            _send(self, 404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            text = run_claude(body.get("prompt", ""), body.get("model") or None)
            _send(self, 200, {"text": text})
        except Exception as exc:  # noqa: BLE001 — report to caller, keep serving
            _send(self, 500, {"error": str(exc)})

    def log_message(self, fmt, *args):  # quieter, prefixed
        sys.stderr.write("[claude-bridge] " + (fmt % args) + "\n")


if __name__ == "__main__":
    found = shutil.which(CLAUDE_CMD)
    if not found:
        print(f"[claude-bridge] WARNING: '{CLAUDE_CMD}' not found on PATH.", file=sys.stderr)
    print(f"[claude-bridge] listening on http://{HOST}:{PORT}  (claude={found})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
