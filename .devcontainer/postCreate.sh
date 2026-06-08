#!/usr/bin/env bash
# Runs once when the Dev Container is created. Builds the reproducible dev env.
set -euo pipefail

echo "[postCreate] Installing firebase-tools (global)..."
npm install -g firebase-tools

echo "[postCreate] Creating backend venv and installing deps..."
python -m venv backend/.venv
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install -r backend/requirements.txt

if [ -f frontend/package.json ]; then
  echo "[postCreate] Installing frontend deps..."
  (cd frontend && npm ci)
fi

echo "[postCreate] Done. Versions:"
python --version
node --version
( gcloud --version | head -n1 ) || true
( firebase --version ) || true
