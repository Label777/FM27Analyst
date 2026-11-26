@echo off
chcp 65001 >nul
rem Запуск ядра FM27 Analyst. Вызывается из «Запустить FM27 Analyst.bat» после проверки обновлений.
cd /d "%~dp0.."

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  if not defined PY goto nopython
  echo Первый запуск: ставлю зависимости, это 1-3 минуты...
  %PY% -m venv .venv || goto nopython
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e core || goto fail
  rem захват экрана для кнопки «Анализ экрана» — не обязателен
  ".venv\Scripts\python.exe" -m pip install "mss>=9.0" "windows-capture>=1.4" "pygetwindow>=0.0.9"
)

".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || goto oldpython

set "FM27_WEB_DIR=%CD%\web"
echo.
echo FM27 Analyst запущен: http://127.0.0.1:8727
echo Не закрывайте это окно, пока пользуетесь помощником.
echo.
start "" "http://127.0.0.1:8727"
".venv\Scripts\python.exe" -m fm27_analyst.server
pause
exit /b

:nopython
echo.
echo Не найден Python. Установите Python 3.12 с python.org
echo (при установке отметьте "Add python.exe to PATH") и запустите помощника снова.
pause
exit /b 1

:oldpython
echo.
echo Нужен Python 3.11 или новее. Установите Python 3.12 с python.org,
echo удалите папку .venv в папке помощника и запустите его снова.
pause
exit /b 1

:fail
echo.
echo Не удалось установить зависимости. Пришлите Claude текст из этого окна.
pause
exit /b 1
