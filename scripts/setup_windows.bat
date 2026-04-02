@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
if not exist "%ROOT_DIR%" (
  echo [SETUP] Raiz do projeto nao encontrada: "%ROOT_DIR%"
  exit /b 1
)

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo [SETUP] Falha ao acessar a raiz do projeto: "%ROOT_DIR%"
  exit /b 1
)

if not exist "%ROOT_DIR%\pyproject.toml" (
  echo [SETUP] pyproject.toml nao encontrado na raiz: "%ROOT_DIR%"
  echo [SETUP] Execute este script a partir de uma copia completa do repositorio.
  exit /b 1
)

set "SETUP_NO_VENV=0"
if /I "%~1"=="--no-venv" set "SETUP_NO_VENV=1"
if /I "%RPA_WINDOWS_NO_VENV%"=="1" set "SETUP_NO_VENV=1"
if "%SETUP_NO_VENV%"=="1" goto :setup_system

call :resolve_python
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Criando ambiente virtual em .venv...
  %PY_CMD% -m venv .venv --upgrade-deps
  if errorlevel 1 (
    %PY_CMD% -m venv .venv
  )
  if errorlevel 1 (
    echo [SETUP] Falha ao criar .venv.
    exit /b 1
  )
)

set "PY_CMD=.venv\Scripts\python.exe"
call :ensure_venv_pip
if errorlevel 1 exit /b 1

echo [SETUP] Atualizando pip...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
  echo [SETUP] Aviso: falha ao atualizar pip da .venv. Tentando manter/recuperar pip...
  call :ensure_venv_pip
  if errorlevel 1 (
    echo [SETUP] Falha ao preparar pip na .venv.
    exit /b 1
  )
  echo [SETUP] Continuando com pip disponivel na .venv.
)

echo [SETUP] Instalando dependencias do projeto...
%PY_CMD% -m pip install -e "%ROOT_DIR%"
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

echo [SETUP] Instalando pywinauto (Microsoft To Do app desktop)...
%PY_CMD% -m pip install pywinauto
if errorlevel 1 (
  echo [SETUP] Falha ao instalar pywinauto.
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

:setup_system
call :resolve_system_python
if errorlevel 1 exit /b 1

echo [SETUP] Modo sem venv ativo. Usando Python do sistema: %PY_CMD%
call :ensure_system_pip
if errorlevel 1 exit /b 1

echo [SETUP] Atualizando pip (sistema)...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
  echo [SETUP] Aviso: falha ao atualizar pip do sistema. Tentando manter/recuperar pip...
  call :ensure_system_pip
  if errorlevel 1 (
    echo [SETUP] Falha ao preparar pip no Python do sistema.
    exit /b 1
  )
  echo [SETUP] Continuando com pip disponivel no sistema.
)

echo [SETUP] Instalando dependencias do projeto (usuario atual)...
%PY_CMD% -m pip install --user -e "%ROOT_DIR%"
if errorlevel 1 (
  echo [SETUP] Falha ao instalar dependencias do projeto no sistema.
  exit /b 1
)

echo [SETUP] Instalando Playwright (usuario atual)...
%PY_CMD% -m pip install --user playwright
if errorlevel 1 (
  echo [SETUP] Falha ao instalar Playwright no sistema.
  exit /b 1
)

echo [SETUP] Instalando pywinauto (Microsoft To Do app desktop)...
%PY_CMD% -m pip install --user pywinauto
if errorlevel 1 (
  echo [SETUP] Falha ao instalar pywinauto no sistema.
  exit /b 1
)

echo [SETUP] Instalando browser Chromium do Playwright...
%PY_CMD% -m playwright install chromium
if errorlevel 1 (
  echo [SETUP] Falha ao instalar Chromium do Playwright.
  exit /b 1
)

echo [SETUP] Ambiente Windows pronto (sem venv).
echo [SETUP] Proximo passo: scripts\run_rpa_windows.bat --no-venv --dry-run
exit /b 0

:ensure_venv_pip
%PY_CMD% -m pip --version >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [SETUP] pip detectado na .venv.
  goto :eof
)

echo [SETUP] pip ausente na .venv. Tentando reparar com ensurepip...
%PY_CMD% -m ensurepip --upgrade >nul 2>nul

%PY_CMD% -m pip --version >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [SETUP] pip reparado com ensurepip.
  goto :eof
)

echo [SETUP] ensurepip nao resolveu. Recriando .venv...
if exist ".venv" rmdir /s /q ".venv"

call :resolve_python
if errorlevel 1 exit /b 1

%PY_CMD% -m venv .venv --upgrade-deps
if errorlevel 1 (
  %PY_CMD% -m venv .venv
)
if errorlevel 1 (
  echo [SETUP] Falha ao recriar .venv.
  exit /b 1
)

set "PY_CMD=.venv\Scripts\python.exe"
%PY_CMD% -m ensurepip --upgrade >nul 2>nul
%PY_CMD% -m pip --version >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [SETUP] pip disponivel apos recriacao da .venv.
  goto :eof
)

echo [SETUP] Nao foi possivel habilitar pip na .venv.
exit /b 1

:ensure_system_pip
%PY_CMD% -m pip --version >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [SETUP] pip detectado no Python do sistema.
  goto :eof
)

echo [SETUP] pip ausente no Python do sistema. Tentando ensurepip...
%PY_CMD% -m ensurepip --upgrade >nul 2>nul

%PY_CMD% -m pip --version >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [SETUP] pip habilitado no Python do sistema.
  goto :eof
)

echo [SETUP] Nao foi possivel habilitar pip no Python do sistema.
exit /b 1

:resolve_python
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

echo [SETUP] Python nao encontrado.
echo [SETUP] Instale Python 3.11+ e tente novamente.
exit /b 1
