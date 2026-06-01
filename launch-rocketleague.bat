@echo off
REM Launch Steam and Rocket League.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-rocketleague.ps1" %*
