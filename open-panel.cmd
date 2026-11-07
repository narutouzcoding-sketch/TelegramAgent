@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-panel.ps1" %*
if errorlevel 1 pause
