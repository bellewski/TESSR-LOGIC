#!/usr/bin/env python3
"""
Verify a (local or remote/rented) Ollama GPU is wired up and fast BEFORE spending
rental time on real builds.

Checks, in order:
  1. Ollama reachable at the given host
  2. Required coder model is present (pulls listed if missing)
  3. A timed test generation -> reports tokens/sec (your speed signal)
  4. Whether TESSR's backend is pointed at this same host

Usage:
  python tools/verify_gpu.py                          # checks localhost:11434
  python tools/verify_gpu.py --host http://localhost:11434
  python tools/verify_gpu.py --host http://<vast-ip>:<port> --model qwen3-coder:30b
"""
import argparse
import time
import sys
import json

try:
    import httpx
except ImportError:
    print("httpx not installed (it ships with the backend). Run from the repo venv.")
    sys.exit(1)

PREFERRED = ["devstral-small:24b", "qwen3-coder:30b", "qwen3-coder-next", "qwen2.5-coder:7b"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:11434", help="Ollama base URL")
    ap.add_argument("--model", default="", help="model to test (default: first preferred one present)")
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="TESSR backend URL")
    args = ap.parse_args()
    host = args.host.rstrip("/")

    print(f"=== Verifying Ollama at {host} ===\n")

    # 1. Reachable + list models
    try:
        r = httpx.get(f"{host}/api/tags", timeout=10)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        print(f"[FAIL] Ollama not reachable at {host}: {e}")
        print("       - Is `ollama serve` running on the box?")
        print("       - If remote: did you expose port 11434 (OLLAMA_HOST=0.0.0.0) or open an SSH tunnel?")
        sys.exit(1)
    print(f"[ok]  Ollama reachable. {len(models)} model(s): {models}")

    # 2. Pick / check model
    model = args.model or next((m for m in PREFERRED if m in models), None)
    if not model:
        print(f"[FAIL] No usable coder model present. Pull one on the box, e.g.:")
        print(f"         ollama pull devstral-small:24b")
        sys.exit(1)
    if model not in models:
        print(f"[FAIL] Requested model '{model}' not present. Available: {models}")
        sys.exit(1)
    print(f"[ok]  Using model: {model}")

    # 3. Timed generation -> tokens/sec
    print(f"\n[..] Running a timed test generation on {model} ...")
    payload = {
        "model": model,
        "prompt": "Write a complete, valid index.html for a landing page with a header, one button, and a footer. Output only the file.",
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 400, "num_ctx": 8192},
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{host}/api/generate", json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[FAIL] Generation failed: {e}")
        sys.exit(1)
    elapsed = time.time() - t0
    toks = data.get("eval_count", 0)
    tps = toks / elapsed if elapsed else 0
    print(f"[ok]  Generated {toks} tokens in {elapsed:.1f}s  ->  {tps:.1f} tok/s")
    if tps >= 30:
        print("       SPEED: GOOD (clearly GPU-accelerated)")
    elif tps >= 12:
        print("       SPEED: OK (usable; on a real GPU expect faster)")
    else:
        print("       SPEED: SLOW (<12 tok/s) — likely CPU spill / model too big for VRAM. Check `nvidia-smi`/`rocm-smi`.")

    # 4. Is TESSR pointed here?
    print(f"\n=== TESSR backend wiring ({args.backend}) ===")
    try:
        s = httpx.get(f"{args.backend}/api/settings", timeout=5).json()
        cur = (s.get("ollama_base_url") or "").rstrip("/")
        print(f"[i]  TESSR ollama_base_url = {cur}")
        if cur == host:
            print("[ok] TESSR is pointed at THIS host. ✅")
        else:
            print(f"[!]  TESSR is NOT pointed here. Set it:")
            print(f'     curl -X PATCH {args.backend}/api/settings -H "Content-Type: application/json" -d "{{\\"ollama_base_url\\":\\"{host}\\"}}"')
    except Exception as e:
        print(f"[i]  Could not read TESSR settings ({e}); start the backend or set OLLAMA_BASE_URL in .env.")

    print("\n=== DONE. If speed is GOOD and TESSR points here, you're ready to run real builds. ===")


if __name__ == "__main__":
    main()
