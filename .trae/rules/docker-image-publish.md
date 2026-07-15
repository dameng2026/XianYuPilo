---
alwaysApply: false
description: 涉及 git push 到 main、Docker 镜像构建发布、修改 Dockerfile/docker-compose/镜像命名空间，或新增容器化服务时的约束
---

# Docker 镜像自动构建与发布

- 推送到 `main` 分支会自动触发 `.github/workflows/docker-publish.yml`，构建 `api`/`web`/`crawler` 镜像并推送到 GHCR，无需手动 `docker push`
- 镜像命名固定为 `ghcr.io/xianyu-assistant-opensource/xianyu-assistant-{api,web,crawler}`，标签为 `latest` + git 短 SHA
- 镜像以多架构 manifest 形式发布（`linux/amd64` + `linux/arm64`），覆盖 x86 服务器与 Apple Silicon Mac；GHCR 会自动按宿主架构派发对应层
- 修改 `Dockerfile`、`requirements.txt`、`package*.json` 等影响镜像内容的文件后，下一次 push `main` 会自动重建镜像，不要手动构建推送
- 新增或修改 Python 依赖时，`apps/api/requirements.txt` 必须使用 `pip-compile --generate-hashes` 跨平台生成（包含 amd64 与 arm64 的 wheel hash），否则 arm64 构建会因 hash 校验失败
- 新增或修改 Node 依赖时无需关心架构，`npm ci` 会自动按宿主架构解析
- 新增需要容器化服务时，其 `Dockerfile` 的基础镜像必须是多架构镜像（同时支持 amd64 与 arm64），否则多架构构建会在 arm64 节点失败
- `docker-compose.yml` 中每个自定义服务必须同时保留 `image`（指向 GHCR，默认值用 `${*_IMAGE:-ghcr.io/...}` 形式）和 `build`（本地源码），便于 `.env` 覆盖或 `--build` 切回本地构建
- 修改镜像命名空间时必须同步四处：`docker-publish.yml` 的 `IMAGE_NAMESPACE`、`docker-compose.yml` 三个服务的 `image` 默认值、`.env.example` 的 `IMAGE_*` 变量
- 新增需要容器化的服务时，在 workflow 的 `matrix.include` 中加入对应 `component` 与 `context`，并在 `docker-compose.yml` 中以相同 `image`/`build` 模式声明该服务
- 一键运行流程为 `docker compose pull && docker compose up -d`；本地构建用 `docker compose up -d --build`
