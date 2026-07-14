# 开源版本地运行说明

> 本文只适用于本机开发，不是生产部署依据。生产部署必须使用根目录
> `.env.example`、`start.sh`/`start.bat` 和 `docs/production-readiness.md`。

## 目标

这份说明只解决一件事：

- 确保前端、开源版本地 API、本地 crawler 走的是同一条本机链路
- 避免 Web/API 误连商业版或旧环境，导致闲鱼扫码登录出现“异地登录/像是在洛杉矶登录”之类的问题

## 当前约定

本地联调默认使用以下地址：

- Web 开发页：`http://127.0.0.1:15176/#/login`
- API：`http://127.0.0.1:15177`
- API 存活检查：`http://127.0.0.1:15177/health`
- API 就绪检查：`http://127.0.0.1:15177/health/ready`（数据库、迁移、Redis、消息自动化与 Token 刷新器均须为 `ok`）
- crawler：`http://127.0.0.1:15178`
- crawler 就绪检查：`http://127.0.0.1:15178/ready`（配置与 Playwright Chromium 均须可用）
- Scheduler Worker 不监听端口，入口为 `python -m app.worker`；本地脚本通过 PID、精确命令归属和 Worker 心跳共同判断它是否健康

扫码登录相关前端请求统一走：

- `POST /api/qrlogin/generate`
- `POST /api/qrlogin/status/{sessionId}`
- `POST /api/qrlogin/cleanup`

前端不会直连商业版后端地址。

以上主站扫码接口由本地 API 的同一服务端会话负责，不是飞书对话功能。飞书自建
应用仍可发送 Session 过期通知、查询账号状态和普通回复，但飞书二维码自动登录已
退役；收到二维码意图时会明确引导到 Web 管理端的账号管理页使用“重新扫码”。

旧 Java 网关使用的 `/api/internal/qrlogin/*` 已整体退役；带有效内部令牌的已知旧
路径只返回结构化 HTTP 410 与迁移指引，且不再提供原始 Cookie 读取。公共主站状态
接口只返回凭据是否可用，实际 Cookie 始终留在服务端并在持久化前加密。同步 MTOP
扫码网络调用由 API 在线程中执行，不阻塞异步请求事件循环。

Crawler 中曾存在的 QR session 路由 `create/generate/status/cleanup` 及无状态
`capture/solve` 已全部移除。`capture` 在返回截图后会关闭浏览器，`solve` 会新建
另一个浏览器会话，两者之间没有 session handoff；而旧 session 路由在 pending
阶段不返回二维码，生产 headless 模式下也没有用户可见的扫码入口。主站同名
`/api/qrlogin/*` 路径属于 Python API 的另一套真实会话实现，仍然保留。不得恢复或
重新组合已退役的 Crawler 路由冒充可扫码流程。

## 商业版桥接

当前环境模板默认关闭商业版桥接：URL 与 token 都留空，本地使用兜底数据。
只有在桥接所有者书面授权、提供独立最小权限 token 且 HTTPS 证书验证通过后，
才应在服务端 `.env` 填写 `COMMERCIAL_BACKEND_*`。浏览器页面不应收集商业版账号、
密码、数据库信息或桥接 token。旧 handoff 中的公网探测记录只是历史信息，不是
当前可用性或上线证据。

开源版不提供注册、VIP/会员、充值、订阅、独立计费或通用支付。商业桥中唯一可
产生交易的功能是广告申请及其广告订单专用支付；广告桥未配置时，该页面不会使用
本地兜底套餐或伪支付订单，而是明确禁用提交与支付。其他业务不得复用 `/api/ads`
支付路径。

`COMMERCIAL_BACKEND_PAID_AD_PLACEMENT_ENFORCED` 必须保持 `false`，直到联调已证明未支付、
已关闭或已过期的广告订单不会激活，也不会进入轮播或文字广告展示接口。

## 推荐启动方式

首次本地开发请将 `.env.development.example` 复制为 `.env`，自行生成
`ADMIN_PASSWORD_HASH` 并填写本机 MySQL 凭据。该模板中的 `dev-only` 密钥只能在
本机使用；生产预检会拒绝它们。不要把生产 `.env` 用于本地调试。

### 方式 1：直接使用脚本

在仓库根目录执行：

```bat
start-local.bat
status-local.bat
stop-local.bat
verify-local.bat
```

说明：

