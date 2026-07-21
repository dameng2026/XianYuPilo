---
alwaysApply: false
description: 准备 git push/上传到 GitHub、提交新功能或修复、需要更新版本日志时的约束
---

# 更新日志维护规则

- 每次上传（git push）到 `main` 前，必须更新 `CHANGELOG.md`，不要只提交代码改动
- 当前版本号记录在 `CHANGELOG.md` 顶部已发布段落，遵循语义化版本：新增功能 → 次版本号 +1（如 v1.0.0 → v1.1.0）；仅修复 → 修订号 +1（v1.0.1）；破坏性变更 → 主版本号 +1（v2.0.0）
- 新改动写入 `[Unreleased]` 段。**重要**：本项目的实际工作流是"每次 push 到 `main` 即视为已发布"，因此 `[Unreleased]` 段会被"关于我们"页面直接展示为"最新版本"（日期取自 `CHANGELOG.md` 文件最后修改时间，对应最近一次 git push）。开发者无需在 push 前手动将 `[Unreleased]` 改为 `[vX.Y.Z] - YYYY-MM-DD`。
- 当需要明确标记一个正式版本号时（例如打 tag 发布 release），将 `[Unreleased]` 段改为 `[vX.Y.Z] - YYYY-MM-DD` 并在顶部重新起一个空的 `[Unreleased]` 段。这样历史版本会保留正式版本号，最新迭代内容继续累积在新的 `[Unreleased]` 段中并展示为"最新版本"。
- 每个版本段使用三类小标题：`### 新增`（新功能）、`### 变更`（对现有功能的修改）、`### 修复`（问题修复）；无内容的分类可省略。也允许使用其他小标题（如 `### 优化`、`### 功能亮点`、`### 技术架构`、`### 安全特性`），它们都会被解析展示。
- 条目格式推荐 `- **标题**：描述`（冒号或破折号分隔均可），也支持纯文本条目 `- 描述`。描述用一句话说清"改了什么"，不写实现细节；用户可见的功能变更才记录，纯重构/格式化/测试补充可不记
- 对应的 git tag 必须与 CHANGELOG 版本号一致，格式 `vX.Y.Z`（如 `v1.1.0`），打 tag 命令：`git tag vX.Y.Z`
- 同时修改了 Docker 镜像相关内容时，仍需遵循 `docker-image-publish.md` 规则
- `CHANGELOG.md` 会被后端 `commercial_bridge.py` 的 `parse_changelog_to_logs()` 解析，结果通过 `/system/about-content` 接口的 `logs` 字段返回给前端"关于我们"页面的"更新日志"板块展示。解析器有 60 秒内存缓存，文件 mtime 变更后自动重读
