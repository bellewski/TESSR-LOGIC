# TESSR-LOGIC — Rented GPU Runbook (Vast.ai)

Goal: connect TESSR to a rented NVIDIA GPU, **verify it's wired and GPU-fast**, then run
real builds — with **zero wasted rental time**. Do all the local prep BEFORE you rent.

Recommended instance: **single RTX 4090 48GB, high reliability, fast network**
(e.g. Vast #36839944, Texas, ~$1.15/hr). 48GB fits the big coders with headroom.

---

## A. Before you rent (free, do now)
- [x] Backend committed & ready (compiles, 52 routes).
- [x] `tools/verify_gpu.py` present.
- Decide the coder model: **`devstral-small:24b`** (agentic, fits 24/48GB) or
  **`qwen3-coder:30b`** (fast MoE). On 48GB you can also run `qwen3-coder-next`.

---

## B. Launch the Vast.ai instance
1. Pick an image with CUDA + Ollama, or a base Ubuntu/CUDA image (you'll install Ollama).
2. **Confirm 48GB** once in: `nvidia-smi` → check "Memory" total.
3. Note the instance's **SSH command** (Vast shows `ssh -p <PORT> root@<IP>`).

---

## C. On the rented box — install + pull models
```bash
# install Ollama (if not in the image)
curl -fsSL https://ollama.com/install.sh | sh

# make Ollama listen so a tunnel/remote can reach it
export OLLAMA_HOST=0.0.0.0:11434
ollama serve &          # leave running

# pull the coder (datacenter network = fast)
ollama pull devstral-small:24b
# optional extras:
ollama pull qwen3-coder:30b
ollama pull qwen3-coder-next      # 48GB only

ollama list                       # confirm they're there
nvidia-smi                        # confirm the GPU + 48GB
```

---

## D. Connect TESSR to it — choose ONE

### Option 1 — SSH tunnel (RECOMMENDED: secure, no config change)
On **your local PC** (keeps TESSR pointed at localhost, doesn't expose Ollama to the internet):
```powershell
# stop LOCAL ollama first so :11434 is free for the tunnel
.\stop-tessr.bat            # or: Get-Process ollama* | Stop-Process -Force

# open the tunnel (use the Vast SSH host/port)
ssh -N -L 11434:localhost:11434 -p <PORT> root@<IP>
```
Now `localhost:11434` on your PC = the rented GPU. TESSR needs **no change** (it already uses localhost:11434). Start TESSR backend: `TESSR-LOGIC.bat`.

### Option 2 — Direct connect (simpler, less secure)
Point TESSR straight at the instance (only if you trust the network / it's short-lived):
```powershell
# set TESSR's Ollama URL to the rented box
curl -X PATCH http://127.0.0.1:8000/api/settings -H "Content-Type: application/json" -d "{\"ollama_base_url\":\"http://<IP>:<PORT>\"}"
```
(`<PORT>` = whatever Vast mapped to 11434.)

---

## E. VERIFY before spending build time (the money-saver)
From the repo on your local PC:
```powershell
# Option 1 (tunnel): host is localhost
python tools/verify_gpu.py --host http://localhost:11434 --model devstral-small:24b

# Option 2 (direct): host is the instance
python tools/verify_gpu.py --host http://<IP>:<PORT> --model devstral-small:24b
```
You want: **Ollama reachable ✅, model present ✅, speed GOOD (≥30 tok/s) ✅, TESSR pointed here ✅.**
If speed is SLOW → model too big for VRAM or CPU fallback — fix before building.

---

## F. Set TESSR's per-role models for the rental
```powershell
curl -X PATCH http://127.0.0.1:8000/api/settings -H "Content-Type: application/json" -d "{\"ollama_fast_model\":\"devstral-small:24b\",\"ollama_creative_model\":\"qwen3-coder:30b\"}"
```
(On a 24GB box, set BOTH to the same model — e.g. `devstral-small:24b` — to avoid model swapping.)

---

## G. Run real builds & judge quality
- Open TESSR (`http://localhost:5173`), run your prompts (restaurant fullstack, multi-page site).
- Watch Build Pipeline; view results in Artifacts → Live Preview.
- This is the real test: does a 24B–30B coder make TESSR produce working, good-looking output?

---

## H. When done — stop paying
- **DESTROY the Vast.ai instance** (not just stop — destroyed = no more charges).
- Locally: close the SSH tunnel; `stop-tessr.bat` to shut everything down.

---

## I. If tests pass → buy hardware
- A box like the **Corsair AI Workstation 300** (Ryzen AI Max, 48GB unified) runs these models
  **offline/owned** — verify Ollama+ROCm support for its Radeon iGPU first.
- Or an **NVIDIA RTX 4090 (24GB)** desktop for max speed (CUDA), accepting 24GB capacity.
- Either way: the rental tells you the model + quality target; then buy hardware that matches.

---

### Cost math
~$1.15/hr × a 3–4 hr verification+testing session ≈ **$4–5 total**. Prep locally so none of
that is wasted on setup.
