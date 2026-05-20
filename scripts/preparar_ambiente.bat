@echo off
chcp 65001 >nul 2>nul
setlocal EnableDelayedExpansion
title RPA PBSeg - Preparacao Completa do Ambiente

:: ============================================================
::  RPA PBSeg — Preparacao Completa do Ambiente Windows
::  Execute UMA vez numa maquina nova ou apos atualizar o projeto.
:: ============================================================

for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

set "LOG_FILE=%ROOT_DIR%\outputs\setup_log.txt"
set "ENV_FILE=%ROOT_DIR%\.env"
set "ENV_EXAMPLE=%ROOT_DIR%\.env.example"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "OUTPUTS_DIR=%ROOT_DIR%\outputs"
set "ARQUIVOS_DIR=%ROOT_DIR%\arquivos"

:: Cria outputs antes de qualquer coisa (log precisa da pasta)
if not exist "%OUTPUTS_DIR%" mkdir "%OUTPUTS_DIR%"

echo.
echo ============================================================
echo   RPA PBSeg - Preparacao Completa do Ambiente
echo   %date% %time%
echo ============================================================
echo.
echo   Raiz do projeto : %ROOT_DIR%
echo   Log de setup    : %LOG_FILE%
echo.

call :LOG "=== INICIO DO SETUP === %date% %time%"

:: ────────────────────────────────────────────────────────────
:: PASSO 1: Verificar / instalar Python 3.11+
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 1/9 — Python 3.11+"

set "PY="
set "PY_VER="

:: Tenta py launcher primeiro (Windows oficial)
where py >nul 2>nul
if !ERRORLEVEL! equ 0 (
    for /f "tokens=*" %%V in ('py -3 --version 2^>^&1') do set "PY_VER=%%V"
    set "PY=py -3"
    call :OK "Python encontrado: !PY_VER! (py launcher)"
    goto :check_py_version
)

:: Tenta python direto
where python >nul 2>nul
if !ERRORLEVEL! equ 0 (
    for /f "tokens=*" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
    set "PY=python"
    call :OK "Python encontrado: !PY_VER!"
    goto :check_py_version
)

:: Tenta python3
where python3 >nul 2>nul
if !ERRORLEVEL! equ 0 (
    for /f "tokens=*" %%V in ('python3 --version 2^>^&1') do set "PY_VER=%%V"
    set "PY=python3"
    call :OK "Python encontrado: !PY_VER!"
    goto :check_py_version
)

:: Python nao encontrado — tenta instalar via winget
call :AVISO "Python nao encontrado. Tentando instalar via winget..."
where winget >nul 2>nul
if !ERRORLEVEL! equ 0 (
    echo     Instalando Python 3.12 via winget...
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! equ 0 (
        call :OK "Python instalado com sucesso."
        set "PY=py -3"
    ) else (
        call :ERRO "Falha ao instalar Python automaticamente."
        call :ERRO "Acesse https://python.org/downloads e instale Python 3.11 ou superior."
        call :ERRO "Marque 'Add Python to PATH' durante a instalacao."
        pause
        exit /b 1
    )
) else (
    call :ERRO "winget nao disponivel. Instale Python 3.11+ manualmente:"
    call :ERRO "  https://python.org/downloads"
    call :ERRO "  Marque: Add Python to PATH"
    pause
    exit /b 1
)

:check_py_version
:: Verifica versao minima 3.11
for /f "tokens=2 delims= " %%V in ("!PY_VER!") do (
    for /f "tokens=1,2 delims=." %%M in ("%%V") do (
        if %%M LSS 3 (
            call :ERRO "Python %%M.%%N encontrado. Necessario 3.11 ou superior."
            pause
            exit /b 1
        )
        if %%M EQU 3 if %%N LSS 11 (
            call :ERRO "Python %%M.%%N encontrado. Necessario 3.11 ou superior."
            pause
            exit /b 1
        )
    )
)
call :LOG "Python OK: !PY_VER!"

