@echo off
chcp 65001 >nul 2>nul
title Configuracao do Chrome para RPA PBSeg

echo ============================================================
echo   Configuracao do Chrome para RPA PBSeg
echo   Este script configura o Chrome para aceitar conexoes do robo.
echo ============================================================
echo.

:: Encontra o Chrome
set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else (
    echo [ERRO] Chrome nao encontrado.
    pause
    exit /b 1
)

echo [OK] Chrome encontrado: %CHROME_EXE%
echo.

:: Fecha Chrome se estiver aberto
echo [1/3] Fechando Chrome...
taskkill /IM chrome.exe >nul 2>nul
timeout /t 3 /nobreak >nul

:: Cria atalho na area de trabalho com debug port
echo [2/3] Criando atalho "Chrome PBSeg" na area de trabalho...
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Chrome PBSeg.lnk"
set "USER_DATA=%LOCALAPPDATA%\Google\Chrome\User Data"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $sc = $ws.CreateShortcut('%SHORTCUT%'); ^
     $sc.TargetPath = '%CHROME_EXE%'; ^
     $sc.Arguments = '--remote-debugging-port=9222 --profile-directory=\"Profile 1\" --restore-last-session'; ^
     $sc.WorkingDirectory = '%LOCALAPPDATA%\Google\Chrome\Application'; ^
     $sc.Description = 'Chrome com debug remoto para RPA PBSeg'; ^
     $sc.Save()"

if exist "%SHORTCUT%" (
    echo [OK] Atalho criado: %SHORTCUT%
) else (
    echo [AVISO] Falha ao criar atalho. Crie manualmente.
)

:: Inicia Chrome com debug port
echo [3/3] Iniciando Chrome com perfil PBSeg...
start "" "%CHROME_EXE%" --remote-debugging-port=9222 --profile-directory="Profile 1" --restore-last-session --no-first-run

echo.
echo ============================================================
echo   PRONTO! O Chrome foi configurado.
echo.
echo   IMPORTANTE: Sempre abra o Chrome pelo atalho "Chrome PBSeg"
echo   na area de trabalho (ou pela barra de tarefas apos fixar).
echo.
echo   O robo agora vai conectar automaticamente ao Chrome aberto.
echo ============================================================
echo.
pause
