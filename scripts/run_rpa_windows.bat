@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
if not exist "%ROOT_DIR%" (
  echo [RPA] Raiz do projeto nao encontrada: "%ROOT_DIR%"
  exit /b 1
)

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo [RPA] Falha ao acessar a raiz do projeto: "%ROOT_DIR%"
  exit /b 1
)

if not exist "%ROOT_DIR%\pyproject.toml" (
  echo [RPA] pyproject.toml nao encontrado na raiz: "%ROOT_DIR%"
  exit /b 1
)

set "PYTHONPATH=%ROOT_DIR%\src"

set "FORCE_SYSTEM_PYTHON=0"
if /I "%~1"=="--no-venv" (
  set "FORCE_SYSTEM_PYTHON=1"
  shift
)
if /I "%RPA_WINDOWS_NO_VENV%"=="1" set "FORCE_SYSTEM_PYTHON=1"

call :resolve_python
if errorlevel 1 exit /b 1

if "%MICROSOFT_TODO_WEB_HEADLESS%"=="" set "MICROSOFT_TODO_WEB_HEADLESS=0"

%PY_CMD% -c "import openpyxl, pypdf" >nul 2>nul
if errorlevel 1 (
  echo [RPA] Dependencias ausentes. Execute scripts\setup_windows.bat primeiro.
  exit /b 1
)

%PY_CMD% -m rpa_corretora.main %*
exit /b %ERRORLEVEL%

:resolve_python
if /I "%FORCE_SYSTEM_PYTHON%"=="1" goto :resolve_system_python

if exist ".venv\Scripts\python.exe" (
  set "PY_CMD=.venv\Scripts\python.exe"
  goto :eof
)

:resolve_system_python
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

echo [RPA] Python nao encontrado.
exit /b 1
