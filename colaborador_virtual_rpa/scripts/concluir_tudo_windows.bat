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
set "COLAB_EXAMPLE=%ROOT_DIR%\colaborador_virtual_rpa\.env.example"
set "ROOT_ENV=%ROOT_DIR%\.env"
set "COLAB_SYNC=%ROOT_DIR%\colaborador_virtual_rpa\scripts\sincronizar_env_da_raiz.bat"
set "COLAB_SETUP=%ROOT_DIR%\colaborador_virtual_rpa\scripts\setup_windows.bat"
set "COLAB_RUN=%ROOT_DIR%\colaborador_virtual_rpa\scripts\run_colaborador_windows.bat"

if not exist "%COLAB_ENV%" (
  if exist "%ROOT_ENV%" (
    echo [COLAB] .env especifico nao encontrado. Sincronizando com .env da raiz...
    if not exist "%COLAB_SYNC%" (
      echo [COLAB] Script de sincronizacao nao encontrado: "%COLAB_SYNC%"
      exit /b 1
    )
    call "%COLAB_SYNC%"
    if errorlevel 1 exit /b 1
  ) else (
    echo [COLAB] Nenhum .env encontrado. Criando a partir do exemplo...
    copy /Y "%COLAB_EXAMPLE%" "%COLAB_ENV%" >nul
    if errorlevel 1 (
      echo [COLAB] Falha ao criar %COLAB_ENV%.
      exit /b 1
    )
    echo [COLAB] Preencha %COLAB_ENV% e rode novamente.
    exit /b 1
  )
)

echo [COLAB] 1/4 Setup do ambiente Windows (venv)...
if not exist "%COLAB_SETUP%" (
  echo [COLAB] Script de setup nao encontrado: "%COLAB_SETUP%"
  exit /b 1
)
call "%COLAB_SETUP%"
if errorlevel 1 (
  echo [COLAB] Falha no setup.
  exit /b 1
)

echo [COLAB] 2/4 Auditoria de ambiente...
if not exist "%COLAB_RUN%" (
  echo [COLAB] Script de execucao nao encontrado: "%COLAB_RUN%"
  exit /b 1
)
call "%COLAB_RUN%" --windows-audit-only
if errorlevel 1 (
  echo [COLAB] Falha na auditoria.
  exit /b 1
)

echo [COLAB] 3/4 Dry-run de seguranca...
call "%COLAB_RUN%" --dry-run
if errorlevel 1 (
  echo [COLAB] Falha no dry-run.
  exit /b 1
)

echo [COLAB] 4/4 Execucao real do ciclo diario...
call "%COLAB_RUN%"
if errorlevel 1 (
  echo [COLAB] Falha na execucao real.
  exit /b 1
)

echo [COLAB] Conclusao com sucesso.
echo [COLAB] Evidencias:
echo [COLAB] - outputs\dashboard_latest.html
echo [COLAB] - outputs\relatorio_execucao_YYYYMMDD_HHMMSS.json
echo [COLAB] - outputs\relatorio_execucao_YYYYMMDD_HHMMSS.pdf
exit /b 0
