# 首次启动初始化向导（Windows PowerShell 版本）
# 自动生成所有 secrets 文件、bcrypt admin 密码 hash 和 .env
# 用法：在仓库根目录执行 .\scripts\setup-wizard.ps1
#Requires -Version 5.1
[CmdletBinding()]
param(
  [string]$AdminPassword = "admin123"
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectDir

$SecretsDir = Join-Path $ProjectDir "secrets"
$DefaultAdminPassword = $AdminPassword

function Write-Info { param([string]$Msg) Write-Host "• $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "✓ $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "! $Msg" -ForegroundColor Yellow }
function Write-Die  { param([string]$Msg) Write-Host "✗ $Msg" -ForegroundColor Red; exit 1 }

# ---------- 1. 前置依赖检查 ----------
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
  Write-Die "未检测到 Docker，请先安装：https://docs.docker.com/get-docker/"
}
$composeVersion = & docker compose version 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Die "未检测到 Docker Compose v2，请升级 Docker 或安装 docker-compose-plugin"
}

# ---------- 2. 创建 secrets 目录 ----------
# 注意：docker-compose secrets file 模式下，容器内进程（如 mysql 用户）需要读取权限
# 因此 secrets 文件权限不能是 0600（仅 owner 可读），Windows 不强制 chmod 但容器会继承 ACL
if (-not (Test-Path $SecretsDir)) {
  New-Item -ItemType Directory -Path $SecretsDir -Force | Out-Null
}

# 生成 base64url 随机字符串
function New-RandomSecret {
  param([int]$Bytes = 32)
  $buffer = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($buffer)
  $base64 = [Convert]::ToBase64String($buffer)
  # 转 base64url：去掉 = padding，+→-，/→_
  return $base64.TrimEnd('=').Replace('+','-').Replace('/','_')
}

# 写入 secret 文件（已存在且非空则跳过）
function Write-Secret {
  param([string]$File, [string]$Content)
  if (Test-Path $File) {
    $existing = Get-Content $File -Raw -ErrorAction SilentlyContinue
    if ($existing -and $existing.Trim().Length -gt 0) { return }
  }
  [System.IO.File]::WriteAllText($File, $Content)
}

# 生成空的可选 secret 文件
function Touch-Optional {
  param([string]$File)
  if (-not (Test-Path $File)) {
    [System.IO.File]::WriteAllText($File, "")
  }
}

# ---------- 3. 生成必需的随机 secrets ----------
Write-Info "生成随机 secrets（如已存在则跳过）..."

Write-Secret (Join-Path $SecretsDir "mysql-root-password")      (New-RandomSecret 32)
Write-Secret (Join-Path $SecretsDir "mysql-app-password")       (New-RandomSecret 32)
Write-Secret (Join-Path $SecretsDir "mysql-migration-password") (New-RandomSecret 32)
Write-Secret (Join-Path $SecretsDir "redis-password")           (New-RandomSecret 32)
Write-Secret (Join-Path $SecretsDir "jwt-secret")               (New-RandomSecret 64)
Write-Secret (Join-Path $SecretsDir "cookie-crypto-secret")     (New-RandomSecret 64)
Write-Secret (Join-Path $SecretsDir "internal-api-token")       (New-RandomSecret 64)

# ---------- 4. 生成空的可选 secrets ----------
Touch-Optional (Join-Path $SecretsDir "commercial-backend-access-token")
Touch-Optional (Join-Path $SecretsDir "embedding-api-key")
Touch-Optional (Join-Path $SecretsDir "ai-provider-api-key")
Touch-Optional (Join-Path $SecretsDir "amap-api-key")

# ---------- 5. 生成 admin bcrypt 密码 hash ----------
$hashFile = Join-Path $SecretsDir "admin-password-hash"
if (Test-Path $hashFile) {
  $existingHash = Get-Content $hashFile -Raw -ErrorAction SilentlyContinue
  if ($existingHash -and $existingHash.Trim().Length -gt 0) {
    Write-Ok "admin-password-hash 已存在（跳过生成）"
  } else {
    $needHash = $true
  }
} else {
  $needHash = $true
}

