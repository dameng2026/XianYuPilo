-- Migration 033: 商品同步任务表
-- 补建 xianyu_goods_sync_task 表（模型已存在于 entities.py，但之前缺少建表迁移）。
-- 使用 CREATE TABLE IF NOT EXISTS，对已有数据库安全（幂等）。

CREATE TABLE IF NOT EXISTS `xianyu_goods_sync_task` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `sync_id` VARCHAR(80) NOT NULL COMMENT '同步任务ID',
  `account_id` BIGINT NOT NULL,
  `status` VARCHAR(30) NOT NULL DEFAULT 'queued' COMMENT 'queued/running/completed/failed',
  `progress` INT NULL DEFAULT 0,
  `total_count` INT NULL DEFAULT 0,
  `new_count` INT NULL DEFAULT 0,
  `updated_count` INT NULL DEFAULT 0,
  `skipped_count` INT NULL DEFAULT 0,
  `off_shelf_count` INT NULL DEFAULT 0,
  `detail_synced_count` INT NULL DEFAULT 0,
  `duration_seconds` FLOAT NULL DEFAULT 0,
  `error_message` TEXT NULL,
  `started_time` DATETIME NULL,
  `finished_time` DATETIME NULL,
  `deleted` SMALLINT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sync_id` (`sync_id`),
  INDEX `idx_goods_sync_task_account` (`account_id`, `deleted`),
  INDEX `idx_goods_sync_task_status` (`status`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品同步任务表';
