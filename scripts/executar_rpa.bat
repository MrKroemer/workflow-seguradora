@echo off
chcp 65001 >nul 2>nul
title RPA Corretora - PBSeg

echo ============================================================
echo   RPA Corretora de Seguros - PBSeg
echo   Execucao automatica do ciclo diario
echo ============================================================
echo.

:: Raiz do projeto (pasta pai de scripts\)
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

set "PYTHONPATH=%ROOT_DIR%\src"

:: Detecta Python
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=py -3"
    ) else (
        set "PY=python"
    )
)

:: Verifica dependencias
%PY% -c "import openpyxl" >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Dependencias nao instaladas. Execute setup_windows.bat primeiro.
    pause
    exit /b 1
)

echo [1/3] Executando dry-run de validacao...
echo.
%PY% -m rpa_corretora.main --dry-run --no-dashboard-html >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Dry-run falhou. Verifique o .env e as planilhas.
    echo         Executando novamente com output para diagnostico:
    echo.
    %PY% -m rpa_corretora.main --dry-run
    echo.
    pause
    exit /b 1
)
echo [OK] Validacao concluida sem erros.
echo.

echo [2/3] Iniciando ciclo de producao...
echo.
%PY% -m rpa_corretora.main
set "EXIT_CODE=%ERRORLEVEL%"
echo.

if %EXIT_CODE%==0 (
    echo ============================================================
    echo   [SUCESSO] Ciclo diario finalizado.
    echo   Relatorio enviado para pbseg.seguros@gmail.com
    echo   Dashboard: outputs\dashboard_latest.html
    echo ============================================================
) else (
    echo ============================================================
    echo   [ATENCAO] Ciclo finalizado com erros.
    echo   Verifique o relatorio em outputs\
    echo ============================================================
)

echo.
echo [3/3] Pressione qualquer tecla para fechar...
pause >nul
exit /b %EXIT_CODE%
