@echo off
REM Double-click to stop TESSR-LOGIC: backend, frontend, and Ollama.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-tessr.ps1" %*
