@echo off
chcp 65001 >nul 2>nul
title RPA PBSeg - Instalação / Atualização Completa

echo ============================================================
echo   RPA PBSeg - Instalação e Atualização Completa
echo   Corretora de Seguros PBSeg
echo ============================================================
echo.

:: Detecta diretorio do projeto
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

:: Detecta Python
set "PY="
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    echo [OK] Python encontrado: .venv\Scripts\python.exe
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=py -3"
        echo [OK] Python encontrado: py -3
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL%==0 (
            set "PY=python"
            echo [OK] Python encontrado: python
        ) else (
            echo [ERRO] Python nao encontrado. Instale em python.org
            pause
            exit /b 1
        )
    )
)

echo.
echo ============================================================
echo [1/6] Atualizando pip...
echo ============================================================
%PY% -m pip install --upgrade pip 2>nul
echo.

echo ============================================================
echo [2/6] Instalando dependencias do RPA...
echo ============================================================
%PY% -m pip install openpyxl flask playwright pywinauto pypdf 2>nul
if %ERRORLEVEL% neq 0 (
    echo [AVISO] Algumas dependencias podem ter falhado. Continuando...
)
echo.

echo ============================================================
echo [3/6] Instalando navegadores Playwright...
echo ============================================================
%PY% -m playwright install chromium 2>nul
if %ERRORLEVEL% neq 0 (
    echo [AVISO] Playwright chromium nao instalado. Portais podem nao funcionar.
)
echo.

echo ============================================================
echo [4/6] Verificando estrutura de pastas...
echo ============================================================
if not exist "outputs" mkdir outputs
if not exist "web" mkdir web
echo [OK] Pastas criadas/verificadas.
echo.

echo ============================================================
echo [5/6] Validando instalacao...
echo ============================================================
set "PYTHONPATH=%ROOT_DIR%\src"
%PY% -c "import openpyxl; print('  [OK] openpyxl')"
%PY% -c "import flask; print('  [OK] flask')"
%PY% -c "import playwright; print('  [OK] playwright')"
%PY% -c "from rpa_corretora.webapp import app; print('  [OK] webapp')"
%PY% -c "from rpa_corretora.processing.orchestrator import DailyProcessor; print('  [OK] orchestrator')"
%PY% -c "from rpa_corretora.core import OperationalDatabase; print('  [OK] database')"
echo.

echo ============================================================
echo [6/6] Configurando Chrome...
echo ============================================================
:: Verifica se Chrome existe
set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if defined CHROME_EXE (
    echo [OK] Chrome encontrado: %CHROME_EXE%
    :: Cria atalho na area de trabalho
    set "DESKTOP=%USERPROFILE%\Desktop"
    powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut('%DESKTOP%\Chrome PBSeg.lnk');$sc.TargetPath='%CHROME_EXE%';$sc.Arguments='--remote-debugging-port=9222 --profile-directory=\"Profile 1\" --restore-last-session';$sc.Description='Chrome para RPA PBSeg';$sc.Save()" 2>nul
    echo [OK] Atalho "Chrome PBSeg" criado na area de trabalho.
) else (
    echo [AVISO] Chrome nao encontrado. Instale o Google Chrome.
)
echo.

echo ============================================================
echo   INSTALAÇÃO CONCLUÍDA!
echo ============================================================
echo.
echo   Para usar o RPA PBSeg:
echo.
echo   1. Abra o Chrome pelo atalho "Chrome PBSeg" na area de trabalho
echo   2. Execute: scripts\abrir_painel.bat
echo.
echo   O painel web abrira automaticamente no navegador.
echo.
echo ============================================================
echo.
pause