- `start-local.bat` 会先检查三个隔离端口、运行版本化数据库迁移与 Crawler 构建，再通过 `scripts/local-dev.ps1` 启动 API、Crawler、Web 和 Scheduler Worker 并等待全部就绪；任一步失败都会回滚本次受管进程，批处理文件不会另起一份 Worker
- `status-local.bat` 会检查 `15177 / 15178 / 15176`，并单独显示无端口 Scheduler 的 `owned` 与 `healthy` 状态
- `stop-local.bat` 对有端口服务只停止 PID 文件与端口监听者一致的受管进程；对 Scheduler 则只停止 `scheduler.pid` 指向且可执行文件与 `python -m app.worker` 命令完全匹配的进程，不会按端口或进程名批量终止
- Scheduler 的标准输出和错误日志分别写入 `output/local-dev/scheduler.out.log` 与 `output/local-dev/scheduler.err.log`，PID 写入 `output/local-dev/pids/scheduler.pid`
- 受管 Python 进程统一使用 UTF-8 写日志，避免 Windows 默认 GBK 导致跨编辑器、CI 或日志采集器查看时乱码
- `verify-local.bat` 会串行执行 Web 构建、API 编译检查和 Crawler 构建

### 方式 2：手动启动

先显式升级并确认数据库版本，再启动 API：

```powershell
Push-Location apps/api
python -m app.migrations upgrade
python -m app.migrations status
Pop-Location
python apps/api/run.py
```

不要跳过迁移步骤；API/Worker 只做只读版本检查，存在 pending/unknown 版本时会拒绝启动。

在另一个终端中启动无端口 Scheduler Worker：

```powershell
cd apps/api
python -m app.worker
```

手动启动时可用 `python -m app.worker --check` 验证心跳；受管脚本会为本地栈设置独立的心跳文件，避免与其他项目实例混淆。

启动 crawler：

```powershell
cd apps/crawler
npm run dev
```

启动 Web：

```powershell
cd apps/web
npm run dev
```

## 前端代理要求

`apps/web/vite.config.js` 当前默认就是：

- `/api` -> `http://127.0.0.1:15177`
- `/uploads` -> `http://127.0.0.1:15177`

也就是说，正常情况下不需要再改 `VITE_API_PROXY_TARGET`。

只有在你临时改了本地 API 端口时，才需要覆盖：

```powershell
$env:VITE_API_PROXY_TARGET='http://127.0.0.1:15177'
npm --prefix apps/web run dev
```

## 联调通过标准

如果本地链路正确，应同时满足：

- `http://127.0.0.1:15177/health/ready` 返回 HTTP 200、`status=ready`，且全部 `components` 为 `ok`
- `http://127.0.0.1:15178/ready` 返回 HTTP 200、`status=ready`
- `http://127.0.0.1:15176/#/login` 可访问
- `status-local.bat` 中 Scheduler 的 `owned=True` 且 `healthy=True`
- `verify-local.bat` 可一键串行跑完上述验收链路
- 登录后 `GET /api/system/runtime-status` 返回：
  - `crawlerBaseUrl=http://127.0.0.1:15178`
  - `commercialBridgeMode=local-fallback` 或 `commercial`
  - `commercialUserHealthOk` 与 `commercialAdminHealthOk` 为真实探活结果
- `POST /api/qrlogin/generate` 能返回 `sessionId` 和二维码 Base64

## 历史验证记录（不能替代当前验收）

以下记录来自早期本地联调，只用于排查回归；每次发布仍须重新运行当前 CI、
`verify-local.bat` 和生产候选环境验收：

- `POST http://127.0.0.1:15177/api/auth/login` 可成功登录固定管理员账号
- `POST http://127.0.0.1:15177/api/qrlogin/generate` 可成功生成二维码登录会话
- `GET /api/system/runtime-status` 已返回
  - `dbConnected=true`
  - `redisConnected=true`
  - `commercialBridgeConfigured=false`
  - `commercialBridgeMode=local-fallback`
  - `commercialUserHealthOk=true`
  - `commercialAdminHealthOk=true`

## 常见问题

### 1. 扫码登录提示异地，像是连到了别的环境

先检查这三件事：

- API 是否真的跑在本机 `15177`
- Web 是否通过本地 Vite 代理请求 `/api/*`

主站扫码不经过 Crawler；Crawler 的 `15178` 就绪状态只影响滑块求解。确认 API 与
Web 代理均指向本机后，前端扫码链路才不会直接打到商业版后端。

### 2. 打开账号管理页后二维码请求失败

先执行：

```bat
status-local.bat
```

确认这三个端口都正常：

- `15177`
- `15178`
- `15176`

同时确认 Scheduler 行为 `owned=True` 且 `healthy=True`。Scheduler 没有端口，因此仅查看三个端口不能证明定时任务执行器已经启动。

### 3. `runtime-status` 里桥接还是本地兜底

这是正常的，只说明：

- 商业版地址可达
- 但还没有回填 `COMMERCIAL_BACKEND_ACCESS_TOKEN`
- 或者线上 bridge 虽然可能已存在，但当前无 token 无法完成正式验收

等商业版桥接接口完成后，只需要补 token，不需要修改开源版扫码链路。
