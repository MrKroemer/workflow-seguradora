@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"
if not exist "%ROOT_DIR%" (
  echo [COLAB] Raiz do projeto nao encontrada: "%ROOT_DIR%"
  exit /b 1
)

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo [COLAB] Falha ao acessar a raiz do projeto: "%ROOT_DIR%"
  exit /b 1
)

set "ROOT_ENV=%ROOT_DIR%\.env"
set "COLAB_ENV=%ROOT_DIR%\colaborador_virtual_rpa\.env"

if not exist "%ROOT_ENV%" (
  echo [COLAB] Arquivo .env da raiz nao encontrado.
  echo [COLAB] Preencha a raiz primeiro ou crie colaborador_virtual_rpa\.env manualmente.
  exit /b 1
)

copy /Y "%ROOT_ENV%" "%COLAB_ENV%" >nul
if errorlevel 1 (
  echo [COLAB] Falha ao copiar .env para colaborador_virtual_rpa\.env
  exit /b 1
)

echo [COLAB] colaborador_virtual_rpa\.env sincronizado com a raiz.
exit /b 0
