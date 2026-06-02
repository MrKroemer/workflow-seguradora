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

set "COLAB_ENV=%ROOT_DIR%\colaborador_virtual_rpa\.env"
if not exist "%COLAB_ENV%" (
  echo [COLAB] Arquivo %COLAB_ENV% nao encontrado.
  echo [COLAB] Copie colaborador_virtual_rpa\.env.example para colaborador_virtual_rpa\.env.
  exit /b 1
)

set "ROOT_RUN=%ROOT_DIR%\scripts\run_rpa_windows.bat"
if not exist "%ROOT_RUN%" (
  echo [COLAB] Script principal nao encontrado: "%ROOT_RUN%"
  exit /b 1
)

echo [COLAB] Executando ciclo diario do Colaborador Virtual...
call "%ROOT_RUN%" --env-file "%COLAB_ENV%" --files-dir "%ROOT_DIR%\arquivos" --strict-production %*
exit /b %ERRORLEVEL%
