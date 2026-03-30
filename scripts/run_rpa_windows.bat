@echo off
setlocal EnableExtensions
cd /d %~dp0\..
set "PYTHONPATH=src"

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

echo [RPA] Python nao encontrado.
exit /b 1
