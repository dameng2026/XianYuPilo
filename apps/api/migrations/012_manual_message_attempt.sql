-- Migration 012: durable exactly-once attempts for operator-triggered messages.
-- Message bodies, image URLs, raw conversation IDs, and raw peer IDs are not stored.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `manual_message_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `idempotency_key` VARCHAR(128) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `session_digest` CHAR(64) NOT NULL COMMENT '会话标识 SHA-256，不存原始会话 ID',
  `peer_digest` CHAR(64) NOT NULL COMMENT '接收方标识 SHA-256，不存原始用户 ID',
  `payload_digest` CHAR(64) NOT NULL COMMENT '消息类型及正文/图片地址 SHA-256，不存消息内容',
  `message_type` VARCHAR(16) NOT NULL COMMENT 'text/image',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/sending/confirmed/failed/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `send_started_at` DATETIME NULL,
  `confirmed_at` DATETIME NULL,
  `local_message_id` BIGINT NULL,
  `platform_message_digest` CHAR(64) NULL COMMENT '平台消息 ID 摘要，不存原始 ID',
  `last_error_code` VARCHAR(64) NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_manual_message_attempt_key` (`idempotency_key`),
  KEY `idx_manual_message_attempt_state_lease` (`state`, `lease_until`),
  KEY `idx_manual_message_attempt_account_created` (`account_id`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='人工消息持久化幂等、有限租约与未知结果隔离';
