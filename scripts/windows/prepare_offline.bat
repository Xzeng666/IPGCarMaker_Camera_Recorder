@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_offline.ps1"
if errorlevel 1 pause
