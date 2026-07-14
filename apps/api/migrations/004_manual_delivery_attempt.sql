-- Migration 004: persistent, duplicate-resistant manual-delivery state machine.
-- MySQL 8.0. External message/platform calls are never executed by migration.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `manual_delivery_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `order_id` BIGINT NOT NULL COMMENT '本地 xianyu_trade_order.id',
  `account_id` BIGINT NOT NULL COMMENT '本地闲鱼账号 ID',
  `external_order_id` VARCHAR(200) NOT NULL COMMENT '平台订单 ID',
  `idempotency_key` VARCHAR(128) NOT NULL COMMENT '客户端或服务端生成的幂等键',
  `content_digest` CHAR(64) NOT NULL COMMENT '发货正文 SHA-256，仅用于防止键/内容错配',
  `delivery_record_id` BIGINT NULL COMMENT '关联 delivery_record.id',
  `delivery_mode` VARCHAR(32) NOT NULL DEFAULT 'text',
  `quantity_requested` INT NOT NULL DEFAULT 1,
  `session_id` VARCHAR(200) NOT NULL COMMENT '已解析的 IM 会话 ID',
  `peer_id` VARCHAR(200) NOT NULL COMMENT '已解析的买家接收 ID',
  `item_id` VARCHAR(200) NOT NULL COMMENT '平台商品 ID',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/message_sent/success/failed/unknown',
  `retry_scope` VARCHAR(32) NULL COMMENT 'message/platform_confirm',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `message_started_at` DATETIME NULL,
  `message_confirmed_at` DATETIME NULL,
  `platform_confirmed_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '脱敏、限长的可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_manual_delivery_attempt_order` (`order_id`),
  UNIQUE KEY `uk_manual_delivery_attempt_key` (`idempotency_key`),
  KEY `idx_manual_delivery_attempt_state_lease` (`state`, `lease_until`),
  KEY `idx_manual_delivery_attempt_record` (`delivery_record_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='手动发货的持久化幂等与恢复状态';
