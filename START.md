# TESSR-LOGIC — Start & View (Vast.ai / Linux box)

The app = a **FastAPI backend** (serves the built React frontend on one port, default 8000) + a
local **Ollama** model. To view it remotely you expose port 8000 with a **Cloudflare quick tunnel**.

## TL;DR — one command
```bash
cd /workspace/TESSR-LOGIC && ./start.sh
```
That brings up Ollama → venv + deps → frontend build → backend → public tunnel, then prints a
`https://<random>.trycloudflare.com` URL. **Open that URL in your browser** to use the app.

Already set up and just pulled new code? Use `./update.sh` (pull + rebuild + restart), then start a
tunnel if you don't have one. Check health any time with `./verify.sh`.

---

## First-time setup on a brand-new box (if `start.sh` warns)
Run these once, then `./start.sh` handles the rest.

```bash
# 1) Ollama + a chat model
curl -fsSL https://ollama.com/install.sh | sh
nohup ollama serve > ollama.log 2>&1 &
ollama pull devstral-small-2            # the chat/code model TESSR uses

# 2) Get the code (if not already on the box)
cd /workspace
git clone <your repo url> TESSR-LOGIC   # or it's already at /workspace/TESSR-LOGIC
cd TESSR-LOGIC
git checkout universal-pipeline-workshop

# 3) Tooling (most Vast images have these; install if missing)
#    python3 + venv, node + npm, and cloudflared for the public URL.

# 4) Optional power-ups (learning memory + vision)
./powerup.sh
```

## What runs where
- **Backend + frontend:** one process — `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
  (FastAPI serves the React build from `frontend/dist`). Logs → `tessr.log`.
- **Ollama:** `http://localhost:11434`. Logs → `ollama.log`.
- **Public view:** `cloudflared tunnel --url http://localhost:8000` → prints a trycloudflare URL.
  Logs → `cf.log`. (Note: the tunnel URL CHANGES every restart, and has a ~100s per-request limit.)

## Viewing
- **On the box:** `http://localhost:8000`
- **From anywhere:** the `https://….trycloudflare.com` URL `start.sh` prints.
- If the tunnel URL is lost: `grep trycloudflare cf.log | tail -1`

## Stopping / restarting
```bash
pkill -f "uvicorn backend.main"     # stop backend
pkill -f "cloudflared tunnel"       # stop tunnel
./start.sh                          # bring it all back up
```

---

## Prompt you can give an AI assistant
> "I'm on a Vast.ai Linux box. The TESSR-LOGIC repo is at /workspace/TESSR-LOGIC on branch
> universal-pipeline-workshop. Start the whole app for viewing: make sure Ollama is serving with a
> chat model, create/activate the Python venv and install requirements.txt, build the frontend
> (npm run build), start the backend with uvicorn backend.main:app on 0.0.0.0:8000, and start a
> cloudflared quick tunnel to port 8000. Then give me the public trycloudflare URL. There's a
> ./start.sh that does all of this — run it and report the URL and the backend health code."
