# Сборка установщика FM27 Analyst для Windows.
# Требуется: Python 3.11+, Node 20+, Rust (rustup), WebView2 (есть в Windows 10/11).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "1/3 Ядро -> fm27-core.exe" -ForegroundColor Cyan
python -m pip install -e "core[windows]" pyinstaller
python -m PyInstaller --noconfirm --onefile --name fm27-core `
    --collect-data fm27_analyst --distpath build\core --workpath build\pyi --specpath build `
    core\run_core.py
Copy-Item build\core\fm27-core.exe app\src-tauri\fm27-core.exe -Force

Write-Host "2/3 Интерфейс" -ForegroundColor Cyan
Set-Location app
npm install

Write-Host "3/3 Установщик (NSIS/MSI)" -ForegroundColor Cyan
# Ядро кладётся рядом с FM27 Analyst.exe — оболочка запускает его сама
npm run tauri build -- --config '{\"bundle\":{\"resources\":{\"fm27-core.exe\":\"fm27-core.exe\"}}}'
Write-Host "Готово: app\src-tauri\target\release\bundle\" -ForegroundColor Green
