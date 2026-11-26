@echo off
chcp 65001 >nul
rem Режим разработки: ядро в отдельном окне + приложение Tauri
cd /d "%~dp0.."
start "FM27 Analyst — ядро" cmd /k python -m fm27_analyst.server --port 8727
cd app
npm run tauri dev