:: ────────────────────────────────────────────────────────────
:: PASSO 2: Criar ambiente virtual .venv
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 2/9 — Ambiente virtual (.venv)"

if exist "%VENV_DIR%\Scripts\python.exe" (
    call :OK ".venv ja existe — pulando criacao."
) else (
    echo     Criando ambiente virtual em .venv ...
    %PY% -m venv "%VENV_DIR%"
    if !ERRORLEVEL! neq 0 (
        call :ERRO "Falha ao criar .venv"
        pause
        exit /b 1
    )
    call :OK ".venv criado."
)

:: Usa o Python do venv a partir daqui
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
call :LOG ".venv Python: %VENV_PY%"

:: Atualiza pip dentro do venv
echo     Atualizando pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet
call :OK "pip atualizado."

:: ────────────────────────────────────────────────────────────
:: PASSO 3: Instalar dependencias Python
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 3/9 — Dependencias Python"

echo     Instalando pacotes principais...
"%VENV_PY%" -m pip install --quiet ^
    openpyxl ^
    flask ^
    playwright ^
    pywinauto ^
    pypdf

if !ERRORLEVEL! neq 0 (
    call :ERRO "Falha ao instalar dependencias."
    call :ERRO "Verifique sua conexao com a internet e tente novamente."
    pause
    exit /b 1
)
call :OK "Pacotes instalados: openpyxl, flask, playwright, pywinauto, pypdf"

:: Verifica cada pacote
for %%P in (openpyxl flask playwright pypdf) do (
    "%VENV_PY%" -c "import %%P" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        call :OK "  [OK] %%P"
    ) else (
        call :AVISO "  [?] %%P nao importou corretamente"
    )
)
call :LOG "Dependencias instaladas."

:: ────────────────────────────────────────────────────────────
:: PASSO 4: Instalar navegador Playwright (Chromium)
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 4/9 — Navegador Playwright (Chromium)"

:: Verifica se Chromium ja esta instalado
"%VENV_PY%" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium; p.stop()" >nul 2>nul
if !ERRORLEVEL! equ 0 (
    call :OK "Chromium Playwright ja instalado — pulando."
    goto :passo5
)

echo     Instalando Chromium para Playwright (pode levar alguns minutos)...
"%VENV_PY%" -m playwright install chromium
if !ERRORLEVEL! neq 0 (
    call :AVISO "Falha ao instalar Chromium do Playwright."
    call :AVISO "O RPA pode funcionar sem ele se o Chrome nativo estiver disponivel."
    call :AVISO "Execute manualmente: .venv\Scripts\python.exe -m playwright install chromium"
) else (
    call :OK "Chromium instalado."
)
call :LOG "Playwright Chromium verificado."

:passo5
:: ────────────────────────────────────────────────────────────
:: PASSO 5: Criar e validar .env
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 5/9 — Arquivo de configuracao (.env)"

if not exist "%ENV_FILE%" (
    if exist "%ENV_EXAMPLE%" (
        copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
        call :OK ".env criado a partir de .env.example"
        call :AVISO "ATENCAO: Abra o arquivo .env e preencha suas credenciais antes de executar."
        call :AVISO "  - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN"
        call :AVISO "  - GMAIL_IMAP_USER / GMAIL_IMAP_PASSWORD"
        call :AVISO "  - MICROSOFT_TODO_CLIENT_ID / MICROSOFT_TODO_CLIENT_SECRET"
        call :AVISO "  - SEGFY_USER / SEGFY_PASSWORD"
        echo.
        set /p ABRIR_ENV="Deseja abrir o .env para editar agora? (S/N): "
        if /i "!ABRIR_ENV!"=="S" (
            start notepad "%ENV_FILE%"
            echo     Aguarde: edite o .env e salve. Pressione qualquer tecla para continuar.
            pause >nul
        )
    ) else (
        call :AVISO ".env.example nao encontrado. Criando .env minimo..."
        (
            echo # RPA PBSeg - Configuracoes minimas
            echo RPA_STRICT_PRODUCTION=0
            echo MICROSOFT_TODO_REQUIRE_DESKTOP=0
            echo SEGFY_WEB_ENABLED=1
            echo MICROSOFT_TODO_DESKTOP_ENABLED=1
        ) > "%ENV_FILE%"
        call :AVISO "Preencha %ENV_FILE% com suas credenciais."
    )
) else (
    call :OK ".env ja existe."
)

