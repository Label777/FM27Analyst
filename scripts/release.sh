#!/usr/bin/env bash
# Новый релиз FM27 Analyst: версия во всех местах, плагин в ядре, запуск сборки установщика в GitHub Actions.
#   scripts/release.sh 0.2.1                         — без пересборки плагина
#   GAME="<папка FM27 с BepInEx>" scripts/release.sh 0.2.1 — с пересборкой плагина под файлы игры
set -euo pipefail
cd "$(dirname "$0")/.."
V="${1:?укажите версию, например 0.2.1}"
python3 - "$V" <<'PY'
import json, re, sys
v = sys.argv[1]
p = "app/src-tauri/tauri.conf.json"; d = json.load(open(p)); d["version"] = v
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
for p, pat, rep in [("app/src-tauri/Cargo.toml", r'^version = ".*?"', f'version = "{v}"'),
                    ("app/package.json", r'"version": ".*?"', f'"version": "{v}"'),
                    ("core/fm27_analyst/__init__.py", r'__version__ = ".*?"', f'__version__ = "{v}"')]:
    s = open(p).read(); open(p, "w").write(re.sub(pat, rep, s, count=1, flags=re.M))
PY
if [ -n "${GAME:-}" ]; then
  (cd bridge && dotnet build src/FM27Bridge -c Release "-p:Game=$GAME" -v q -nologo)
  cp bridge/src/FM27Bridge/bin/Release/net6.0/FM27AnalystBridge.dll core/fm27_analyst/data/plugin/
fi
(cd core && python3 -m pytest -q)
(cd app && npx tsc --noEmit -p .)
git add -A
git commit -m "Релиз $V" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_018hCavAf3dp31UifaevxR8W"
git push origin main
# Сборку запускаем вручную (workflow_dispatch): тег v$V создаст сам шаг «Релиз».
gh api -X POST repos/Label777/FM27Analyst/actions/workflows/release.yml/dispatches -f ref=main
echo "Сборка v$V запущена: GitHub → Actions → release."
