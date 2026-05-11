@echo off
chcp 65001 >nul 2>nul
title RPA PBSeg - Painel Web
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"
set "PYTHONPATH=%ROOT_DIR%\src"

echo ============================================================
echo   RPA PBSeg - Painel Web
echo   Abrindo em http://localhost:5000
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m rpa_corretora.webapp
) else (
    py -3 -m rpa_corretora.webapp
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRO] Falha ao iniciar. Verifique se Flask esta instalado:
    echo   pip install flask
    echo.
    pause
)
