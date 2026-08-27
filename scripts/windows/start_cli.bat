@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_cli.ps1"
if errorlevel 1 pause
