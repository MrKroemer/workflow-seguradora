@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo.
echo === RPA PBSeg - Setup Completo ===
echo.

REM Detecta Python
set "PY="
where py >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "PY=py -3"
    echo [OK] Python: py -3
    goto :install
)
where python >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "PY=python"
    echo [OK] Python: python
    goto :install
)
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    echo [OK] Python: .venv
    goto :install
)
echo [ERRO] Python nao encontrado.
pause
exit /b 1

:install
echo.
echo [1/4] Instalando dependencias...
%PY% -m pip install --upgrade pip
%PY% -m pip install openpyxl flask playwright pywinauto pypdf
echo.

echo [2/4] Instalando Chromium para Playwright...
%PY% -m playwright install chromium
echo.

echo [3/4] Criando pastas...
if not exist "outputs" mkdir outputs
if not exist "web" mkdir web
echo [OK] Pastas prontas.
echo.

echo [4/4] Validando...
set "PYTHONPATH=%cd%\src"
%PY% -c "import openpyxl; print('[OK] openpyxl')"
%PY% -c "import flask; print('[OK] flask')"
%PY% -c "import playwright; print('[OK] playwright')"
echo.

echo === CONCLUIDO ===
echo.
echo Para usar: scripts\abrir_painel.bat
echo.
pause
