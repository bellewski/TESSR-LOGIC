#!/usr/bin/env bash
#
# Deploy TESSR-LOGIC on a GPU box (rented Vast.ai or owned) that already runs
# Ollama locally. Installs deps, builds the web UI, starts the backend, and points
# every agent at the local GPU model. Then you expose port 8000 via a tunnel and
# use the full TESSR site in your browser — all builds run on the box's GPU.
#
# Run from the repo root on the box:
#   git clone -b universal-pipeline-workshop https://github.com/bellewski/TESSR-LOGIC.git
#   cd TESSR-LOGIC && bash tools/setup-gpu-box.sh
#
# Override defaults via env:
#   TESSR_MODEL=qwen3-coder:30b  OLLAMA_URL=http://localhost:11434  TESSR_PORT=8000  bash tools/setup-gpu-box.sh
set -e

MODEL="${TESSR_MODEL:-devstral-small-2:latest}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
PORT="${TESSR_PORT:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==========================================================="
echo "  TESSR-LOGIC GPU-box setup"
echo "  model=$MODEL  ollama=$OLLAMA_URL  port=$PORT"
echo "==========================================================="

# --- 0. Ollama must be up with the model ---------------------------------
echo "[..] Checking Ollama at $OLLAMA_URL"
if ! curl -s --max-time 8 "$OLLAMA_URL/api/tags" | grep -q '"models"'; then
  echo "[!]  Ollama not reachable at $OLLAMA_URL."
  echo "     Start it first:  OLLAMA_HOST=0.0.0.0:11434 nohup ollama serve > /tmp/ollama.log 2>&1 &"
  echo "     And pull the model:  ollama pull $MODEL"
  exit 1
fi
echo "[ok] Ollama reachable"

# --- 1. Python deps ------------------------------------------------------
echo "[..] Installing Python deps"
pip install -q -r requirements.txt
echo "[ok] Python deps installed"

# --- 2. Node (for the web UI build + runtime QA) -------------------------
if ! command -v node >/dev/null 2>&1; then
  echo "[..] Installing Node.js"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1 || true
  apt-get install -y nodejs >/dev/null 2>&1 || echo "[!] Node install failed — UI build + runtime QA will be skipped"
fi
if command -v node >/dev/null 2>&1; then echo "[ok] Node $(node --version)"; fi

# --- 3. Build the web UI (so the backend serves the full site) -----------
if command -v npm >/dev/null 2>&1; then
  echo "[..] Building the TESSR web UI (npm install + build)"
  ( cd frontend && npm install --no-audit --no-fund >/dev/null 2>&1 && npm run build >/dev/null 2>&1 ) \
    && echo "[ok] Web UI built (backend will serve it)" \
    || echo "[!] UI build failed — backend API still works; check 'cd frontend && npm run build'"
  echo "[..] Installing runtime-QA checker deps"
  ( cd tools/runtime-check && npm install --no-audit --no-fund >/dev/null 2>&1 ) \
    && echo "[ok] Runtime QA enabled" || echo "[!] runtime-check deps failed — runtime QA will be skipped"
else
  echo "[!] npm not available — skipping UI build + runtime QA"
fi

# --- 4. Start the backend ------------------------------------------------
echo "[..] Starting TESSR backend on :$PORT"
pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 2
nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" > /tmp/tessr.log 2>&1 &
for i in $(seq 1 20); do
  curl -s --max-time 2 "http://localhost:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
if curl -s --max-time 3 "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
  echo "[ok] Backend UP on :$PORT"
else
  echo "[!] Backend not responding — check /tmp/tessr.log"; tail -20 /tmp/tessr.log; exit 1
fi

# --- 5. Point every agent at the local GPU model -------------------------
echo "[..] Pointing TESSR at $OLLAMA_URL with model $MODEL"
curl -s -X PATCH "http://localhost:$PORT/api/settings" -H "Content-Type: application/json" \
  -d "{\"ollama_base_url\":\"$OLLAMA_URL\",\"ollama_fast_model\":\"$MODEL\",\"ollama_creative_model\":\"$MODEL\",\"ollama_quality_model\":\"$MODEL\"}" >/dev/null
echo "[ok] TESSR pointed at the GPU model"

echo ""
echo "==========================================================="
echo "  DONE. TESSR is running on the GPU box."
echo "  Next:"
echo "   1) Expose port $PORT via a Cloudflare tunnel in the portal."
echo "   2) Open that tunnel URL in your browser = the full TESSR site."
echo "   3) Submit a prompt in Prompt Studio (or POST /api/builds)."
echo "  Logs: tail -f /tmp/tessr.log   |   GPU: watch -n1 nvidia-smi"
echo "==========================================================="
