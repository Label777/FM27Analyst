@echo off
chcp 65001 >nul
title FM27 Analyst
rem Этот файл не меняется при обновлениях: всё остальное обновляет tools\update.ps1.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\update.ps1"
call "%~dp0tools\start-core.bat"
