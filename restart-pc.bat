@echo off
REM Cleanly stop TESSR-LOGIC and restart the PC (cancellable countdown).
REM To cancel a pending restart:  shutdown /a
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-pc.ps1" %*
