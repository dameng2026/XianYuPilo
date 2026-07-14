-- Migration 011: enforce AI auto-reply work policy and durable daily quotas.
-- Existing buyer-facing attempts are classified conservatively; ambiguous or
-- confirmed sends occupy quota while explicit failures do not.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_auto_reply_daily_quota` (
  `account_id` BIGINT NOT NULL,
  `quota_date` DATE NOT NULL COMMENT 'AI 客服配置时区内的自然日',
  `occupied_count` INT NOT NULL DEFAULT 0 COMMENT '预留中加已发送或结果未知',
  `consumed_count` INT NOT NULL DEFAULT 0 COMMENT '已发送或结果未知',
  `released_count` INT NOT NULL DEFAULT 0 COMMENT '明确未发送并释放的累计次数',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`, `quota_date`),
  KEY `idx_ai_reply_quota_date` (`quota_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 自动回复按账号与配置时区自然日的并发安全额度';

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'ai_auto_reply_attempt'
      AND column_name = 'quota_date'
  ),
  'SELECT 1',
  'ALTER TABLE `ai_auto_reply_attempt` ADD COLUMN `quota_date` DATE NULL COMMENT ''额度所属配置时区自然日'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'ai_auto_reply_attempt'
      AND column_name = 'quota_status'
  ),
  'SELECT 1',
  'ALTER TABLE `ai_auto_reply_attempt` ADD COLUMN `quota_status` VARCHAR(16) NULL COMMENT ''reserved/consumed/released'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'ai_auto_reply_attempt'
      AND column_name = 'policy_timezone'
  ),
  'SELECT 1',
  'ALTER TABLE `ai_auto_reply_attempt` ADD COLUMN `policy_timezone` VARCHAR(64) NULL COMMENT ''额度与工作时段使用的明确时区'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'ai_auto_reply_attempt'
      AND index_name = 'idx_ai_auto_reply_quota'
  ),
  'SELECT 1',
  'ALTER TABLE `ai_auto_reply_attempt` ADD INDEX `idx_ai_auto_reply_quota` (`account_id`, `quota_date`, `quota_status`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE `ai_auto_reply_attempt`
SET `quota_date` = COALESCE(`quota_date`, DATE(`created_time`)),
    `policy_timezone` = COALESCE(NULLIF(`policy_timezone`, ''), 'Asia/Shanghai'),
    `quota_status` = CASE
      WHEN `quota_status` IS NOT NULL THEN `quota_status`
      WHEN `state` IN ('confirmed', 'message_sent', 'unknown') THEN 'consumed'
      WHEN `state` = 'failed' THEN 'released'
      ELSE 'reserved'
    END
WHERE `quota_date` IS NULL
   OR `quota_status` IS NULL
   OR `policy_timezone` IS NULL
   OR `policy_timezone` = '';

INSERT IGNORE INTO `ai_auto_reply_daily_quota` (
  `account_id`, `quota_date`, `occupied_count`, `consumed_count`,
  `released_count`, `created_time`, `updated_time`
)
SELECT
  `account_id`,
  `quota_date`,
  SUM(CASE WHEN `quota_status` IN ('reserved', 'consumed') THEN 1 ELSE 0 END),
  SUM(CASE WHEN `quota_status` = 'consumed' THEN 1 ELSE 0 END),
  SUM(CASE WHEN `quota_status` = 'released' THEN 1 ELSE 0 END),
  NOW(),
  NOW()
FROM `ai_auto_reply_attempt`
WHERE `quota_date` IS NOT NULL
GROUP BY `account_id`, `quota_date`;

