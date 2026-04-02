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

echo [COLAB] Setup do Colaborador Virtual (baseado no projeto principal)...
set "ROOT_SETUP=%ROOT_DIR%\scripts\setup_windows.bat"
if not exist "%ROOT_SETUP%" (
  echo [COLAB] Script principal nao encontrado: "%ROOT_SETUP%"
  exit /b 1
)

call "%ROOT_SETUP%" %*
exit /b %ERRORLEVEL%