if ($needHash) {
  Write-Info "生成 admin bcrypt 密码 hash（cost 12）..."

  $env:ADMIN_PASSWORD = $DefaultAdminPassword
  $hashValue = ""
  $failedReasons = @()

  # --- 方案 1：主机 Python + bcrypt（已装） ---
  $pythonCmd = $null
  foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
      $testBcrypt = & $cmd -c "import bcrypt" 2>$null
      if ($LASTEXITCODE -eq 0) {
        $pythonCmd = $cmd
        break
      }
    }
  }

  if ($pythonCmd) {
    Write-Info "  [1/4] 使用主机 $pythonCmd + bcrypt 生成..."
    try {
      $hashValue = & $pythonCmd -c @'
import os, bcrypt
pw = os.environ["ADMIN_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
'@ 2>$null
      if ($hashValue -and $hashValue.Trim().Length -gt 0) {
        Write-Ok "  [1/4] 主机 Python bcrypt 生成成功"
      } else {
        $failedReasons += "主机 Python bcrypt 调用失败"
      }
    } catch {
      $failedReasons += "主机 Python bcrypt 异常: $_"
    }
  } else {
    $failedReasons += "主机无 Python bcrypt 包"
  }

  # --- 方案 2：主机 pip install bcrypt ---
  if (-not $hashValue -and $pythonCmd) {
    Write-Info "  [2/4] 尝试 pip install bcrypt..."
    $pipOutput = & $pythonCmd -m pip install --user --quiet --timeout 60 bcrypt 2>&1
    $testBcrypt = & $pythonCmd -c "import bcrypt" 2>$null
    if ($LASTEXITCODE -eq 0) {
      try {
        $hashValue = & $pythonCmd -c @'
import os, bcrypt
pw = os.environ["ADMIN_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
'@ 2>$null
        if ($hashValue -and $hashValue.Trim().Length -gt 0) {
          Write-Ok "  [2/4] pip install bcrypt 成功并生成 hash"
        } else {
          $failedReasons += "pip install 后 bcrypt 调用失败"
        }
      } catch {
        $failedReasons += "pip install 后 bcrypt 异常"
      }
    } else {
      $failedReasons += "pip install bcrypt 失败: $($pipOutput | Select-Object -Last 1)"
    }
  }

  # --- 方案 3：Docker 容器 python:3.11-slim ---
  if (-not $hashValue) {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
      Write-Info "  [3/4] 使用 Docker 临时容器生成（python:3.11-slim，首次约 30-60s）..."
      $dockerOutput = & docker run --rm -e ADMIN_PASSWORD python:3.11-slim sh -c 'pip install --quiet --no-cache-dir --timeout 60 bcrypt 2>&1 && python -c "import os, bcrypt; pw=os.environ[\"ADMIN_PASSWORD\"].encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())"' 2>&1
      # 从输出中提取 bcrypt hash（以 $2 开头的行）
      $hashValue = ($dockerOutput | Where-Object { $_ -match '^\$2[aby]\$' } | Select-Object -First 1)
      if ($hashValue -and $hashValue.Trim().Length -gt 0) {
        Write-Ok "  [3/4] Docker python:3.11-slim 生成成功"
      } else {
        $failedReasons += "Docker python:3.11-slim 失败: $($dockerOutput | Select-Object -Last 2 | Select-Object -First 1)"
      }
    } else {
      $failedReasons += "主机未安装 Docker"
    }
  }

  # --- 方案 4：Docker 容器 + 国内清华源 ---
  if (-not $hashValue) {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
      Write-Info "  [4/4] 使用国内 PyPI 镜像源重试（清华源）..."
      $dockerOutput = & docker run --rm -e ADMIN_PASSWORD python:3.11-slim sh -c 'pip install --quiet --no-cache-dir --timeout 60 -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn bcrypt 2>&1 && python -c "import os, bcrypt; pw=os.environ[\"ADMIN_PASSWORD\"].encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())"' 2>&1
      $hashValue = ($dockerOutput | Where-Object { $_ -match '^\$2[aby]\$' } | Select-Object -First 1)
      if ($hashValue -and $hashValue.Trim().Length -gt 0) {
        Write-Ok "  [4/4] 国内源 Docker 生成成功"
      } else {
        $failedReasons += "Docker 国内源失败: $($dockerOutput | Select-Object -Last 2 | Select-Object -First 1)"
      }
    }
  }

  Remove-Item Env:ADMIN_PASSWORD -ErrorAction SilentlyContinue

  if ($hashValue -and $hashValue.Trim().Length -gt 0) {
    [System.IO.File]::WriteAllText($hashFile, $hashValue.Trim())
    Write-Ok "admin bcrypt hash 生成完成"
  } else {
    # 所有方案失败：不终止脚本，由 start.bat 在镜像构建后用 api 容器兜底生成
    Write-Warn "所有 bcrypt 生成方案均失败，将延迟到镜像构建后用 api 容器生成"
    foreach ($reason in $failedReasons) {
      Write-Warn "  - $reason"
    }
    # 创建空文件作为标记，start.bat 会检测并用 api 镜像生成
    [System.IO.File]::WriteAllText($hashFile, "")
  }
}

# ---------- 6. 创建 .env ----------
$envFile = Join-Path $ProjectDir ".env"
$envExample = Join-Path $ProjectDir ".env.example"
if (-not (Test-Path $envFile)) {
  if (Test-Path $envExample) {
    Copy-Item $envExample $envFile
    Write-Ok "已从 .env.example 创建 .env"
  } else {
    Write-Die ".env.example 不存在，无法创建 .env"
  }
} else {
  Write-Ok ".env 已存在（跳过创建）"
}

# ---------- 7. 完成 ----------
Write-Host ""
Write-Ok "初始化完成"
Write-Host ""
Write-Host "默认管理员账号："
Write-Host "  用户名：admin"
Write-Host "  密码：$DefaultAdminPassword"
Write-Host ""
Write-Warn "请尽快登录后修改默认密码！"
Write-Host ""
Write-Host "下一步："
Write-Host "  启动服务：.\start.bat"
Write-Host "  或手动：docker compose pull ; docker compose up -d"
Write-Host ""
