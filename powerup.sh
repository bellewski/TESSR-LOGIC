#!/usr/bin/env bash
# TESSR-LOGIC — enable the optional power-ups (one-time). Safe to re-run.
#   1) Learning memory     -> nomic-embed-text  (Connectors + fix-learning)
#   2) Vision critique      -> playwright + chromium + a local vision model (agents that SEE)
# Requires Ollama running. Run from the repo root:  ./powerup.sh
set -uo pipefail
cd "$(dirname "$0")"
VISION_MODEL="${VISION_MODEL:-llava}"   # override: VISION_MODEL=moondream ./powerup.sh  (smaller, less VRAM)

have() { command -v "$1" >/dev/null 2>&1; }
ollama_has() { ollama list 2>/dev/null | grep -qi "$1"; }

echo "==> 1/3  Learning memory (embeddings)"
if have ollama; then
  if ollama_has nomic-embed-text; then echo "    nomic-embed-text already installed."
  else echo "    pulling nomic-embed-text (~280MB)…"; ollama pull nomic-embed-text; fi
else
  echo "    SKIP: ollama not found."
fi

echo "==> 2/3  Headless browser for vision (Playwright + Chromium)"
if [ -f venv/bin/activate ]; then # shellcheck disable=SC1091
  source venv/bin/activate; fi
if python -c "import playwright" 2>/dev/null; then
  echo "    playwright python package present."
else
  echo "    pip install playwright…"; pip install -q playwright || echo "    (pip failed)"
fi
echo "    installing chromium browser (+ system deps)…"
python -m playwright install chromium 2>/dev/null || echo "    (chromium install failed — check pip step)"
python -m playwright install-deps chromium 2>/dev/null || true   # needs root; non-fatal

echo "==> 3/3  Vision model ($VISION_MODEL)"
if have ollama; then
  if ollama_has "$VISION_MODEL"; then echo "    $VISION_MODEL already installed."
  else echo "    pulling $VISION_MODEL (several GB)…"; ollama pull "$VISION_MODEL"; fi
else
  echo "    SKIP: ollama not found."
fi

echo
echo "==> verify"
ollama_has nomic-embed-text && echo "  [ok] learning memory model present" || echo "  [--] nomic-embed-text missing"
python -c "import playwright" 2>/dev/null && echo "  [ok] playwright importable" || echo "  [--] playwright missing"
ollama_has "$VISION_MODEL" && echo "  [ok] vision model ($VISION_MODEL) present" || echo "  [--] vision model missing"
echo
echo "==> Restart the backend so it picks up the new capabilities:"
echo "    pkill -f 'uvicorn backend.main' ; sleep 1 && nohup uvicorn backend.main:app --host 0.0.0.0 --port 8000 > tessr.log 2>&1 &"
echo "    (or just run ./update.sh)"
echo "==> done."
