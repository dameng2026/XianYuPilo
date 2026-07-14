-- Migration 021: durable, duplicate-resistant item-polish tasks.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `item_polish_task` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(64) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `idempotency_key` VARCHAR(128) NOT NULL,
  `request_digest` CHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/running/completed/partial/failed/needs_verification/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `total_count` INT NOT NULL DEFAULT 0,
  `processed_count` INT NOT NULL DEFAULT 0,
  `polished_count` INT NOT NULL DEFAULT 0,
  `already_done_count` INT NOT NULL DEFAULT 0,
  `failed_count` INT NOT NULL DEFAULT 0,
  `unknown_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL,
  `started_time` DATETIME NULL,
  `finished_time` DATETIME NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_item_polish_task_id` (`task_id`),
  UNIQUE KEY `uk_item_polish_task_key` (`idempotency_key`),
  KEY `idx_item_polish_account_created` (`account_id`, `created_time`),
  KEY `idx_item_polish_state_lease` (`status`, `lease_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商品擦亮持久任务';

CREATE TABLE IF NOT EXISTS `item_polish_task_item` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `task_db_id` BIGINT NOT NULL,
  `goods_id` BIGINT NOT NULL,
  `account_id` BIGINT NOT NULL,
  `external_goods_id` VARCHAR(200) NOT NULL,
  `title_snapshot` VARCHAR(500) NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/confirmed/already_done/failed/needs_verification/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `remote_started_at` DATETIME NULL,
  `remote_confirmed_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_item_polish_task_goods` (`task_db_id`, `goods_id`),
  KEY `idx_item_polish_item_state` (`task_db_id`, `status`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商品擦亮逐商品结果';
