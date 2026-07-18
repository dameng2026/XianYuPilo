@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

REM First-time setup: if .env or .\secrets missing, run the wizard
if not exist ".env" (
  echo 检测到首次使用，启动设置向导...
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-wizard.ps1
  exit /b %errorlevel%
)
if not exist ".\secrets" (
  echo 检测到首次使用，启动设置向导...
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-wizard.ps1
  exit /b %errorlevel%
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify-production.ps1" %*
exit /b %errorlevel%