:: Verifica variaveis criticas
call :VERIFICAR_ENV "GOOGLE_CLIENT_ID" "Google Calendar"
call :VERIFICAR_ENV "GMAIL_IMAP_USER" "Gmail IMAP"
call :VERIFICAR_ENV "MICROSOFT_TODO_CLIENT_ID" "Microsoft To Do"
call :VERIFICAR_ENV "SEGFY_USER" "Segfy"
call :LOG ".env verificado."

:: ────────────────────────────────────────────────────────────
:: PASSO 6: Criar estrutura de pastas
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 6/9 — Estrutura de pastas"

for %%D in (
    "%OUTPUTS_DIR%"
    "%ARQUIVOS_DIR%"
    "%ROOT_DIR%\web"
    "%ROOT_DIR%\config"
) do (
    if not exist %%D (
        mkdir %%D
        call :OK "Criada: %%~D"
    ) else (
        call :OK "Existe: %%~D"
    )
)

:: Copia planilhas de exemplo se nao existirem no destino
for %%F in (
    "SEGUROS PBSEG.xlsx"
    "ACOMPANHAMENTO 2026.xlsx"
    "FLUXO DE CAIXA.xlsx"
) do (
    if not exist "%ARQUIVOS_DIR%\%%~F" (
        call :AVISO "Planilha ausente: arquivos\%%~F"
        call :AVISO "  -> Coloque o arquivo em: %ARQUIVOS_DIR%\%%~F"
    ) else (
        call :OK "Planilha presente: %%~F"
    )
)
call :LOG "Pastas criadas."

:: ────────────────────────────────────────────────────────────
:: PASSO 7: Inicializar banco de dados SQLite
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 7/9 — Banco de dados operacional (SQLite)"

set "PYTHONPATH=%ROOT_DIR%\src"
set "PYTHONUNBUFFERED=1"

"%VENV_PY%" -c "
import sys, os
sys.path.insert(0, r'%ROOT_DIR%\src')
os.environ.setdefault('PYTHONPATH', r'%ROOT_DIR%\src')
try:
    from rpa_corretora.core import OperationalDatabase
    db = OperationalDatabase(r'%OUTPUTS_DIR%\rpa_corretora.db')
    count = db.conn.execute('SELECT COUNT(*) FROM policies').fetchone()[0]
    print(f'[OK] Banco inicializado. Apolices: {count}')
    db.close()
except Exception as e:
    print(f'[AVISO] {e}')
" 2>&1

if !ERRORLEVEL! equ 0 (
    call :OK "Banco de dados OK."
) else (
    call :AVISO "Banco sera criado automaticamente na primeira execucao."
)
call :LOG "SQLite verificado."

:: ────────────────────────────────────────────────────────────
:: PASSO 8: Configurar Chrome para RPA (atalho CDP)
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 8/9 — Chrome com CDP (Segfy)"

set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else (
    :: Tenta localizar via registro
    for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do set "CHROME_EXE=%%B"
)

