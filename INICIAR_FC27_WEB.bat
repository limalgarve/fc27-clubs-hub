@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title FC27 Clubs Hub WEB V5
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_FC27_WEB.ps1"
if %errorlevel% neq 0 (
  echo.
  echo Falha na inicializacao. Envie LOG_FC27_WEB.txt.
  pause
)
