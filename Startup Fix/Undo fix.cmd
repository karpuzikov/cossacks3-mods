@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0StartupFix.ps1" -Restore %*
pause
