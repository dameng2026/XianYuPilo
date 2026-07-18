# Setup wizard for first-time users on Windows.
# Checks Docker, generates random secrets, validates .env, and starts compose.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[错误] $msg" -ForegroundColor Red }

# Step 1: Check Docker
Write-Info "检查 Docker..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Docker 未安装。请先安装 Docker Desktop：https://docs.docker.com/desktop/install/windows-install/。安装完成后重新运行本脚本。"
    exit 1
}
$composeVersion = docker compose version 2>$null
if (-not $composeVersion) {
    Write-Err "Docker Compose v2 不可用。请升级 Docker Desktop。"
    exit 1
}
Write-Info "Docker 已就绪。"

# Step 2: Check .env
if (-not (Test-Path ".env")) {
    Write-Info ".env 不存在，从 .env.example 复制..."
    Copy-Item ".env.example" ".env"
}

# Step 3: Ensure ./secrets directory with random values
$secretsDir = ".\secrets"
if (-not (Test-Path $secretsDir)) {
    Write-Info "创建 $secretsDir 目录并生成随机 secrets..."
    New-Item -ItemType Directory -Path $secretsDir -Force | Out-Null

    function New-Secret($length) {
        $bytes = New-Object byte[] $length
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        return [Convert]::ToBase64String($bytes).Substring(0, $length)
    }

    # Placeholder admin password hash. User must replace with their own.
    '$2b$12$placeholder.admin.password.hash.replace.me' | Out-File -FilePath "$secretsDir\admin-password-hash" -NoNewline -Encoding utf8
    New-Secret 32 | Out-File -FilePath "$secretsDir\mysql-root-password" -NoNewline -Encoding utf8
    New-Secret 32 | Out-File -FilePath "$secretsDir\mysql-app-password" -NoNewline -Encoding utf8
    New-Secret 32 | Out-File -FilePath "$secretsDir\mysql-migrate-password" -NoNewline -Encoding utf8
    New-Secret 32 | Out-File -FilePath "$secretsDir\redis-password" -NoNewline -Encoding utf8
    New-Secret 48 | Out-File -FilePath "$secretsDir\jwt-secret" -NoNewline -Encoding utf8
    New-Secret 48 | Out-File -FilePath "$secretsDir\cookie-crypto-secret" -NoNewline -Encoding utf8
    New-Secret 32 | Out-File -FilePath "$secretsDir\internal-api-token" -NoNewline -Encoding utf8
    # Optional integrations: empty files
    '' | Out-File -FilePath "$secretsDir\commercial-backend-access-token" -NoNewline -Encoding utf8
    '' | Out-File -FilePath "$secretsDir\embedding-api-key" -NoNewline -Encoding utf8
    '' | Out-File -FilePath "$secretsDir\ai-provider-api-key" -NoNewline -Encoding utf8
    '' | Out-File -FilePath "$secretsDir\amap-api-key" -NoNewline -Encoding utf8

    Write-Warn "已在 $secretsDir 生成随机 secrets。"
    Write-Warn "admin-password-hash 是占位符，请用 bcrypt cost>=12 重新生成你自己的密码 hash："
    Write-Warn '  python -c "import bcrypt; print(bcrypt.hashpw(b''YOUR_PASSWORD'', bcrypt.gensalt(rounds=12)).decode())" > secrets\admin-password-hash'
}

# Step 4: Validate compose config
Write-Info "校验 docker compose 配置..."
$null = docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Err "docker compose 配置校验失败。请检查 .env 文件是否填写完整。"
    exit 1
}
Write-Info "配置校验通过。"

# Step 5: Start
Write-Info "启动 docker compose（首次会拉取/构建镜像，请耐心等待）..."
docker compose up -d --wait

Write-Info "✅ 启动成功！"
$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { '8080' }
Write-Info "访问 http://localhost:$webPort"
$adminUser = if ($env:ADMIN_USERNAME) { $env:ADMIN_USERNAME } else { 'admin' }
Write-Info "默认账号: $adminUser"
Write-Warn "默认密码请参考 $secretsDir\admin-password-hash 生成时使用的原文。"
