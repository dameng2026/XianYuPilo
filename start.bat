@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Fill every REQUIRED blank, then run start.bat again.
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify-production.ps1" %*
exit /b %errorlevel%
