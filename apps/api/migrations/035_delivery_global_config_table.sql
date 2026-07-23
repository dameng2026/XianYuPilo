-- Migration 035: 全店默认发货配置表
-- 补建 delivery_global_config 表（代码在 delivery_workflow_compat.py:3734/3765/3769/3775 使用，
-- 但之前缺少建表迁移，导致 GET/PUT /api/auto-delivery/global-config 接口无法正常工作）。
-- 代码已有容错（表不存在时 GET 返回空对象），但 PUT 保存配置会失败。
-- 使用 CREATE TABLE IF NOT EXISTS，对已有数据库安全（幂等）。
-- 字段依据 delivery_workflow_compat.py 中的 SQL 推断：
--   SELECT config_json FROM delivery_global_config WHERE deleted = 0 LIMIT 1
--   SELECT id FROM delivery_global_config WHERE deleted = 0 LIMIT 1
--   UPDATE delivery_global_config SET config_json = :cfg, updated_time = NOW() WHERE id = :id
--   INSERT INTO delivery_global_config (config_json, created_time, updated_time, deleted) VALUES (...)

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `delivery_global_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `config_json` LONGTEXT NOT NULL COMMENT '配置JSON',
  `deleted` SMALLINT NOT NULL DEFAULT 0 COMMENT '0未删除 1已删除',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='全店默认发货配置';
