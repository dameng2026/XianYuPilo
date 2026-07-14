-- Migration 009: durable single-flight state for real-time automatic delivery.
-- No external marketplace or messaging operation is executed by this migration.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `realtime_delivery_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `event_key` CHAR(64) NOT NULL COMMENT '账号隔离的稳定事件幂等键',
  `account_id` BIGINT NOT NULL,
  `external_order_id` VARCHAR(200) NULL,
  `source_event_id` VARCHAR(200) NOT NULL,
  `session_id` VARCHAR(200) NOT NULL,
  `peer_id` VARCHAR(200) NOT NULL,
  `item_id` VARCHAR(200) NOT NULL,
  `rule_id` BIGINT NULL,
  `delivery_record_id` BIGINT NULL,
  `delivery_mode` VARCHAR(32) NOT NULL,
  `content_digest` CHAR(64) NOT NULL COMMENT '发货正文摘要，不存储正文或卡密',
  `quantity_requested` INT NOT NULL DEFAULT 1,
  `card_group_id` BIGINT NULL,
  `auto_confirm_shipment` SMALLINT NOT NULL DEFAULT 0,
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/message_sending/message_sent/platform_confirming/success/failed/unknown',
  `retry_scope` VARCHAR(32) NULL COMMENT 'message/platform_confirm',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `message_started_at` DATETIME NULL,
  `message_confirmed_at` DATETIME NULL,
  `platform_confirm_started_at` DATETIME NULL,
  `platform_confirmed_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '脱敏、限长、可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_realtime_delivery_attempt_event` (`event_key`),
  KEY `idx_realtime_delivery_attempt_state_lease` (`state`, `lease_until`),
  KEY `idx_realtime_delivery_attempt_account_order` (`account_id`, `external_order_id`),
  KEY `idx_realtime_delivery_attempt_record` (`delivery_record_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='实时自动发货持久化幂等、租约与恢复状态';

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'card_item'
      AND column_name = 'realtime_attempt_id'
  ),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD COLUMN `realtime_attempt_id` BIGINT NULL COMMENT ''实时发货认领尝试 ID'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'card_item'
      AND column_name = 'claim_token'
  ),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD COLUMN `claim_token` VARCHAR(64) NULL COMMENT ''实时发货原子认领令牌'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'card_item'
      AND index_name = 'idx_card_item_realtime_claim'
  ),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD INDEX `idx_card_item_realtime_claim` (`realtime_attempt_id`, `claim_token`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'card_item'
      AND index_name = 'idx_card_item_available_group'
  ),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD INDEX `idx_card_item_available_group` (`group_id`, `status`, `deleted`, `id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
