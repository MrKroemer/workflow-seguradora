@echo off
chcp 65001 >nul 2>nul
title Setup Ollama + Llama 3.1 para RPA PBSeg

echo ============================================================
echo   Instalacao do Ollama + Llama 3.1
echo   Modelo open source para o agente cognitivo PBSeg
echo ============================================================
echo.

:: Verifica se Ollama ja esta instalado
where ollama >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [OK] Ollama ja esta instalado.
    goto :pull_model
)

:: Baixa e instala Ollama
echo [1/3] Baixando Ollama...
echo       Acesse: https://ollama.com/download/windows
echo       Instale e volte aqui.
echo.
start https://ollama.com/download/windows
echo Aguardando instalacao do Ollama...
echo Pressione qualquer tecla apos instalar.
pause >nul

:pull_model
echo.
echo [2/3] Baixando modelo Llama 3.1 (4.7GB)...
echo       Isso pode levar alguns minutos na primeira vez.
echo.
ollama pull llama3.1

echo.
echo [3/3] Iniciando Ollama em background...
start /B ollama serve

echo.
echo ============================================================
echo   PRONTO! Ollama + Llama 3.1 instalados.
echo.
echo   O agente cognitivo PBSeg agora tem IA local.
echo   Abra com: scripts\abrir_agente.bat
echo ============================================================
echo.
pause
