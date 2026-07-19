@echo off
REM 一键启动脚本（Windows）：自动初始化 secrets、拉取镜像、启动服务、等待健康
REM 用法：
REM   .\start.bat              拉取预构建镜像并启动（推荐）
REM   .\start.bat --build      本地源码构建并启动
REM   .\start.bat --no-pull    跳过镜像拉取（用本地已有的镜像）
REM
REM 错误兜底策略：
REM   - secrets 生成失败 → setup-wizard.ps1 内部多层兜底
REM   - bcrypt hash 生成失败 → 镜像构建后用 api 容器兜底生成
REM   - 镜像拉取失败 → 自动回退到本地源码构建
REM   - 容器启动失败 → 显示异常服务名和排查步骤
REM   - 健康检查超时 → 显示日志查看命令
setlocal enabledelayedexpansion

set DO_BUILD=0
set DO_PULL=1
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--build" (set DO_BUILD=1 & set DO_PULL=0 & shift & goto parse_args)
if /i "%~1"=="--no-pull" (set DO_PULL=0 & shift & goto parse_args)
echo 未知参数：%~1（支持：--build 本地构建 / --no-pull 跳过拉取） 1>&2
exit /b 1
:args_done

cd /d "%~dp0"

REM ---------- 1. 前置依赖检查 ----------
where docker >nul 2>&1
if errorlevel 1 (
  echo [X] 未检测到 Docker，请先安装 Docker Desktop：https://docs.docker.com/desktop/install/windows-install/ 1>&2
  exit /b 1
)
docker compose version >nul 2>&1
if errorlevel 1 (
  echo [X] 未检测到 Docker Compose v2，请升级 Docker Desktop 1>&2
  exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo [X] Docker 引擎未运行，请先启动 Docker Desktop 并等待右下角图标变绿 1>&2
  exit /b 1
)

REM ---------- 2. 首次启动初始化 ----------
set NEED_INIT=0
if not exist ".env" set NEED_INIT=1
if not exist "secrets" set NEED_INIT=1
if exist "secrets" (
  dir /b "secrets" 2>nul | findstr "." >nul
  if errorlevel 1 set NEED_INIT=1
)
for %%f in (admin-password-hash mysql-root-password mysql-app-password mysql-migration-password redis-password jwt-secret cookie-crypto-secret internal-api-token) do (
  if not exist "secrets\%%f" set NEED_INIT=1
)

if "%NEED_INIT%"=="1" (
  echo [*] 首次启动，运行初始化向导...
  powershell -ExecutionPolicy Bypass -File "scripts\setup-wizard.ps1"
  if errorlevel 1 (
    echo [X] 初始化向导执行失败 1>&2
    exit /b 1
  )
)

REM ---------- 3. 读取 .env 中的 WEB_PORT ----------
set WEB_PORT=8080
set WEB_BIND=0.0.0.0
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "key=%%a"
    set "value=%%b"
    if /i "!key!"=="WEB_PORT" set "WEB_PORT=!value!"
    if /i "!key!"=="WEB_BIND_ADDRESS" set "WEB_BIND=!value!"
  )
)

REM ---------- 3.5 端口占用检查 ----------
netstat -ano | findstr ":!WEB_PORT! " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [!] 端口 !WEB_PORT! 已被占用！
  echo     解决方法：修改 .env 中的 WEB_PORT=其他端口（如 8081），然后重新运行 .\start.bat
  echo     或检查占用进程：netstat -ano | findstr :!WEB_PORT!
  exit /b 1
)

REM ---------- 4. 拉取镜像或本地构建 ----------
set BUILD_OK=0
if "%DO_BUILD%"=="1" (
  echo [*] 本地源码构建镜像（首次约 5-10 分钟）...
  docker compose build
  if errorlevel 1 (
    echo [X] 镜像构建失败。查看上方错误信息，或检查网络和磁盘空间 1>&2
    exit /b 1
  )
  set BUILD_OK=1
) else (
  if "%DO_PULL%"=="1" (
    echo [*] 拉取最新镜像（首次约 3-5 分钟）...
    docker compose pull
    if errorlevel 1 (
      echo [!] 镜像拉取失败（可能是 GHCR 镜像未发布或命名空间不匹配）
      echo     自动回退到本地源码构建（首次约 5-10 分钟）...
      set DO_BUILD=1
    ) else (
      set BUILD_OK=1
    )
  )
  if "!BUILD_OK!"=="0" (
    docker compose build
    if errorlevel 1 (
      echo [X] 镜像构建失败。查看上方错误信息，或检查网络和磁盘空间 1>&2
      exit /b 1
    )
    set BUILD_OK=1
  )
)

