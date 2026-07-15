---
alwaysApply: false
description: 准备 git push/上传到 GitHub、提交新功能或修复、需要更新版本日志时的约束
---

# 更新日志维护规则

- 每次上传（git push）到 `main` 前，必须更新 `CHANGELOG.md`，不要只提交代码改动
- 当前版本号记录在 `CHANGELOG.md` 顶部已发布段落，遵循语义化版本：新增功能 → 次版本号 +1（如 v1.0.0 → v1.1.0）；仅修复 → 修订号 +1（v1.0.1）；破坏性变更 → 主版本号 +1（v2.0.0）
- 新改动先写入 `[Unreleased]` 段，发布时（打 tag 或正式上传）将 `[Unreleased]` 改为 `[vX.Y.Z] - YYYY-MM-DD` 并重新起一个空的 `[Unreleased]`
- 每个版本段使用三类小标题：`### 新增`（新功能）、`### 变更`（对现有功能的修改）、`### 修复`（问题修复）；无内容的分类可省略
- 描述用一句话说清"改了什么"，不写实现细节；用户可见的功能变更才记录，纯重构/格式化/测试补充可不记
- 对应的 git tag 必须与 CHANGELOG 版本号一致，格式 `vX.Y.Z`（如 `v1.1.0`），打 tag 命令：`git tag vX.Y.Z`
- 同时修改了 Docker 镜像相关内容时，仍需遵循 `docker-image-publish.md` 规则
