#!/usr/bin/env bash
# Готовит release/ для автообновления: интерфейс, плагин, номер версии.
# Плагин собирается только при наличии файлов игры (BepInEx/interop): GAME="<папка FM27>" scripts/make-release.sh
set -euo pipefail
cd "$(dirname "$0")/.."
(cd app && npx tsc --noEmit -p . && npx vite build >/dev/null)
rm -rf release/web && mkdir -p release/web && cp -r app/dist/* release/web/
if [ -n "${GAME:-}" ]; then
  (cd bridge && dotnet build src/FM27Bridge -c Release "-p:Game=$GAME" -v q -nologo)
  mkdir -p release/plugin && cp bridge/src/FM27Bridge/bin/Release/net6.0/FM27AnalystBridge.dll release/plugin/
fi
test -f release/plugin/FM27AnalystBridge.dll || { echo "Нет release/plugin/FM27AnalystBridge.dll — укажите GAME=" >&2; exit 1; }
echo "$(date -u +%Y.%m.%d.%H%M)" > release/VERSION
echo "release $(cat release/VERSION) готов"
