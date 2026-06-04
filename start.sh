#!/usr/bin/env bash
# TESSR-LOGIC — full cold start on a Vast.ai (or any Linux) box.
# Brings up: Ollama -> Python venv + deps -> frontend build -> backend (uvicorn) -> public tunnel.
# Prints the URL to view the app. Safe to re-run.
#   cd /workspace/TESSR-LOGIC && ./start.sh
set -uo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
have() { command -v "$1" >/dev/null 2>&1; }

echo "==> 1/6  Ollama"
if have ollama; then
  if curl -s "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    echo "    ollama already serving."
  else
    echo "    starting ollama serve…"; nohup ollama serve > ollama.log 2>&1 & sleep 3
  fi
  # warn if no usable chat model present
  ollama list 2>/dev/null | grep -qiE "devstral|qwen|llama|mistral|coder" \
    && echo "    chat model present." \
    || echo "    WARNING: no chat model found — pull one, e.g. 'ollama pull devstral-small-2'."
else
  echo "    WARNING: ollama not installed. Install: curl -fsSL https://ollama.com/install.sh | sh"
fi

echo "==> 2/6  Python venv + deps"
# Respect an already-active venv (e.g. Vast images ship one); only create ./venv if none.
if [ -n "${VIRTUAL_ENV:-}" ]; then
  echo "    using active venv: $VIRTUAL_ENV"
elif [ -d venv ]; then # shellcheck disable=SC1091
  source venv/bin/activate
else
  python3 -m venv venv; # shellcheck disable=SC1091
  source venv/bin/activate
fi
pip install -r requirements.txt || echo "    (pip step had issues — see output above)"

echo "==> 3/6  Frontend build"
if [ -d frontend ]; then
  ( cd frontend && npm install && npm run build ) \
    || { echo "    frontend build failed — check node/npm and the output above"; }
fi

echo "==> 4/6  Backend (uvicorn) on :$PORT"
pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 1
nohup uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" > tessr.log 2>&1 &
sleep 5
CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/docs" || echo 000)
echo "    backend health: HTTP $CODE  ($([ "$CODE" = 200 ] && echo OK || echo 'check tessr.log'))"

echo "==> 5/6  Public tunnel (cloudflared)"
if have cloudflared; then
  pkill -f "cloudflared tunnel" 2>/dev/null || true
  sleep 1
  nohup cloudflared tunnel --url "http://localhost:$PORT" > cf.log 2>&1 &
  # wait for the URL to appear
  URL=""
  for i in $(seq 1 15); do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' cf.log 2>/dev/null | head -1)
    [ -n "$URL" ] && break
    sleep 1
  done
  [ -n "$URL" ] && echo "    tunnel: $URL" || echo "    tunnel not ready yet — check: grep trycloudflare cf.log"
else
  echo "    cloudflared not installed (skipping public URL). Local only: http://localhost:$PORT"
  echo "    install: see https://github.com/cloudflare/cloudflared/releases"
fi

echo "==> 6/6  View it"
echo "    Local:  http://localhost:$PORT"
[ -n "${URL:-}" ] && echo "    Public: $URL   <-- open this in your browser"
echo "==> done.  (logs: tessr.log, cf.log, ollama.log)  Health check anytime: ./verify.sh"
