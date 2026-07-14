@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if not exist .env (
    echo .env not found, creating it from .env.development.example...
    copy .env.development.example .env >nul
    echo Local .env created. Configure ADMIN_PASSWORD_HASH and local database credentials, then run this script again.
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found in PATH.
    exit /b 1
)

rem Keep the open-source development stack isolated from other local products.
set "XYA_WEB_PORT=15176"
set "XYA_WEB_HOST=127.0.0.1"
set "SERVER_HOST=127.0.0.1"
set "SERVER_PORT=15177"
set "CRAWLER_PORT=15178"
set "PORT=%CRAWLER_PORT%"
set "HOST=127.0.0.1"
set "CRAWLER_BASE_URL=http://127.0.0.1:%CRAWLER_PORT%"
set "CRAWLER_SERVICE_URL=http://127.0.0.1:%CRAWLER_PORT%"
set "VITE_API_PROXY_TARGET=http://127.0.0.1:%SERVER_PORT%"
set "VITE_UPLOAD_PROXY_TARGET=http://127.0.0.1:%SERVER_PORT%"
set "CORS_ALLOWED_ORIGINS=http://127.0.0.1:%XYA_WEB_PORT%,http://localhost:%XYA_WEB_PORT%"
set "CRAWLER_ALLOWED_ORIGINS=http://127.0.0.1:%XYA_WEB_PORT%,http://localhost:%XYA_WEB_PORT%"

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\local-dev.ps1 preflight
if errorlevel 1 (
    echo One or more isolated local ports are already in use. Nothing was started.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\local-dev.ps1 start
set "START_EXIT=%ERRORLEVEL%"
if not "%START_EXIT%"=="0" (
    echo Local stack startup failed. See output\local-dev for service logs.
    exit /b %START_EXIT%
)

echo Local stack is ready. Use status-local.bat or stop-local.bat to manage it.
exit /b 0
