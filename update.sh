#!/usr/bin/env bash
# TESSR-LOGIC — one-command catch-up for the box.
# Pulls every latest commit, rebuilds the frontend, restarts the backend, prints status.
# Usage:  ./update.sh        (from the repo root, e.g. /workspace/TESSR-LOGIC)
set -uo pipefail

BRANCH="universal-pipeline-workshop"
PORT="8000"
cd "$(dirname "$0")"

echo "==> 1/4  git pull ($BRANCH)"
git pull origin "$BRANCH" || { echo "git pull failed"; exit 1; }
echo "    now at: $(git rev-parse --short HEAD)  ($(git log -1 --pretty=%s))"

# Activate venv if present (don't fail if it isn't)
if [ -f venv/bin/activate ]; then # shellcheck disable=SC1091
  source venv/bin/activate
fi

echo "==> 2/4  pip install -r requirements.txt (quiet)"
pip install -q -r requirements.txt 2>/dev/null || echo "    (pip skipped/failed — continuing)"

echo "==> 3/4  rebuild frontend"
if [ -d frontend ]; then
  ( cd frontend && npm run build ) || { echo "frontend build failed"; exit 1; }
else
  echo "    (no frontend/ dir — skipped)"
fi

echo "==> 4/4  restart backend on :$PORT"
pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 1
nohup uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" > tessr.log 2>&1 &
sleep 4

CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/docs" || echo 000)
if [ "$CODE" = "200" ]; then
  echo "==> OK — backend healthy on :$PORT (HTTP $CODE)"
else
  echo "==> WARNING — backend not healthy yet (HTTP $CODE). Check: tail -30 tessr.log"
fi

# Reminders for the optional, non-git pieces
command -v ollama >/dev/null 2>&1 && {
  ollama list 2>/dev/null | grep -qi nomic || \
    echo "    note: 'nomic-embed-text' not installed -> learning memory is OFF. Enable: ollama pull nomic-embed-text"
}
echo "==> done."
