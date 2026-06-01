@echo off
REM Double-click launcher for TESSR-LOGIC.
REM Starts backend + frontend and opens the website.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-tessr.ps1" %*
