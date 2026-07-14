-- Migration 010: durable, duplicate-resistant AI auto-reply delivery.
-- This migration performs no marketplace, model-provider, or messaging calls.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_auto_reply_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `event_key` CHAR(64) NOT NULL COMMENT '账号隔离的买家消息事件 SHA-256 幂等键',
  `account_id` BIGINT NOT NULL,
  `source_message_digest` CHAR(64) NOT NULL COMMENT '来源消息标识摘要，不存上游消息 ID',
  `request_digest` CHAR(64) NOT NULL COMMENT '本次回复上下文摘要，不存买家正文',
  `session_id` VARCHAR(200) NOT NULL,
  `peer_id` VARCHAR(200) NOT NULL,
  `goods_id` VARCHAR(200) NULL,
  `seller_external_uid` VARCHAR(200) NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/generating/message_sending/message_sent/confirmed/failed/unknown',
  `retry_scope` VARCHAR(32) NULL COMMENT 'generation/message/local',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `generation_started_at` DATETIME NULL,
  `message_started_at` DATETIME NULL,
  `message_confirmed_at` DATETIME NULL,
  `local_confirmed_at` DATETIME NULL,
  `reply_digest` CHAR(64) NULL COMMENT 'AI 回复正文摘要',
  `encrypted_reply` TEXT NULL COMMENT '仅在本地确认前短暂保留的 AES-GCM 密文',
  `local_message_id` BIGINT NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '脱敏、限长、可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_auto_reply_attempt_event` (`event_key`),
  UNIQUE KEY `uk_ai_auto_reply_attempt_source` (`account_id`, `source_message_digest`),
  KEY `idx_ai_auto_reply_state_lease` (`state`, `lease_until`),
  KEY `idx_ai_auto_reply_account_created` (`account_id`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 自动回复持久化幂等、有限租约与未知结果隔离';

