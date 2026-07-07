# TESSR-LOGIC — Customer Deployment Guide

## Quick Start (5 minutes)

### Option 1: Double-Click Start (Manual)
1. Double-click **`start.bat`**
2. Open browser to `http://localhost:8000`
3. Press `Ctrl+C` in the window to stop

### Option 2: Auto-Start Windows Service (Recommended)
1. **Right-click** `install-service.ps1` → **Run with PowerShell as Administrator**
2. Service installs and starts automatically
3. Open `http://localhost:8000` in any browser
4. Service auto-starts on every Windows boot

### Option 3: PyWin32 Service (Alternative)
```powershell
pip install pywin32
python service.py install
python service.py start
```

## Desktop Shortcut
Run `create-shortcut.ps1` (no admin needed) to add a desktop icon.

## Prerequisites
- Windows 10/11
- Python 3.11+ (must be in PATH)
- npm (for building frontend — only needed if modifying UI)

## Build Frontend (Only needed for UI changes)
```bash
cd frontend
npm install
npm run build
```
The backend auto-detects `frontend/dist/` and serves it.

## Configuring Build Output Directory

By default, builds are saved to a `workspace/builds/` folder relative to where `start.bat` runs. To change this:

1. Create a file named `.env` in the same folder as `start.bat`
2. Add a line like:
   ```
   WORKSPACE_PATH=C:\Your\Custom\BuildOutput
   ```
3. Restart the server

Any valid Windows path works — absolute or relative.

## Service Management

| Command | Action |
|---------|--------|
| `net start TESSR-LOGIC` | Start service |
| `net stop TESSR-LOGIC` | Stop service |
| `install-service.ps1 -Uninstall` | Remove service |
| `install-service.ps1 -Stop` | Stop without removing |

## Troubleshooting

**Port 8000 already in use?**
- Edit `install-service.ps1` or `start.bat` — change `--port 8000` to another port

**Service won't start?**
- Check `logs/service-err.log` and `logs/service-out.log`
- Ensure Python is in PATH: `python --version`

**Ollama not detected?**
- Install Ollama from https://ollama.com
- Verify: `ollama list` in Command Prompt


## Known-good hardware reference

| Tier | Example machine | Models | Experience |
|------|----------------|--------|------------|
| Minimum tested | RTX 4050 laptop (6GB VRAM), 16GB RAM | qwen2.5-coder:7b + hermes3:3b | Full pipeline works at GPU speed; one model loaded at a time |
| Recommended | 8-12GB VRAM (RTX 4060/3060 12GB), 16GB+ RAM | qwen2.5-coder:7b + llama3.1:8b | Comfortable headroom for 8192 context |
| Below minimum | 4GB VRAM or no supported GPU | 3b-class models only | CPU fallback is slow (~3-5 tok/s); expect long builds |

Set `OLLAMA_QUALITY_MODEL` in `.env` to match your tier — the default assumes 6GB+ VRAM.
