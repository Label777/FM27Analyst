# FM27 Analyst — автообновление с GitHub и установка плагина в игру.
# Запускается из «Запустить FM27 Analyst.bat» перед стартом помощника.
# Ничего не удаляет из игры и сейвов: обновляет только папку помощника и файл плагина FM27AnalystBridge.dll.

param([switch]$NoUpdate)

$ErrorActionPreference = "Stop"
$Repo = "Label777/FM27Analyst"
$Root = Split-Path -Parent $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say($text) { Write-Host $text }

function Get-LocalVersion {
    $f = Join-Path $Root "VERSION"
    if (Test-Path $f) { return (Get-Content $f -Raw).Trim() }
    return ""
}

function Update-App {
    $local = Get-LocalVersion
    try {
        $remote = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 `
            -Uri "https://raw.githubusercontent.com/$Repo/main/release/VERSION").Content.Trim()
    } catch {
        Say "Обновления не проверены (нет связи с GitHub): $($_.Exception.Message)"
        return
    }
    if ($remote -eq $local) {
        Say "FM27 Analyst $local — последняя версия."
        return
    }
    Say "Обновляю FM27 Analyst: $local -> $remote ..."
    $tmp = Join-Path $env:TEMP ("fm27-update-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp "main.zip"
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 -OutFile $zip `
            -Uri "https://codeload.github.com/$Repo/zip/refs/heads/main"
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $src = Get-ChildItem -Path $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName "release\VERSION") } | Select-Object -First 1
        if (-not $src) { throw "в архиве нет release\VERSION" }

        $oldDeps = ""
        $pyproject = Join-Path $Root "core\pyproject.toml"
        if (Test-Path $pyproject) { $oldDeps = (Get-FileHash $pyproject).Hash }

        # ядро: заменяем код целиком (старые файлы не должны остаться)
        $coreDst = Join-Path $Root "core"
        if (Test-Path (Join-Path $coreDst "fm27_analyst")) { Remove-Item -Recurse -Force (Join-Path $coreDst "fm27_analyst") }
        New-Item -ItemType Directory -Force -Path $coreDst | Out-Null
        Copy-Item -Recurse -Force (Join-Path $src.FullName "core\fm27_analyst") $coreDst
        Copy-Item -Force (Join-Path $src.FullName "core\pyproject.toml") $coreDst

        # интерфейс и плагин
        foreach ($dir in @("web", "plugin")) {
            $dst = Join-Path $Root $dir
            if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
            Copy-Item -Recurse -Force (Join-Path $src.FullName "release\$dir") $dst
        }
        # служебные файлы (сам ярлык запуска не трогаем: он сейчас выполняется)
        Copy-Item -Force (Join-Path $src.FullName "release\tools\*") (Join-Path $Root "tools")
        Copy-Item -Force (Join-Path $src.FullName "release\VERSION") $Root
        Copy-Item -Force (Join-Path $src.FullName "release\ПРОЧТИ.txt") $Root -ErrorAction SilentlyContinue

        $venvPy = Join-Path $Root ".venv\Scripts\python.exe"
        if ((Test-Path $venvPy) -and ($oldDeps -ne (Get-FileHash $pyproject).Hash)) {
            Say "Изменились зависимости — доустанавливаю..."
            & $venvPy -m pip install -q -e $coreDst
        }
        Say "Готово: FM27 Analyst $remote."
    } catch {
        Say "Обновить не удалось: $($_.Exception.Message). Запускаю текущую версию."
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Find-GameFolders {
    $found = @()
    $steam = $null
    try { $steam = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction Stop).SteamPath } catch { }
    $libs = @()
    if ($steam) {
        $libs += $steam
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            foreach ($m in [regex]::Matches((Get-Content $vdf -Raw), '"path"\s+"([^"]+)"')) {
                $libs += $m.Groups[1].Value.Replace("\\", "\")
            }
        }
    }
    foreach ($lib in ($libs | Select-Object -Unique)) {
        $common = Join-Path $lib "steamapps\common"
        if (Test-Path $common) {
            $found += Get-ChildItem -Path $common -Directory -Filter "Football Manager 27*" |
                Where-Object { Test-Path (Join-Path $_.FullName "BepInEx\plugins") } |
                ForEach-Object { $_.FullName }
        }
    }
    return $found | Select-Object -Unique
}

function Install-Plugin {
    $dll = Join-Path $Root "plugin\FM27AnalystBridge.dll"
    if (-not (Test-Path $dll)) { return }
    $games = Find-GameFolders
    if (-not $games) {
        Say "Плагин: не нашёл FM27 с BepInEx (папка BepInEx\plugins). Установите BepInEx — см. ПРОЧТИ.txt."
        return
    }
    foreach ($game in $games) {
        $dstDir = Join-Path $game "BepInEx\plugins\FM27AnalystBridge"
        $dst = Join-Path $dstDir "FM27AnalystBridge.dll"
        if ((Test-Path $dst) -and ((Get-FileHash $dst).Hash -eq (Get-FileHash $dll).Hash)) {
            Say "Плагин в игре актуален: $game"
            continue
        }
        if (Get-Process -Name "fm" -ErrorAction SilentlyContinue) {
            Say "Плагин: есть новая версия, но FM27 запущена. Закройте игру и перезапустите помощника."
            continue
        }
        try {
            New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
            Copy-Item -Force $dll $dst
            Say "Плагин обновлён: $dst"
        } catch {
            Say "Плагин не обновлён: $($_.Exception.Message)"
        }
    }
}

if (-not $NoUpdate) { Update-App }
Install-Plugin
