@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
set "PYTHONPATH=%cd%\src"

REM Detecta Python
set "PY="
where py >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "PY=py -3"
    goto :run
)
where python >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "PY=python"
    goto :run
)
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    goto :run
)
echo [ERRO] Python nao encontrado.
pause
exit /b 1

:run
echo Iniciando RPA PBSeg...
%PY% -m rpa_corretora.webapp
if !ERRORLEVEL! neq 0 (
    echo.
    echo [ERRO] Falha ao iniciar. Execute setup_windows.bat primeiro.
    pause
)