if defined CHROME_EXE (
    call :OK "Chrome encontrado: !CHROME_EXE!"

    :: Cria atalho "Chrome PBSeg" na area de trabalho
    set "DESKTOP=%USERPROFILE%\Desktop"
    set "SHORTCUT=!DESKTOP!\Chrome PBSeg.lnk"
    set "USER_DATA_DIR=%LOCALAPPDATA%\Google\Chrome\User Data"

    powershell -NoProfile -Command ^
        "$ws = New-Object -ComObject WScript.Shell; ^
         $sc = $ws.CreateShortcut('!SHORTCUT!'); ^
         $sc.TargetPath = '!CHROME_EXE!'; ^
         $sc.Arguments = '--remote-debugging-port=9222 --profile-directory=\"Profile 1\" --restore-last-session'; ^
         $sc.WorkingDirectory = '%LOCALAPPDATA%\Google\Chrome\Application'; ^
         $sc.Description = 'Chrome com debug remoto para RPA PBSeg'; ^
         $sc.IconLocation = '!CHROME_EXE!,0'; ^
         $sc.Save()" >nul 2>nul

    if exist "!SHORTCUT!" (
        call :OK "Atalho 'Chrome PBSeg' criado na area de trabalho."
        call :AVISO "LEMBRE-SE: Abra sempre o Segfy pelo atalho 'Chrome PBSeg'."
    ) else (
        call :AVISO "Nao foi possivel criar o atalho automaticamente."
        call :AVISO "Execute scripts\configurar_chrome.bat para criar manualmente."
    )
) else (
    call :AVISO "Google Chrome nao encontrado. Instale o Chrome para usar o Segfy com CDP."
    call :AVISO "  https://google.com/chrome"
)
call :LOG "Chrome configurado."

:: ────────────────────────────────────────────────────────────
:: PASSO 9: Criar atalhos na area de trabalho
:: ────────────────────────────────────────────────────────────
call :CABECALHO "PASSO 9/9 — Atalhos na area de trabalho"

set "DESKTOP=%USERPROFILE%\Desktop"
set "ICON_PY=%VENV_DIR%\Scripts\python.exe"

:: Atalho: Painel Web (principal)
call :CRIAR_ATALHO ^
    "!DESKTOP!\RPA PBSeg - Painel.lnk" ^
    "%ROOT_DIR%\scripts\abrir_painel.bat" ^
    "Abre o painel web do RPA PBSeg em http://localhost:5000" ^
    "%ROOT_DIR%\scripts"

:: Atalho: Executar RPA (ciclo completo)
call :CRIAR_ATALHO ^
    "!DESKTOP!\RPA PBSeg - Executar.lnk" ^
    "%ROOT_DIR%\scripts\executar_rpa.bat" ^
    "Executa o ciclo diario completo do RPA PBSeg" ^
    "%ROOT_DIR%\scripts"

:: Atalho: Configurar Chrome
call :CRIAR_ATALHO ^
    "!DESKTOP!\RPA PBSeg - Configurar Chrome.lnk" ^
    "%ROOT_DIR%\scripts\configurar_chrome.bat" ^
    "Configura o Chrome para conexao CDP com o Segfy" ^
    "%ROOT_DIR%\scripts"

call :LOG "Atalhos criados."

:: ────────────────────────────────────────────────────────────
:: VALIDACAO FINAL: dry-run rapido
:: ────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   VALIDACAO FINAL — dry-run sem output externo
echo ============================================================
echo.

set "PYTHONPATH=%ROOT_DIR%\src"
set "PYTHONUNBUFFERED=1"

:: Valida apenas importacao dos modulos principais
"%VENV_PY%" -c "
import sys
sys.path.insert(0, r'%ROOT_DIR%\src')
erros = []
modulos = [
    ('openpyxl',              'openpyxl'),
    ('flask',                 'flask'),
    ('playwright',            'playwright'),
    ('rpa_corretora.config',  'configuracao'),
    ('rpa_corretora.core',    'banco de dados'),
    ('rpa_corretora.webapp',  'servidor web'),
    ('rpa_corretora.main',    'modulo principal'),
]
for mod, nome in modulos:
    try:
        __import__(mod)
        print(f'  [OK] {nome}')
    except Exception as e:
        erros.append(f'  [ERRO] {nome}: {e}')
        print(erros[-1])
if erros:
    print(f'\n{len(erros)} modulo(s) com problema.')
    sys.exit(1)
else:
    print(f'\nTodos os modulos carregaram corretamente.')
    sys.exit(0)
"

if !ERRORLEVEL! equ 0 (
    call :OK "Validacao de modulos concluida."
    call :LOG "Validacao final: OK"
) else (
    call :AVISO "Alguns modulos apresentaram problemas (ver acima)."
    call :AVISO "O RPA pode funcionar mesmo assim — verifique o erro antes de prosseguir."
    call :LOG "Validacao final: AVISO"
)