REM ---------- 4.5 兜底生成 admin bcrypt hash（用 api 镜像） ----------
if exist "secrets\admin-password-hash" (
  for %%A in ("secrets\admin-password-hash") do if %%~zA EQU 0 (
    echo [*] 用 api 镜像兜底生成 admin bcrypt hash...
    set ADMIN_PASSWORD=admin123
    for /f "delims=" %%h in ('docker run --rm -e ADMIN_PASSWORD=admin123 xianyu-assistant-api python -c "import os, bcrypt; pw=os.environ[\"ADMIN_PASSWORD\"].encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())" 2^>nul') do set HASH_VALUE=%%h
    if "!HASH_VALUE!"=="" (
      echo [X] admin bcrypt hash 生成失败 1>&2
      echo     手动生成方法： 1>&2
      echo       1^) 安装 bcrypt: pip install bcrypt 1>&2
      echo       2^) 生成 hash: python -c "import bcrypt; print(bcrypt.hashpw(b'admin123', bcrypt.gensalt(rounds=12)).decode())" ^> secrets\admin-password-hash 1>&2
      echo       3^) 重新运行: .\start.bat --no-pull 1>&2
      exit /b 1
    )
    echo !HASH_VALUE!> "secrets\admin-password-hash"
    echo [OK] admin bcrypt hash 兜底生成成功
  )
)

REM ---------- 5. 启动服务 ----------
echo [*] 启动服务...
docker compose up -d
if errorlevel 1 (
  echo [X] 服务启动失败 1>&2
  echo     查看日志：docker compose logs 1>&2
  exit /b 1
)

REM ---------- 6. 等待 Web 健康检查 ----------
echo [*] 等待服务就绪（最长 3 分钟）...
set /a ATTEMPT=0
:wait_loop
set /a ATTEMPT+=1
if !ATTEMPT! GTR 90 (
  echo.
  echo [!] 服务启动超时（3 分钟内未通过健康检查）
  echo     排查步骤：
  echo       1^) 查看所有服务状态：docker compose ps
  echo       2^) 查看日志：docker compose logs --tail 200
  echo       3^) 如 MySQL 初始化慢，可等待后重试：docker compose up -d
  echo       4^) 完全重置：docker compose down -v ^&^& rmdir /s /q secrets ^&^& del .env ^&^& .\start.bat
  exit /b 1
)

REM 检查异常容器
for /f "delims=" %%i in ('docker compose ps --format "{{.Service}}:{{.Status}}" 2^>nul ^| findstr /i "exited failed unhealthy"') do (
  echo %%i | findstr /b "migrate:" >nul
  if errorlevel 1 (
    echo.
    echo [!] 以下服务异常：
    echo     %%i
    echo.
    echo [*] 排查步骤：
    echo       1^) 查看异常服务日志：docker compose logs --tail 100 ^<服务名^>
    echo       2^) 常见原因：端口冲突、内存不足、secrets 文件权限、数据库初始化失败
    echo       3^) 完全重置：docker compose down -v ^&^& rmdir /s /q secrets ^&^& del .env ^&^& .\start.bat
    exit /b 1
  )
)

REM curl 检查健康
where curl >nul 2>&1
if not errorlevel 1 (
  curl -fsS --max-time 3 "http://127.0.0.1:!WEB_PORT!/readyz" >nul 2>&1
  if not errorlevel 1 goto ready
)

<nul set /p =.
timeout /t 2 /nobreak >nul
goto wait_loop

:ready
echo.
echo [OK] 服务已就绪
echo.
echo 访问地址：http://localhost:!WEB_PORT!
echo.
echo 默认账号：admin
echo 默认密码：admin123（首次启动时由脚本生成，请尽快修改）
echo.
echo 常用命令：
echo   查看状态：python scripts\production_ops.py --env-file .env status
echo   查看日志：python scripts\production_ops.py --env-file .env logs --tail 200
echo   停止服务：python scripts\production_ops.py --env-file .env stop
echo.
if /i "!WEB_BIND!"=="0.0.0.0" (
  echo [!] 默认绑定 0.0.0.0:!WEB_PORT!，暴露到公网前请在 .env 中配置 TRUSTED_HOSTS 和反向代理 TLS
)
exit /b 0
