@echo off
chcp 65001 >nul 2>nul
title RPA PBSeg - Setup
echo Iniciando preparacao do ambiente...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar_ambiente.ps1"