:: ────────────────────────────────────────────────────────────
:: RELATORIO FINAL
:: ────────────────────────────────────────────────────────────
echo.
echo.
echo ============================================================
echo   SETUP CONCLUIDO — %date% %time%
echo ============================================================
echo.
echo   O que foi configurado:
echo     [OK] Python + ambiente virtual (.venv)
echo     [OK] Dependencias: openpyxl, flask, playwright, pywinauto
echo     [OK] Chromium para automacao web
echo     [OK] Arquivo .env
echo     [OK] Pastas do projeto (outputs, arquivos, web)
echo     [OK] Banco de dados SQLite
echo     [OK] Atalho Chrome PBSeg (CDP porta 9222)
echo     [OK] Atalhos na area de trabalho
echo.
echo   PROXIMOS PASSOS:
echo.
echo   1. Preencha o .env com suas credenciais (se ainda nao fez):
echo         %ENV_FILE%
echo.
echo   2. Coloque as planilhas na pasta arquivos\:
echo         - SEGUROS PBSEG.xlsx
echo         - ACOMPANHAMENTO 2026.xlsx
echo         - FLUXO DE CAIXA.xlsx
echo         - SENHAS.pdf  (opcional)
echo.
echo   3. Para usar o Segfy com o robo:
echo         Abra o Chrome pelo atalho "Chrome PBSeg" na area de trabalho
echo         Faca login no Segfy normalmente
echo         Depois execute o RPA
echo.
echo   4. Inicie o painel web:
echo         Clique no atalho "RPA PBSeg - Painel" na area de trabalho
echo         Ou: scripts\abrir_painel.bat
echo         Acesse: http://localhost:5000
echo.
echo   5. (Opcional) Instalar Ollama para IA local do agente:
echo         scripts\setup_ollama.bat
echo.
echo   Log completo: %LOG_FILE%
echo ============================================================
echo.
call :LOG "=== SETUP CONCLUIDO ==="

pause
exit /b 0


:: ============================================================
::  FUNCOES AUXILIARES
:: ============================================================

:CABECALHO
echo.
echo   ── %~1
goto :EOF

:OK
echo     [OK] %~1
call :LOG "[OK] %~1"
goto :EOF

:AVISO
echo     [!!] %~1
call :LOG "[AVISO] %~1"
goto :EOF

:ERRO
echo     [XX] %~1
call :LOG "[ERRO] %~1"
goto :EOF

:LOG
echo %~1 >> "%LOG_FILE%" 2>nul
goto :EOF

:VERIFICAR_ENV
:: Parametros: %1 = nome var, %2 = descricao
set "_VAR_NAME=%~1"
set "_VAR_DESC=%~2"
set "_VAR_VAL="

:: Le o valor do .env
for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if "%%A"=="!_VAR_NAME!" set "_VAR_VAL=%%B"
)

if defined _VAR_VAL (
    if "!_VAR_VAL!" neq "" (
        call :OK "  %_VAR_DESC% configurado"
        goto :EOF
    )
)
call :AVISO "  %_VAR_DESC% nao configurado — edite .env: %_VAR_NAME%="
goto :EOF

:CRIAR_ATALHO
:: Parametros: %1=caminho_lnk, %2=target, %3=descricao, %4=working_dir
set "_LNK=%~1"
set "_TGT=%~2"
set "_DESC=%~3"
set "_WRK=%~4"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $sc = $ws.CreateShortcut('!_LNK!'); ^
     $sc.TargetPath = '!_TGT!'; ^
     $sc.WorkingDirectory = '!_WRK!'; ^
     $sc.Description = '!_DESC!'; ^
     $sc.Save()" >nul 2>nul

if exist "!_LNK!" (
    call :OK "Atalho: %~n1"
) else (
    call :AVISO "Nao criou atalho: %~n1"
)
goto :EOF
