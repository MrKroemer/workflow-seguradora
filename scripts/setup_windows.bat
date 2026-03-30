@echo off
setlocal EnableExtensions
cd /d %~dp0\..

call :resolve_python
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Criando ambiente virtual em .venv...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [SETUP] Falha ao criar .venv.
    exit /b 1
  )
)

set "PY_CMD=.venv\Scripts\python.exe"

echo [SETUP] Atualizando pip...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
  echo [SETUP] Falha ao atualizar pip.
  exit /b 1
)

echo [SETUP] Instalando dependencias do projeto...
%PY_CMD% -m pip install -e .
if errorlevel 1 (
  echo [SETUP] Falha ao instalar dependencias do projeto.
  exit /b 1
)

echo [SETUP] Instalando Playwright...
%PY_CMD% -m pip install playwright
if errorlevel 1 (
  echo [SETUP] Falha ao instalar Playwright.
  exit /b 1
)

echo [SETUP] Instalando browser Chromium do Playwright...
%PY_CMD% -m playwright install chromium
if errorlevel 1 (
  echo [SETUP] Falha ao instalar Chromium do Playwright.
  exit /b 1
)

echo [SETUP] Ambiente Windows pronto.
echo [SETUP] Proximo passo: scripts\run_rpa_windows.bat --dry-run
exit /b 0

:resolve_python
if exist ".venv\Scripts\python.exe" (
  set "PY_CMD=.venv\Scripts\python.exe"
  goto :eof
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PY_CMD=py -3"
  goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PY_CMD=python"
  goto :eof
)

echo [SETUP] Python nao encontrado.
echo [SETUP] Instale Python 3.11+ e tente novamente.
exit /b 1
